"""Replay excerpts through production routing and real bounded TEST SELECTs."""
import asyncio,json,sys,argparse
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import conversation_chat as chat
MESSAGES=[
 "Bonjour, j'ai besoin de la création de ces deux articles : Modern foam boards A XPS 4 CM et Modern foam boards B XPS 4 CM. Unité M2, fournisseur Modern for Foam and Plastic, catégorie AR.",
 '131',
 'F234.',
 'TVA souhaitée 20 %.',
 "ET POUR LE SITE est-ce qu'il y a ou non ?",
 'Vérifie le site 131',
 'Recherche la catégorie « NEGOSE ».',
 'F992.',
 'Et pour le fournisseur ?',
 'Oui, utilise la catégorie NEG.',
 'Change le site 131 vers 201',
 'Le site est 131',
]
async def main():
 args=argparse.ArgumentParser();args.add_argument('--resume',action='store_true');args=args.parse_args()
 out={'checked_at':datetime.now(timezone.utc).isoformat(),'status':'RUNNING','real_qwen':False,'routing':'PRODUCTION','real_sql':True,'sage_writes':0,'turns':[],
      'scope':'Ordered replay of the exact excerpts provided; the full original user transcript was not attached.'}
 owner=uuid4();value=chat.create(owner);out['conversation_id']=str(value['id']);ids=None
 if args.resume:
  out=json.loads((ROOT/'logs/chat-performance-replay.json').read_text(encoding='utf-8'))
  if out.get('error'):out.setdefault('attempt_failures',[]).append({'error':out['error'],'turn':out['turns'][-1]})
  out['turns']=[t for t in out['turns'] if t.get('status')=='PASS'];out['status']='RUNNING'
  with chat.db.connection() as c:owner=c.execute('SELECT owner_id FROM chat_conversations WHERE id=%s',(out['conversation_id'],)).fetchone()['owner_id']
  from uuid import UUID
  value=chat.read(owner,UUID(out['conversation_id']));ids=[a['id'] for a in value['state']['articles']]
 start=len(out['turns'])
 try:
  for n,text in enumerate(MESSAGES[start:],start+1):
   previous=value['state'].get('articles',[])
   value=await chat.send(owner,value['id'],text,value['revision'])
   assistant=[m for m in value['messages'] if m['role']=='assistant'][-1]
   tools=[m for m in value['messages'] if m['role']=='tool'][-1]
   a=value['state']['articles']
   step={'number':n,'user':text,'assistant':assistant['content'],'state':value['state'],'delta':assistant['payload'].get('delta'),'provenance':assistant['payload'].get('provenance'),'tools':tools['payload']}
   out['turns'].append(step)
   assert len(a)==2,('article_count',n,len(a))
   if ids is None:ids=[x['id'] for x in a]
   assert [x['id'] for x in a]==ids,('article_identity',n)
   assert all(x['code_article']==f'MFB-{"AB"[i]}-XPS-40' and x['unite']=='M2' for i,x in enumerate(a)),('code_unit',n)
   assert all(x['categorie']==('NEG' if n>=10 else 'AR') for x in a),('category_mutation',n)
   if n>=2:assert all(x['site']==('201' if n==11 else '131') for x in a),('site_mutation',n)
   if n>=3:assert all(x['code_fournisseur']==('F992' if n>=8 else 'F234') for x in a),('supplier_mutation',n)
   if n>=4:assert all(x['taux_tva']=='20' for x in a),('lost_rate',n)
   if n in [5,6,7,9]:assert [{k:x.get(k) for k in chat.FIELDS} for x in a]==[{k:x.get(k) for k in chat.FIELDS} for x in previous],('read_only_turn_mutated_fields',n)
   if n==7:assert value['state']['awaiting_confirmation']['value']=='NEG'
   if n>=8:
    for i,x in enumerate(a):
     assert x['reference_interne']==f'F992-MFB-{"AB"[i]}-40'
     assert any(z['value']==f'F234-MFB-{"AB"[i]}-40' and z['obsolete'] for z in x['obsolete_derived_values'])
    assert not any(q['field']=='code_fournisseur' for q in value['state']['pending'])
   assert tools['payload']['real_sql'] and all(r.get('ok') for r in tools['payload']['results'].values()),('sql_unavailable',n)
   assert assistant['payload']['provenance'].get('real_model_called') or assistant['payload']['provenance'].get('validation_and_sql_required')
   step['status']='PASS'
   print('TURN',n,'PASS',flush=True)
   (ROOT/'logs/chat-performance-replay.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
  out['status']='PASS';out['final_drafts']=a;out['real_qwen']=any(t['provenance'].get('real_model_called') for t in out['turns'])
 except Exception as e:
  out['status']='FAILED';out['error_type']=type(e).__name__;out['error']=str(e)[:500]
  print('REPLAY FAILED',out['error'],flush=True)
 finally:
  (ROOT/'logs/chat-performance-replay.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
  lines=['# Conversation après correction','',out['scope'],'']
  for t in out['turns']:lines+=['## Message '+str(t['number']),'','**Utilisateur :** '+t['user'],'','**Agent :** '+t['assistant'],'']
  lines+=['Résultat : '+out['status']+'. Aucune écriture Sage.']
  (ROOT/'logs/ETAPE-5-PERFORMANCES-TRANSCRIPTION.md').write_text('\n'.join(lines),encoding='utf-8')
  print('REPLAY',out['status'],flush=True)
if __name__=='__main__':asyncio.run(main())
