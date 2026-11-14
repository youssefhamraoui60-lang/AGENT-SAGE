from copy import deepcopy
import pytest
from app.core.config import settings
from app.services import conversation_chat as chat,chat_fast_extract
from app.services.chat_model import Delta


def state():
    return {'articles':[{'id':str(i),'designation':f'Modern foam boards {label} XPS 4 CM',
        'code_article':f'MFB-{label}-XPS-40','categorie':'NEG','unite':'M2','site':'202',
        'fournisseur_nom':'Modern for Foam and Plastic','code_fournisseur':'F234',
        'reference_interne':f'F234-MFB-{label}-40','sources':{'reference_interne':'internal_proposal_not_supplier_reference'},
        'proposals':{'code_fournisseur':'F234'}} for i,label in enumerate(('A','B'),1)],
        'pending':[{'field':'code_fournisseur','text':'Quel fournisseur ?'}]}


@pytest.mark.parametrize('text',['pas de forniseur dans cette article','ouipas de fronseur','Sans fournisseur',
    'aucun fournisseur','retire le fournisseur','pas de fournisseur pour ces articles'])
def test_removal_clears_supplier_and_only_derived_references(text):
    before=state();fast=chat_fast_extract.extract(text,before)
    assert fast and fast[1]['route']=='explicit_field_removal'
    after=chat.merge(before,fast[0],text)
    assert len(after['articles'])==2
    for old,new in zip(before['articles'],after['articles']):
        for name in ('designation','code_article','categorie','unite','site'):assert old[name]==new[name]
        assert new['fournisseur_nom'] is None and new['code_fournisseur'] is None
        assert not new.get('reference_interne') and not new.get('proposals',{}).get('code_fournisseur')
    assert not any(q['field']=='code_fournisseur' for q in chat.questions(after))
    assert 'Sans fournisseur' in chat.compose(after)


def test_removal_ignores_model_memory_and_respects_article_target():
    before=state()
    delta=Delta(intent='new',shared={'fournisseur_nom':'Modern for Foam and Plastic'},
                articles=[{'designation':'Duplicated old article'}])
    after=chat.merge(before,delta,'pas de fournisseur pour le deuxième article')
    assert len(after['articles'])==2
    assert after['articles'][0]['code_fournisseur']=='F234'
    assert after['articles'][1]['code_fournisseur'] is None


def test_question_does_not_remove_supplier():
    before=state()
    after=chat.merge(before,Delta(intent='lookup'),'Est-ce possible sans fournisseur ?')
    assert after['articles']==before['articles']


def test_declared_site_is_understood_without_model():
    before=state();before['articles'][0]['site']=None;before['articles'][1]['site']=None
    delta,provenance=chat_fast_extract.extract('Site déclaré 202',before)
    after=chat.merge(before,delta,'Site déclaré 202')
    assert provenance['route']=='explicit_site'
    assert all(a['site']=='202' for a in after['articles'])


def test_yes_to_unknown_site_gets_a_short_clear_question():
    before=state()
    for a in before['articles']:a['site']=None
    before['pending']=[{'field':'site','text':'Quel site ?'}]
    after=chat.merge(before,Delta(intent='update'),'oui')
    answer=chat.compose(after)
    assert 'Un « oui » ne précise pas le site' in answer and 'Code proposé' not in answer


def test_business_validity_is_separate_from_execution_scope(monkeypatch):
    monkeypatch.setattr(settings,'sage_powershell_chat_enabled',True)
    a=state()['articles'][0];a['fournisseur_nom']=None;a['code_fournisseur']=None
    refs={k:{'ok':True,'rows':[]} for k in ['duplicate','recent','article_site']}
    refs.update(category={'ok':True,'rows':[{'TCLCOD_0':'NEG'}]},
        units={'ok':True,'rows':[{'UOM_0':'M2'}]},site={'ok':True,'rows':[
            {'FCY_0':'202','FCYNAM_0':'Frais généraux','LEGCPY_0':'20','CPYNAM_0':'OULD BOUAZZA'}]})
    a['checks']=chat.validate_article_draft(a,refs)
    assert a['checks']['valid_basic'] and 'site_201_explicit_required' not in a['checks']['errors']
    answer=chat.compose({'articles':[a]})
    assert 'Catégories retrouvées' in answer and 'NEG' in answer and 'Unités retrouvées' in answer
    assert 'OULD BOUAZZA' in answer and '202' in answer
