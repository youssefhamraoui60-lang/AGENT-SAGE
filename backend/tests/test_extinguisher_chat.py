from app.services import chat_fast_extract,conversation_chat as chat,chat_turns
TEXT='Bonjour youssef, Merci de créer ces nouveaux articles :\nExtincteur à poudre / unite / FG/ CHAOUIA PROTECT/ARTICLE NON GERER\nExtincteur à CO2 / Unite/ FG/ CHAOUIA PROTECT/ ARTICLE NON GERER\nCordialement'

def test_slash_request_fields_and_proposals():
    delta,meta=chat_fast_extract.extract(TEXT,{})
    assert meta['route']=='literal_slash_articles'
    state=chat.merge({'articles':[]},delta,TEXT)
    assert len(state['articles'])==2
    for a,code in zip(state['articles'],['EXT_POUDRE','EXT_CO2']):
        assert a['categorie']=='FG' and a['unite']=='UN' and a['gestion_stock']=='1'
        assert a['fournisseur_nom']=='CHAOUIA PROTECT' and a['code_article']==code
        assert not a.get('site') and not a.get('approved')
    output=chat.compose(state,new=True)
    assert '| Code proposé |' in output and '| FG | UN | CHAOUIA PROTECT | Non géré |' in output

def test_inline_request_and_readonly_followups():
    message=TEXT.replace('\n',' ');delta,_=chat_fast_extract.extract(message,{})
    state=chat.merge({'articles':[]},delta,message)
    assert len(state['articles'])==2
    for text in ['le code articles','lister le']:
        assert chat_turns.analyse(text,state).readonly
        lookup,_=chat_fast_extract.extract(text,state)
        assert chat.merge(state,lookup,text)['articles']==state['articles']

def test_unrecognized_tail_not_silently_dropped():
    from app.services.chat_slash_extract import parse
    assert parse(TEXT+' Ajouter aussi une instruction inconnue') is None
