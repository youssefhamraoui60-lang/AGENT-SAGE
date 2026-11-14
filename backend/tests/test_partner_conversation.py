"""Partner draft regressions using real merger with no database or ERP writes."""
from copy import deepcopy
import pytest
from app.services import chat_partners as partners,conversation_chat as chat,chat_tools
from app.services.chat_model import Delta


def turn(text,state=None):
    state=state or {'articles':[]}
    delta=partners.literal_extract(text,state)
    assert delta is not None
    return chat.merge(state,delta,text)


@pytest.mark.parametrize('kind,word',[('supplier','fournisseur'),('customer','client')])
def test_contact_create_correct_without_touching_articles(kind,word):
    state=turn(f'Créer un {word} Société Atlas, pays MA, devise MAD, email contact@atlas.example.')
    assert state['articles']==[]
    p=state['partners'][0]
    assert p['kind']==kind and p['nom']=='Société Atlas'
    assert p['email']=='contact@atlas.example' and p['pays']=='MA'
    after=turn('Email nouveau@atlas.example',state)
    assert len(after['partners'])==1
    assert after['partners'][0]['email']=='nouveau@atlas.example'
    assert after['partners'][0]['history'][-1]['changes'][0]['before']=='contact@atlas.example'
    assert state['partners'][0]['email']=='contact@atlas.example'


def test_single_company_with_et_is_not_two_partners():
    delta=partners.literal_extract('Créer un fournisseur Dupont et Fils.',{'articles':[]})
    assert len(delta.fournisseurs)==1 and delta.fournisseurs[0].nom=='Dupont et Fils'


def test_plural_company_names_need_explicit_unambiguous_delimiters_or_count():
    delta=partners.literal_extract('Créer deux clients Atlas et Boréal.',{'articles':[]})
    assert len(delta.clients)==2


def test_update_without_index_cannot_create_duplicate():
    before=turn('Créer un fournisseur Atlas, pays MA.')
    after=chat.merge(before,Delta(intent='update',fournisseurs=[{'nom':'Atlas','devise':'MAD'}]),'Atlas : devise MAD')
    assert len(after['partners'])==1 and after['partners'][0]['devise']=='MAD'


def test_ungrounded_new_name_cannot_create_ghost():
    with pytest.raises(ValueError,match='partner_name_not_grounded'):
        chat.merge({'articles':[]},Delta(intent='new',clients=[{'nom':'Inventé'}]),'Créer un client Atlas')


def test_contact_values_not_grounded_in_other_field():
    before=turn('Créer un client Atlas, email contact@atlas.example.')
    after=chat.merge(before,Delta(intent='update',clients=[{'index':1,'code':'Atlas'}]),'Atlas : email nouveau@atlas.example')
    assert not after['partners'][0].get('code')
    assert after['rejected_values'][-1]['field']=='code'


def test_multi_kind_correction_is_ambiguous_without_target():
    first=turn('Créer un fournisseur Atlas.')
    both=turn('Créer un client Boréal.',first)
    assert partners.literal_extract('Email contact@example.test',both) is None


@pytest.mark.parametrize('kind',['supplier','customer'])
def test_validation_never_claims_creation_ready(kind,monkeypatch):
    state={'partners':[{'id':'p','kind':kind,'nom':'Atlas','code':'X12'}]}
    plan=chat_tools.Plan();bindings=partners.tool_plan(state,plan)
    results={c['id']:{'ok':True,'rows':[],'source':'CONTROLLED_FIXTURE'} for c in plan.calls}
    result=partners.validate(state,results,bindings)['partners'][0]['checks']
    assert result['valid_basic'] and not result['creation_ready'] and not result['sage_created']
    assert result['creation_blockers']


def test_partner_sql_failure_and_duplicate_reported_honestly():
    state={'partners':[{'id':'p','kind':'customer','nom':'Atlas','code':'X12'}]}
    plan=chat_tools.Plan();bindings=partners.tool_plan(state,plan)
    refs=bindings['p']
    results={refs['name']:{'ok':False,'rows':[]},refs['code']:{'ok':True,'rows':[{'BPCNUM_0':'X12'}]}}
    after=partners.validate(state,results,bindings)
    assert set(after['partners'][0]['checks']['errors'])=={'sql_checks_incomplete','duplicate_partner_code'}
    answer=partners.compose(after)
    assert 'indisponible' in answer and 'existe déjà' in answer


def test_partner_question_does_not_mutate_article_values():
    before=turn('Créer un fournisseur Atlas, pays MA.')
    after=chat.merge(before,Delta(intent='lookup'), 'Le fournisseur existe-t-il ?')
    assert after['partners']==before['partners']


def test_model_cannot_choose_partner_target_without_user_evidence():
    before=turn('Créer deux clients Atlas et Boréal.')
    after=chat.merge(before,Delta(intent='update',clients=[{'index':1,'email':'contact@example.test'}]),'Email contact@example.test')
    assert after['partners']==before['partners'] and after['turn_clarifications']


def test_supplier_association_cannot_create_supplier_master_implicitly():
    text='Créer un article Panneau, fournisseur Atlas.'
    result=chat.merge({'articles':[]},Delta(intent='new',articles=[{'designation':'Panneau'}],
                      fournisseurs=[{'nom':'Atlas'}]),text)
    assert len(result['articles'])==1 and not result['partners']
    assert result['turn_clarifications']
