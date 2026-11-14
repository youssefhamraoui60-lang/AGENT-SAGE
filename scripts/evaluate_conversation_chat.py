"""Real Qwen evaluation. Controlled negative SQL fixtures are explicitly distinguished."""
import asyncio,json,sys,argparse,traceback,re
from pathlib import Path
from uuid import uuid4,UUID
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import conversation_chat as chat,chat_tools as tools,business_store as db

REFERENCE="Bonjour, j'ai besoin de la création de ces deux articles : Modern foam boards A XPS 4 CM et Modern foam boards B XPS 4 CM. Unité M2, fournisseur Modern for Foam and Plastic, catégorie AR."
ORIGINAL_RUN=tools.run
class Fixture:
 def __init__(self,mode='normal'):self.mode=mode
 def __call__(self,calls):
  out={}
  for c in calls:
   t=c['tool'];a=c['args'];rows=[];ok=self.mode!='offline'
   if ok:
    if t=='get_article_categories' and a.get('Category'):rows=[{'TCLCOD_0':a['Category'],'STOFCY_0':' ','STU_0':'M2','PUU_0':'M2','SAU_0':'M2','ACCCOD_0':'STD','VACITM_0':'NOR'}]
    if t=='get_units':rows=[{'UOM_0':v} for v in set([a.get('Unit'),a.get('Unit2')]) if v]
    if t=='get_sites':rows=[{'FCY_0':a.get('Site') or '201','LEGCPY_0':'20'}]
    if t=='search_suppliers':
     if a.get('Supplier')=='F234':rows=[{'BPSNUM_0':'F234','BPRNAM_0':'Modern for Foam and Plastic','BPRNAM_1':''}]
     elif self.mode=='ambiguous':rows=[{'BPSNUM_0':'F100','BPRNAM_0':'Modern A'},{'BPSNUM_0':'F101','BPRNAM_0':'Modern B'}]
    if t=='check_article_duplicate' and (a.get('Code')=='EXIST001' or (self.mode=='collision' and a.get('Code') in ['MFB-A-XPS-40','MFB-B-XPS-40'])):rows=[{'ITMREF_0':a['Code'],'ITMDES1_0':'Controlled existing article'}]
    if t=='search_articles':rows=[{'ITMREF_0':'CONTROLLED-XPS','ITMDES1_0':'XPS exemple contrôlé','TCLCOD_0':'AR','ACCCOD_0':'STD','VACITM_0':'NOR'}]
    if t=='get_recent_articles':rows=[{'ITMREF_0':'CTRL-001','ITMDES1_0':'Exemple historique non règle'}]
    if t=='get_accounting_categories' and a.get('Label')=='Marchandises':rows=[{'TYP_0':1,'ACCCOD_0':'STD','COA_0':'FRA','DES_0':'Marchandises'}]
    if t=='get_tax_rules':rows=[{'VAT_0':'CONTROLLED20','VATRAT_0':20,'CPY_0':'20','LEG_0':'MAR'}]
   out[c['id']]={'id':c['id'],'tool':t,'ok':ok,'rows':rows,'source':'CONTROLLED_TEST_FIXTURE','code':None if ok else 'controlled_sql_offline'}
  return out

def articles(value):return value['state']['articles']
async def turn(owner,value,text,record):
 result=await chat.send(owner,value['id'],text,value['revision'])
 msg=[m for m in result['messages'] if m['role']=='assistant'][-1]
 record.append({'input':text,'response':msg['content'],'delta':msg['payload'].get('delta'),'provenance':msg['payload'].get('provenance'),'state':result['state']})
 assert msg['payload']['provenance']['real_model_called'] is True or (PRODUCTION_ROUTING and msg['payload']['provenance'].get('validation_and_sql_required'))
 return result

