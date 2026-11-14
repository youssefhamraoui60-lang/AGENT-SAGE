import pytest
from app.services import supplier_chat_flow,chat_multi_operations,conversation_chat as chat

MESSAGE='Bonjour,     Merci de créer le fournisseur : VM HOLZ TIMBER  et articles : madriers 3m  et madriers 4m.     Cdlt'

@pytest.mark.parametrize('message',[MESSAGE,MESSAGE.replace(' et articles :',' et les articles :'),MESSAGE.replace('  et articles :','\n et articles :')])
def test_supplier_and_each_article_have_separate_literal_names(message):
    parsed=supplier_chat_flow.extract(message,{'articles':[],'partners':[]})
    assert parsed
    delta,grounding=parsed
    assert delta.fournisseurs[0].nom=='VM HOLZ TIMBER'
    assert [a.designation for a in delta.articles]==['madriers 3m','madriers 4m']
    state=chat.merge({'articles':[],'partners':[]},delta,grounding)
    assert len(state['partners'])==1 and state['partners'][0]['nom']=='VM HOLZ TIMBER'
    assert [a['designation'] for a in state['articles']]==['madriers 3m','madriers 4m']
    assert all(not a.get('approved') for a in state['articles'])
    assert not state['partners'][0].get('approved')

def test_repeating_request_repairs_the_previous_malformed_uncreated_draft():
    original={'articles':[],'partners':[{'id':'keep-me','kind':'supplier','nom':'VM HOLZ TIMBER et articles : madriers 3m et madriers 4m','sources':{},'operation':{'status':'blocked'}}]}
    delta,ground=supplier_chat_flow.extract(MESSAGE,original)
    repaired=chat.merge(original,delta,ground)
    assert len(repaired['partners'])==1 and repaired['partners'][0]['id']=='keep-me'
    assert repaired['partners'][0]['nom']=='VM HOLZ TIMBER'
    assert len(repaired['articles'])==2
