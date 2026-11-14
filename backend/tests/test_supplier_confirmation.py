from copy import deepcopy
import pytest
from app.services import chat_turns,conversation_chat as chat
from app.services.chat_model import Delta


def test_supplier_yes_only_updates_drafts_with_the_confirmed_proposal():
    before={'articles':[
        {'id':'1','designation':'Article A','code_article':'A','fournisseur_nom':'Atlas','code_fournisseur':None,'proposals':{'code_fournisseur':'F12'},'sources':{}},
        {'id':'2','designation':'Article B','code_article':'B','fournisseur_nom':None,'code_fournisseur':None,'supplier_intent':'none','proposals':{},'sources':{}},
        {'id':'3','designation':'Article C','code_article':'C','fournisseur_nom':'Boréal','code_fournisseur':None,'proposals':{},'sources':{}}],
        'pending':[{'field':'code_fournisseur','text':'Confirmer Atlas F12 ?'}]}
    after=chat.merge(before,Delta(intent='update'),'oui')
    assert [a.get('code_fournisseur') for a in after['articles']]==['F12',None,None]
    assert after['articles'][1]['supplier_intent']=='none'


def state():
    return {'articles':[{'id':'synthetic','designation':'Extincteur à poudre','code_article':'EXT_POUDRE',
        'categorie':'NEG','unite':'UN','site':'201','fournisseur_nom':'CHAOUIA PROTECT',
        'gestion_stock':'1','code_fournisseur':None,'sources':{'site':'user_declared'},
        'proposals':{'code_fournisseur':'F1025'}}],
        'pending':[{'field':'code_fournisseur','text':'F1025 ?'}]}


@pytest.mark.parametrize('text',['OUI','OUI LE F1025','oui F1025','OUI je confirme','OUI je confiremer'])
def test_persisted_supplier_offer_is_confirmed_without_model_guess(text):
    value=state()
    result=chat.merge(value,Delta(intent='update'),text)
    a=result['articles'][0]
    assert a['code_fournisseur']=='F1025'
    assert a['site']=='201' and a['categorie']=='NEG' and a['gestion_stock']=='1'
    assert a['sources']['code_fournisseur']=='user_declared'
    assert not any(q['field']=='code_fournisseur' for q in chat.questions(result))
    assert not a.get('approved') and not a.get('operation')


@pytest.mark.parametrize('text',['OUI NEG','OUI LE F9999','NON','Est-ce le fournisseur F1025 ?'])
def test_other_answers_do_not_accept_supplier_offer(text):
    assert 'code_fournisseur' not in chat_turns.analyse(text,state()).values


def test_yes_without_pending_offer_never_guesses_supplier():
    value=state();value['pending']=[]
    assert 'code_fournisseur' not in chat_turns.analyse('OUI',value).values


def test_site_and_misspelled_supplier_declaration_are_both_preserved():
    turn=chat_turns.analyse('le site 201 et le fournsieur est F1025',state())
    assert turn.values=={'site':'201','code_fournisseur':'F1025'}


def test_yes_with_different_supplier_candidates_is_ambiguous():
    value=state();second=deepcopy(value['articles'][0]);second['id']='second'
    second['proposals']['code_fournisseur']='F234';value['articles'].append(second)
    assert 'code_fournisseur' not in chat_turns.analyse('OUI',value).values


def test_unresolved_question_is_not_silently_hidden_forever():
    value=state()
    for a in value['articles']:a['checks']={'errors':['supplier_confirmation_required']}
    chat.compose(value)
    assert 'Pour continuer' in chat.compose(value)


def test_write_limitations_are_reported_without_removing_fields():
    from app.services.sage_powershell_chat import creation_blockers
    a=state()['articles'][0]
    assert set(creation_blockers(a))=={'test_article_code_required','supplier_write_mapping_not_supported','stock_write_mapping_not_supported'}
    assert a['code_article']=='EXT_POUDRE' and a['gestion_stock']=='1'
