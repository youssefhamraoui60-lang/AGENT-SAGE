"""Behavioral regressions for natural corrections, never using ERP connections."""
from copy import deepcopy
import pytest
from app.services import conversation_chat as chat, chat_fast_extract as fast, chat_turns
from app.services.chat_model import Delta


def state():
    return {'articles': [dict(id=str(i), designation=f'Panneau {i}', code_article=f'PAN-{i}',
                             categorie='AR', unite='UN', site='201', sources={}, proposals={})
                         for i in (1, 2)], 'pending': [], 'asked': []}


@pytest.mark.parametrize('text', ['Change la catégorie NEG. Le site existe-t-il ?',
                                'Change la catégorie NEG ; quelles unités existent ?',
                                'Peux-tu changer la catégorie en NEG ?'])
def test_explicit_correction_survives_question(text):
    after = chat.merge(state(), Delta(intent='update', shared={'categorie':'NEG'}), text)
    assert [a['categorie'] for a in after['articles']] == ['NEG', 'NEG']


@pytest.mark.parametrize('text', ['la catigorer NEG', 'la catigorie NEG', 'catégorie NEG'])
def test_category_spelling(text):
    turn = chat_turns.analyse(text, state())
    assert turn.values.get('categorie') == 'NEG'


def test_first_message_can_explicitly_omit_supplier():
    text = 'Créer un article Panneau, catégorie NEG, unité M2, sans fournisseur, site 202.'
    after = chat.merge({'articles':[]}, Delta(intent='new', articles=[{'designation':'Panneau'}],
                       shared={'categorie':'NEG','unite':'M2','site':'202'}), text)
    assert after['articles'][0].get('supplier_intent') == 'none'


def test_distinct_article_sites_are_not_overwritten_by_first_site():
    text = 'Créer deux articles : Panneau A site 201 et Panneau B site 202.'
    delta = Delta(intent='new', articles=[{'designation':'Panneau A','site':'201'},
                                         {'designation':'Panneau B','site':'202'}])
    after = chat.merge({'articles':[]}, delta, text)
    assert [a['site'] for a in after['articles']] == ['201','202']


def test_code_replacement_retains_other_values():
    before = state()
    text = 'Remplacer - par _ dans les codes articles.'
    after = chat.merge(before, Delta(intent='generate'), text)
    assert [a['code_article'] for a in after['articles']] == ['PAN_1','PAN_2']
    assert [a['categorie'] for a in after['articles']] == ['AR','AR']
    assert before == state()


def test_question_is_not_repeated_when_state_has_not_changed():
    value = state()
    for a in value['articles']: a['site'] = None
    first = chat.compose(value)
    second = chat.compose(value)
    assert 'Sur quel site' in first
    assert 'Sur quel site' not in second


def test_optional_supplier_is_not_an_instruction_to_remove_existing_supplier():
    before = state()
    for a in before['articles']: a.update(code_fournisseur='F12', fournisseur_nom='Existant')
    after = chat.merge(before, Delta(intent='update'), 'Le forniseur pas obliger')
    assert all(a['code_fournisseur']=='F12' for a in after['articles'])
    assert after.get('supplier_requirement') == 'optional'


def test_explicit_multi_article_abbreviation_is_grounded_without_guessing():
    text = 'Créer deux articles Panneaux A et B XPS 4 CM, catégorie NEG, unité M2, sans fournisseur, site 202.'
    delta = Delta(intent='new', articles=[{'designation':'Panneaux A XPS 4 CM'},
                                         {'designation':'Panneaux B XPS 4 CM'}])
    after = chat.merge({'articles':[]}, delta, text)
    assert len(after['articles']) == 2
    assert all(a.get('supplier_intent')=='none' for a in after['articles'])


def test_product_designation_is_not_a_lookup_command():
    text='Créer un article TEST ARTICLE CONTROLE, catégorie NEG, unité UN, site 201.'
    delta,proof=fast.extract(text,{'articles':[]})
    after=chat.merge({'articles':[]},delta,text)
    assert len(after['articles'])==1 and after['articles'][0]['designation']=='TEST ARTICLE CONTROLE'


def test_separate_corrections_keep_each_article_target():
    before=state()
    text='Pour le premier article : site 202 ; pour le deuxième article : site 209.'
    delta=Delta(intent='update',articles=[{'index':1,'site':'202'},{'index':2,'site':'209'}])
    result=chat.merge(before,delta,text)
    assert [a['site'] for a in result['articles']]==['202','209']


def test_conversation_convention_applies_to_later_new_articles():
    first=chat.merge(state(),Delta(intent='generate'),'Remplacer - par _ dans les codes articles.')
    second=chat.merge(first,Delta(intent='new',articles=[{'designation':'Autre panneau'}]),'Créer un article Autre panneau')
    assert second['articles'][-1]['code_article']=='AUTRE_PANNEAU'


def test_reviewed_experience_is_filtered_and_redacted():
    from app.services import chat_experiences as experiences
    value=state();a=value['articles'][0]
    example=experiences.snapshot(a,value,chat.FIELDS,'qwen2.5:7b')
    assert example['_experience']['validated_by_human'] and not example['_experience']['training_performed']
    assert experiences.relevant('Panneau', [{'snapshot':example}])
    assert not experiences.relevant('Complètement différent fournisseur', [{'snapshot':example}])
    assert 'abc123' not in str(experiences.safe({'nom':'password=abc123','token':'abc123'}))


def test_change_code_without_value_gets_targeted_clarification():
    before=state();after=chat.merge(before,Delta(intent='update'),'Change le code')
    assert after['articles']==before['articles']
    assert 'nouveau code' in after['turn_clarifications'][0]


def test_prompt_memory_is_bounded_without_deleting_persisted_history():
    import json
    from app.services.chat_semantics import memory_context
    value=state();value['correction_history']=[{'changes':[{'article_id':str(j),'field':'site','before':'201','after':str(i)} for j in range(10)]} for i in range(100)]
    before=deepcopy(value)
    context=memory_context(value)
    assert len(context['recent_corrections'])<=12
    assert len(json.dumps(context))<5000
    assert value==before and len(value['correction_history'])==100


def test_duplicate_codes_in_same_batch_block_both_drafts():
    from app.services import chat_tools
    from test_conversation_chat import FakeSQL
    before=state()
    for a in before['articles']:a['code_article']='TEST_IDENTIQUE'
    plan,bindings=chat.tool_plan(before)
    after=chat.prepare_article_draft(before,FakeSQL()(plan.calls),bindings)
    assert all('duplicate_code_in_drafts' in a['checks']['errors'] and not a['checks']['valid_basic'] for a in after['articles'])
    assert any(q['field']=='code_article' for q in chat.questions(after))
