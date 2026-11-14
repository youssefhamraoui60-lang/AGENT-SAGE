import asyncio,copy
import pytest
from app.services.article_relations import track
from app.services import conversation_tools as engine,modification_actions
from app.services.modification_policy import ArticleModificationPolicy

def state():
    return {'supplier_target':'TEST','articles':[{'id':'a','code_article':'GEN_AINATLASE','operation':{'status':'succeeded'}}]}

def test_relation_retains_parent_and_explicit_two_supplier_selection():
    s=state()
    r=track(s,'dire fihe le fourniseur rachide ou cimat')
    assert r['article']=='GEN_AINATLASE' and r['supplier_codes']==[]
    track(s,'ah homa hado direhame bejouje')
    assert r['supplier_codes']==[]  # no guessed selection from ambiguous results
    track(s,'F10043 — Ahmde rachide ou cimat F007 dire hado bejouje')
    assert r['supplier_codes']==['F10043','F007']
    assert track(s,'direhame fi articles GEN_AINATLASE')['article']=='GEN_AINATLASE'

@pytest.mark.parametrize('text',['annule ce rattachement','je veux créer un fournisseur','réactiver le fournisseur F007','cherche le fournisseur F007','modifier le téléphone du fournisseur F007'])
def test_change_of_task_clears_relation(text):
    s=state();track(s,'ajoute les fournisseurs à cet article')
    assert track(s,text) is None and 'article_supplier_request' not in s

def test_relation_is_not_inferred_for_ambiguous_articles_or_cross_folder():
    s=state();s['articles'].append({'code_article':'OTHER','operation':{'status':'succeeded'}})
    assert track(s,'ajoute le fournisseur F007') is None
    assert track(s,'ajoute le fournisseur F007 à GEN_AINATLASE')['article']=='GEN_AINATLASE'
    s['supplier_target']='OB'
    assert track(s,'direhame bejouje') is None

def test_final_pointer_uses_historical_codes_and_only_prepares_article(monkeypatch):
    s=state();track(s,'dire fihe le fournisseur rachide ou cimat')
    track(s,'F10043 et F007 dire hado bejouje')
    attempts=[]
    def prepare(d):
        attempts.append(copy.deepcopy(d));d['operation']={'status':'prepared'}
    monkeypatch.setattr(modification_actions,'prepare_draft',prepare)
    history=[{'role':'user','content':'F10043 et F007 dire hado bejouje'}]
    result=asyncio.run(engine.turn(None,None,'direhame fi articles GEN_AINATLASE',s,history))
    assert result['phase']=='article_supplier_relation'
    assert attempts[0]['resource']=='article' and attempts[0]['code']=='GEN_AINATLASE'
    assert attempts[0]['changes']['add_suppliers']==[{'code':'F10043','reference':''},{'code':'F007','reference':''}]
    assert result['state']['tool_orchestration']['sage_writes']==0

def test_wrong_supplier_modification_tool_does_not_change_target():
    s=state();track(s,'ajoute les fournisseurs à cet article')
    result=engine.dispatch('select_for_modification',engine.Read(resource='supplier',code='F007'),s,'ah homa hado direhame bejouje')
    assert not result['ok'] and 'GEN_AINATLASE' in result['message']
    assert not s.get('modification_drafts')

def test_explicit_refusal_cannot_prepare_supplier_association(monkeypatch):
    monkeypatch.setattr(modification_actions,'prepare_draft',lambda d:pytest.fail('Unexpected preparation'))
    text="N'ajoute pas le fournisseur F007 à GEN_AINATLASE"
    with pytest.raises(ValueError,match='refusal'):
        engine.dispatch('prepare_modification',engine.Modify(resource='article',code='GEN_AINATLASE',changes=[engine.Change(field='add_suppliers',value=['F007'],evidence=text)]),state(),text)

def test_site_removal_with_active_orders_explains_real_block():
    analysis={'complete':True,'used':True,'history':[{'tab':'PORDER'}],'active':[{'tab':'PORDER'}],'unknown_activity':[]}
    with pytest.raises(Exception,match='PORDER'):
        ArticleModificationPolicy().check('article',{'remove_sites':['201']},analysis)

def test_site_removal_without_activity_stays_blocked_until_validated_method():
    analysis={'complete':True,'used':False,'history':[],'active':[],'unknown_activity':[]}
    with pytest.raises(Exception,match='retrait physique'):
        ArticleModificationPolicy().check('article',{'remove_sites':['201']},analysis)
