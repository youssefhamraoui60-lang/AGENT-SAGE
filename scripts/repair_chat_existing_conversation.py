"""Repair a proven local question-extraction error, with an audit and fresh SQL checks.
No Sage writes. Requires an exact conversation id; never performs a bulk rewrite.
"""
import argparse,asyncio,copy,json,sys
from pathlib import Path
from uuid import UUID
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import conversation_chat as chat,chat_turns

async def main():
 parser=argparse.ArgumentParser();parser.add_argument('--conversation',type=UUID,required=True);args=parser.parse_args()
 proof={'conversation_id':str(args.conversation),'sage_writes':0,'status':'NOT_APPLIED'}
 with chat.db.connection() as c:
  row=c.execute('SELECT * FROM chat_conversations WHERE id=%s FOR UPDATE',(args.conversation,)).fetchone()
  if not row:raise ValueError('conversation_not_found')
  state=copy.deepcopy(row['state']);a=state.get('articles',[])
  if len(a)!=2 or state.get('_pending') or not all(x.get('site')=='EST' for x in a):raise ValueError('exact_known_corruption_precondition_not_met')
  messages=c.execute('SELECT id,role,content,payload FROM chat_messages WHERE conversation_id=%s ORDER BY id',(args.conversation,)).fetchall()
  last_user=[m for m in messages if m['role']=='user'][-1]
  literal_sites=[]
  for m in messages:
   if m['role']=='user':
    turn=chat_turns.analyse(m['content'],state)
    if not turn.readonly and turn.values.get('site'):literal_sites.append((m['id'],turn.values['site']))
  if not literal_sites:raise ValueError('no_explicit_historical_site')
  source_id,site=literal_sites[-1]
  if site=='EST':raise ValueError('historical_value_not_safe')
  proof['repairs']=[{'article_id':x['id'],'field':'site','old':'EST','new':site,'source_message_id':source_id} for x in a]
  for x in a:
   chat.invalidate(x);x['site']=site;x.setdefault('sources',{})['site']='restored_explicit_user_declaration_from_history'
   x['checks']={'valid_basic':False,'errors':['reverification_required'],'sage_created':False,'tools':{}}
  chat.save_conversation_context(c,row['owner_id'],args.conversation,state)
  revision=c.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s RETURNING revision',(args.conversation,)).fetchone()['revision']
  chat.append(c,args.conversation,'system',f"Correction de mémoire : site EST remplacé par {site}, conformément au message utilisateur {source_id}. Le dernier message est réanalysé ci-dessous pour vérifier la catégorie et le fournisseur. L’historique précédent est conservé ; aucune écriture Sage.",{'source':'controlled_question_state_repair','repairs':proof['repairs'],'replayed_user_message_id':last_user['id']})
 owner=row['owner_id']
 try:
  result=await chat.send(owner,args.conversation,last_user['content'],revision)
  a=result['state']['articles']
  assert len(a)==2 and all(x['site']==site and x['code_fournisseur']=='F992' and x['categorie']=='AR' for x in a)
  assert result['state']['awaiting_confirmation']['value']=='NEG'
  proof['status']='PASS';proof['reanalysed_message_id']=last_user['id'];proof['final']=[{k:x.get(k) for k in ['id','site','categorie','code_fournisseur','reference_interne']} for x in a]
 except Exception as exc:
  proof['status']='SITE_REPAIRED_RECHECK_FAILED';proof['error_type']=type(exc).__name__;proof['error']=str(exc)[:300]
 (ROOT/'logs/chat-corrections-existing-memory.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(proof,ensure_ascii=True))
if __name__=='__main__':asyncio.run(main())
