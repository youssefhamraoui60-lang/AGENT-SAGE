import sys,asyncio,copy
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests'),str(ROOT/'TEST')]
from app.services import conversation_tools as engine,article_sql_dialogue,modification_actions
from test_article_direct_sql import simulated

def state():
 return {'supplier_target':'TEST','articles':[{'id':str(uuid4()),'designation':'Lafarge3k','categorie':'MAIN','unite':'KG','requested_sites':['201','202'],'fournisseurs':[],'operation':{'status':'blocked'}}], 'tool_read_results':[{'ok':True,'folder':'TEST','resource':'supplier','query':'Cimat','rows':[{'BPSNUM_0':'F007','BPRNAM_0':'CIMAT'},{'BPSNUM_0':'F552','BPRNAM_0':'CIMAT BETON'}]}]}

def question():return [{'role':'assistant','content':'Deux fiches correspondent à Cimat : F007 CIMAT ou F552 CIMAT BETON. Laquelle faut-il rattacher au fournisseur de l’article ?'}]

def test_both_suppliers_are_retained_in_creation(monkeypatch):
 monkeypatch.setattr(article_sql_dialogue,'prepare_state',lambda changed,*args:'Brouillon conservé.')
 s=state();r=asyncio.run(engine.turn(None,None,'les deux',s,question()))
 assert {p['code'] for p in r['state']['articles'][0]['fournisseurs']}=={'F007','F552'}
 assert not s['articles'][0]['fournisseurs'] and not r['state']['articles'][0]['approved']

def test_both_suppliers_are_proposed_on_existing_article(monkeypatch):
 def prepare(d):d['operation']={'status':'blocked','message':'Déclencheur à vérifier.'};d['approved']=False
 monkeypatch.setattr(modification_actions,'prepare_draft',prepare)
 s=state();s['articles'][0].update(code_article='MAIN_LAFARGE3K',operation={'status':'succeeded'})
 s['article_supplier_request']={'folder':'TEST','article':'MAIN_LAFARGE3K','supplier_codes':[]}
 r=asyncio.run(engine.turn(None,None,'les deux',s,question()))
 d=r['state']['modification_drafts'][0]
 assert {p['code'] for p in d['changes']['add_suppliers']}=={'F007','F552'} and not d['approved']

def test_both_reaches_readonly_creation_preview(simulated):
 s=state();a=s['articles'][0]
 a.update(code_article='QATEST201',categorie='AVNS',unite='UN',requested_sites=['201'],fournisseurs=[])
 r=asyncio.run(engine.turn(None,None,'les deux',s,question()))
 a=r['state']['articles'][0]
 assert {p['code'] for p in a['fournisseurs']}=={'F007','F552'}
 assert all(not execute for _,execute in simulated[1])

def test_incremental_supplier_changes_merge(monkeypatch):
 monkeypatch.setattr(engine.settings,'sage_modification_enabled',True)
 monkeypatch.setattr(modification_actions,'prepare_draft',lambda d:d.update(operation={'status':'blocked','message':'Conservé'}))
 s={'supplier_target':'TEST','modification_drafts':[{'id':str(uuid4()),'resource':'article','code':'ART1','folder':'TEST','changes':{'add_suppliers':[{'code':'F007','reference':''}]},'operation':{'status':'blocked'}}]}
 a=engine.Modify(resource='article',code='ART1',changes=[engine.Change(field='add_suppliers',value=[{'code':'F552','reference':''}],evidence='F552')])
 engine.dispatch('prepare_modification',a,s,'ajoute F552 à ART1')
 assert {p['code'] for p in s['modification_drafts'][0]['changes']['add_suppliers']}=={'F007','F552'}