async def reference():
 owner=uuid4();value=chat.create(owner);turns=[];tools.run=ORIGINAL_RUN
 messages=[REFERENCE,'131.','F234.','Tu dois créer toi-même les codes articles et les références.',
  'Recherche automatiquement les paramètres comptables et TVA des articles XPS similaires.','TVA par défaut 20 %.','Catégorie comptable : Marchandises.']
 for message in messages:
  value=await turn(owner,value,message,turns)
  print('REFERENCE turn',len(turns),'completed',flush=True)
 a=articles(value)
 assert len(a)==2
 for index,item in enumerate(a):
  letter='AB'[index]
  expected={'designation':f'Modern foam boards {letter} XPS 4 CM','code_article':f'MFB-{letter}-XPS-40','reference_interne':f'F234-MFB-{letter}-40','categorie':'AR','unite':'M2','site':'131','code_fournisseur':'F234','taux_tva':'20','accounting_category':'Marchandises'}
  for k,v in expected.items():assert item.get(k)==v,(k,item.get(k),v)
  assert item.get('site_exclusive') is None
  assert not item.get('code_tva') and not item.get('code_comptable')
  assert not item.get('checks',{}).get('sage_created')
 return {'status':'PASS','conversation_id':str(value['id']),'owner_scope':str(owner),'real_qwen':True,'sql_mode':'REAL_TEST_SELECT','turns':turns,'drafts':a}

