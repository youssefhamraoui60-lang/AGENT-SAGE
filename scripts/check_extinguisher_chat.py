"""User regression: extraction and limited read-only SQL, no conversation/ERP writes."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import chat_fast_extract,conversation_chat as chat,chat_tools
text='Bonjour youssef, Merci de créer ces nouveaux articles :\nExtincteur à poudre / unite / FG/ CHAOUIA PROTECT/ARTICLE NON GERER\nExtincteur à CO2 / Unite/ FG/ CHAOUIA PROTECT/ ARTICLE NON GERER\nCordialement'
delta,provenance=chat_fast_extract.extract(text,{})
state=chat.merge({'articles':[]},delta,text)
plan,bindings=chat.tool_plan(state);results=chat_tools.run(plan.calls)
state=chat.prepare_article_draft(state,results,bindings);state['pending']=chat.questions(state)
output=chat.compose(state,new=True)
proof={'mode':'LIVE_SQL_READ_ONLY_NO_ERP_WRITE','state':state,'message':output,'checks':{'article_count':len(state['articles']),'all_un':all(a['unite']=='UN' for a in state['articles']),'all_fg_declared':all(a['categorie']=='FG' for a in state['articles']),'all_not_managed':all(a['gestion_stock']=='1' for a in state['articles']),'category_verified':all(a['checks'].get('verified',{}).get('categorie') for a in state['articles']),'supplier_exact_match':all(a['checks']['tools'].get('supplier',{}).get('exact_name_match') for a in state['articles'])}}
(ROOT/'logs/extincteurs-chat-check.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps({'checks':proof['checks'],'errors':[a['checks']['errors'] for a in state['articles']],'supplier_proposals':[a['proposals'].get('code_fournisseur') for a in state['articles']]},ensure_ascii=False))
