import pytest
from app.services.article_sql_dialogue import clean_text,dimensioned_references,initial,recover_declared_batch
from app.services.modification_resolvers import CategoryResolver
from app.services import erp_modification as mod

EMAIL='Bonjour, Merci de créer les 2 références d article. Fournisseur RZ timber qui est déjà existant MADRIER 37*177*4  MADRIER 37*177*3 Cdlt'
NAMES=['MADRIER 37*177*4','MADRIER 37*177*3']

def test_dimensioned_batch_keeps_both_literal_names():
    assert dimensioned_references(EMAIL)==NAMES
    delta,_=initial(EMAIL,{})
    assert [a.designation for a in delta.articles]==NAMES

@pytest.mark.parametrize('value',['MADRIER 37*177*4','**MADRIER 37*177*4**','`MADRIER 37*177*4`'])
def test_dimensions_are_not_markdown(value):
    assert clean_text(value)==NAMES[0]

def test_recovery_preserves_identity_supplier_and_cancellation():
    article={'id':'stable','designation':NAMES[0],'code_fournisseur':'F1013'}
    state={'articles':[article]}
    history=[{'role':'user','content':EMAIL}]
    assert recover_declared_batch(state,history)==1
    assert [a['designation'] for a in state['articles']]==NAMES
    assert state['articles'][0] is article
    assert state['articles'][1]['fournisseur_nom']=='RZ timber'
    assert recover_declared_batch(state,history)==0
    assert recover_declared_batch({'articles':[article]},history+[{'role':'user','content':'annule ces articles'}])==0

@pytest.mark.parametrize('label',['negose','negouse','négoce'])
def test_category_correction_keeps_real_code(label):
    rows=[{'TCLCOD_0':'NEG','TCLDES_0':'Négoce','STOFCY_0':''}]
    assert CategoryResolver().search(label,rows,{})[0]['code']=='NEG'

def test_empty_snapshot_collections_are_normalized_only_after_validation(monkeypatch):
    monkeypatch.setattr(mod,'transport',lambda *args,**kwargs:{'ok':True,'folder':'TEST','code':'A123'})
    assert mod.snapshot('article','A123')['article_suppliers']==[]
    monkeypatch.setattr(mod,'transport',lambda *args,**kwargs:{'ok':False,'folder':'TEST','code':'A123'})
    with pytest.raises(Exception):mod.snapshot('article','A123')