NAMES=['Deux articles','Informations manquantes','Mémoire multi-message','Correction site','Doublon','Fournisseur inconnu','Fournisseur ambigu','Dix articles','TVA/comptabilité','Références provisoires','Orthographe','Historique isolé','SQL réel','SQL indisponible','Sécurité','Invalidation approbation','Distinction catégories','Codes/collisions','Dépendance article-site','Questions non répétées']
async def scenario(number,variant):
 owner=uuid4();value=chat.create(owner);steps=[]
 mode={5:'normal',6:'normal',7:'ambiguous',14:'offline',18:'collision'}.get(number,'normal')
 tools.run=ORIGINAL_RUN if number==13 else Fixture(mode)
 initial=REFERENCE if variant==0 else 'Créer Modern foam boards A XPS 4 CM et Modern foam boards B XPS 4 CM ; cat AR ; unité M2 ; FRS Modern for Foam and Plastic.'
 if number==2:initial='Crée un article Panneau incomplet, catégorie AR.' if variant==0 else 'Besoin article Panneau incomplet ; cat AR ; unité M2.'
 if number==4:initial=REFERENCE+' Site 201.'
 if number==5:initial='Crée un article Test collision, code article EXIST001, catégorie NEG, unité UN, site 201.'
 if number==6:initial='Crée un article Panneau inconnu, catégorie AR, unité M2, fournisseur SOCIETE INCONNUE XYZ.'
 if number==8:
  initial='Créer les 10 articles suivants, site 201 :\n'+'\n'.join(f'{i}. Panneau test {i}, catégorie {"AR" if i%2 else "NEG"}, unité {"M2" if i%2 else "UN"}.' for i in range(1,11))
  if variant:initial=initial.replace('Panneau test','Composant test')
 if number==9 or number==17:initial=REFERENCE+' Site 131. TVA proposée 20 %. Catégorie comptable Marchandises.'
 if number==10:initial=REFERENCE+' Site 131. Code fournisseur F234. Propose toi-même les références internes.'
 if number==11:initial='bjr cree 2 articls : Modern foam boards A XPS 4 CM et Modern foam boards B XPS 4 CM ; u M2 ; frs Modern for Foam and Plastic ; cat AR.'
 if number==13:initial='Crée un article Test consultation contrôlée, catégorie NEG, unité UN, site 201, fournisseur F234.'
 if number==15:initial='Prépare un article Panneau sécurité, catégorie NEG, unité UN, site 201.'
 if variant:
  variants={
   5:'Création demandée : Test collision. Code article : EXIST001 ; site 201 ; unité UN ; catégorie NEG.',
   6:'Ajoute Panneau inconnu ; unité M2 ; cat AR ; FRS SOCIETE INCONNUE XYZ.',
   9:'Prépare Modern foam boards A XPS 4 CM et Modern foam boards B XPS 4 CM. Catégorie comptable : Marchandises ; TVA 20 % ; site 131 ; catégorie article AR ; unité M2 ; fournisseur Modern for Foam and Plastic.',
   10:'Deux articles à préparer, catégorie AR et unité M2 : Modern foam boards A XPS 4 CM / Modern foam boards B XPS 4 CM. Site 131. Fournisseur Modern for Foam and Plastic, code fournisseur F234. Les références internes sont à proposer.',
   11:'slt, besoin crer 2 art : Modern foam boards A XPS 4 CM + Modern foam boards B XPS 4 CM ; u M2 ; categ AR ; frs Modern for Foam and Plastic',
   13:"Préparation d'un article Test consultation contrôlée : unité UN, site 201, catégorie NEG, code fournisseur F234.",
   15:'Crée uniquement un brouillon pour Panneau sécurité, site 201, unité UN, catégorie NEG. Aucun envoi sans approbation.',
   17:"Crée Modern foam boards A XPS 4 CM et Modern foam boards B XPS 4 CM. Catégorie article : AR ; unité M2 ; site 131. Marchandises est la catégorie comptable ; TVA proposée 20 %. Aucun compte général ni code taxe n'est fourni."
  }
  initial=variants.get(number,initial)
 value=await turn(owner,value,initial,steps)
 if number==3:
  for message in ['131.','F234.','TVA 20 %.']:value=await turn(owner,value,message,steps)
 if number==4:value=await turn(owner,value,'Remplace le site par 131 pour les deux articles.' if variant==0 else 'Correction : site 131, au lieu de 201.',steps)
 if number==16:
  value['state']['articles'][0]['approved']=True
  chat.PERMITS[value['state']['articles'][0]['id']]={'synthetic':True}
  with db.connection() as conn:chat.save_conversation_context(conn,owner,value['id'],value['state'])
  value=await turn(owner,value,'Correction pour les deux articles : unité UN.' if variant==0 else 'Utilise désormais UN comme unité pour tous les articles.',steps)
 if number==20:
  for message in ['131.','F234.','TVA proposée 20 %.']:value=await turn(owner,value,message,steps)
 a=articles(value)
 if number in [1,3,4,9,10,11,17,18,20]:assert len(a)==2,('article_count',len(a))
 if number==1:
  assert all(x.get('categorie')=='AR' and x.get('unite')=='M2' for x in a)
 if number==2:assert any(q['field'] in ['site','unite'] for q in value['state']['pending'])
 if number==3:assert all(x.get('site')=='131' and x.get('code_fournisseur')=='F234' and x.get('taux_tva')=='20' for x in a)
 if number==4:assert all(x.get('site')=='131' for x in a)
 if number==5:assert 'duplicate_article_code' in a[0]['checks']['errors']
 if number==6:assert 'supplier_not_found' in a[0]['checks']['errors'] and not a[0].get('code_fournisseur')
 if number==7:assert 'supplier_ambiguous' in a[0]['checks']['errors'] and not a[0].get('code_fournisseur')
 if number==8:
  assert len(a)==10
  assert all(x['categorie']==('AR' if i%2 else 'NEG') and x['unite']==('M2' if i%2 else 'UN') for i,x in enumerate(a,1))
 if number==9 or number==17:assert all(x.get('taux_tva')=='20' and x.get('accounting_category')=='Marchandises' and x.get('categorie')=='AR' and not x.get('code_tva') and not x.get('code_comptable') and not x.get('compte_general') for x in a)
 if number==10:assert all(x.get('reference_interne') and not x.get('reference_fournisseur') and not x['checks']['supplier_reference_official'] for x in a)
 if number==11:assert all(x.get('categorie')=='AR' and x.get('unite')=='M2' for x in a)
 if number==12:
  assert chat.read(owner,value['id'])['state']==value['state']
  try:chat.read(uuid4(),value['id']);raise AssertionError('Cross-owner read allowed')
  except chat.crud.CrudError as e:assert e.status==404
 if number==13:
  toolmsg=[m for m in value['messages'] if m['role']=='tool'][-1]
  assert toolmsg['payload']['real_sql'] is True
  assert all(r.get('ok') for r in toolmsg['payload']['results'].values())
 if number==14:
  assert all('sql_checks_incomplete' in x['checks']['errors'] and not x['checks']['verified'] and 'supplier_lookup_unavailable' in x['checks']['errors'] for x in a)
  response=[m for m in value['messages'] if m['role']=='assistant'][-1]['content']
  assert 'indisponible' in response and 'n’a pas été retrouvé' not in response
 if number==15:
  try:chat.write_action(owner,value['id'],UUID(a[0]['id']),'prepare',value['revision']);raise AssertionError('Gate bypass')
  except chat.crud.CrudError as e:assert e.status==423
 if number==16:assert not a[0].get('approved') and a[0]['id'] not in chat.PERMITS and all(x.get('unite')=='UN' for x in a)
 if number==18:assert all(len(x['code_article'])<=20 and re.fullmatch('[A-Z0-9-]+',x['code_article']) and not x['checks']['tools']['duplicate']['rows'] for x in a)
 if number==19:assert not a[0]['checks']['article_site_dependency']['parent_exists'] and not a[0]['checks']['article_site_dependency']['creation_executed']
 if number==20:assert all(q['field'] not in ['site','unite','code_fournisseur'] for q in value['state']['pending'])
 return {'status':'PASS','number':number,'name':NAMES[number-1],'variant':variant,'conversation_id':str(value['id']),'real_qwen':any(s['provenance'].get('real_model_called') for s in steps),'routing':'PRODUCTION' if PRODUCTION_ROUTING else 'FORCED_QWEN','sql_mode':'REAL_TEST_SELECT' if number==13 else 'CONTROLLED_TEST_FIXTURE','steps':steps}

