from test_native_conversation_tools import native_chat,campaign,fixture,simulated,call,native,say,send,fact

def test_power_article_request_in_ob_reaches_article_preparation(native_chat):
    c,q,_,_,attempts,_=native_chat
    s=c.post('/api/v1/chat/conversations',json={'discussion_mode':'ob'}).json()
    text='Merci de créer l’article " POWER DUR OB  25Kg ECO " La commande est déjà créée en attendant de la création de l’article.'
    q.extend([native(call('prepare_draft',resource='article',mode='new',fields=[fact('designation','POWER DUR OB  25Kg ECO')])),say('La désignation est conservée dans OB. Quelle catégorie retenir ?')])
    s=send(c,s,text)
    assert s['folder']=='OB' and s['state']['discussion_mode']=='general'
    a=s['state']['articles'][0]
    assert a['designation']=='POWER DUR OB  25Kg ECO' and a['dossier_cible']=='OB'
    assert s['state']['tool_orchestration']['calls'][0]['result']['ok']
    assert all(not a['execute'] for a in attempts)
