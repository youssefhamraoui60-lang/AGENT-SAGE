from app.services.article_agent import Draft, preparation


def test_article_draft_prepares_active_status_without_sending_soap():
    request = preparation(Draft(code_article='TESTAGENT004',
        designation='ARTICLE TEST CREATION AGENT IA', categorie='NEG', unite='UN'))
    assert request.keys == {'ITMREF': 'TESTAGENT004'}
    assert [(f.group, f.value) for f in request.fields if f.name == 'ITMSTA'] == [('ITM0_1', '1')]
    assert {f.name: f.value for f in request.fields if f.name in ('STU', 'PUU', 'SAU')} == {
        'STU': 'UN', 'PUU': 'UN', 'SAU': 'UN'}


def test_explicit_article_code_is_preserved_without_model_guess():
    from app.services.conversation_chat import explicit_overrides
    from app.services.chat_model import Delta
    result = explicit_overrides('Je veux creer un article avec le code TESTAGENT004, categorie NEG.',
                                {'articles': []}, Delta(intent='new'))
    assert result['code_article'] == 'TESTAGENT004'