async def main():
 global PRODUCTION_ROUTING
 parser=argparse.ArgumentParser();parser.add_argument('--production-routing',action='store_true');parser.add_argument('--only',default='');parser.add_argument('--skip-reference',action='store_true');parser.add_argument('--reference-only',action='store_true');parser.add_argument('--variants',type=int,default=2);parser.add_argument('--repair-pass',action='store_true');parser.add_argument('--output',default='chat-real-evaluation.json');args=parser.parse_args()
 PRODUCTION_ROUTING=args.production_routing
 chat.model.FORCE_AI.set(not PRODUCTION_ROUTING)
 file=ROOT/'logs'/args.output
 out=json.loads(file.read_text(encoding='utf-8')) if file.exists() else {'created_at':datetime.now(timezone.utc).isoformat(),'cases':[],'sage_writes':0}
 if not args.skip_reference:
  try:out['reference']=await reference()
  except Exception as e:out['reference']={'status':'FAILED','error_type':type(e).__name__,'error':str(e)[:600]};print('REFERENCE FAILED',out['reference'],flush=True)
  file.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 selected=[int(x) for x in args.only.split(',') if x] or list(range(1,21))
 if args.repair_pass:selected=[2,5,6,9,10,11,13,15,17]
 if args.reference_only:selected=[]
 for number in selected:
  for variant in range(args.variants):
   if args.repair_pass and number not in [2,9,17] and variant==0:continue
   try:result=await scenario(number,variant)
   except Exception as e:result={'number':number,'variant':variant,'status':'FAILED','real_qwen':True,'error_type':type(e).__name__,'error':str(e)[:600]}
   out['cases']=[r for r in out['cases'] if (r['number'],r['variant'])!=(number,variant)]+[result]
   file.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
   print('CASE',number,'VARIANT',variant,result['status'],result.get('error',''),flush=True)
 tools.run=ORIGINAL_RUN
 print('EVALUATION COMPLETED',flush=True)
PRODUCTION_ROUTING=False
if __name__=='__main__':asyncio.run(main())
