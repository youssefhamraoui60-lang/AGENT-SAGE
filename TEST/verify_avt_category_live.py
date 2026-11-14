"""Exact AVT category selection over real HTTP, no approval or execution."""
import json
from pathlib import Path
import httpx
from http_test_account import authenticate_test_client

base='http://127.0.0.1:8000'
with httpx.Client(base_url=base,headers={'Origin':base},timeout=120,trust_env=False) as client:
    account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf']
    response=client.post('/api/v1/chat/conversations');response.raise_for_status();session=response.json()
    identifier=None
    for message in ["bonjour créer l'articles CAF 77H",'AVT']:
        response=client.post('/api/v1/chat/conversations/'+session['id']+'/messages',json={'content':message,'revision':session['revision']})
        response.raise_for_status();session=response.json()
        assert len(session['state']['articles'])==1
        article=session['state']['articles'][0]
        if identifier is not None:assert article['id']==identifier
        identifier=article['id']
        assert article['designation']=='CAF 77H' and not article.get('approved')
        assert 'services IA' not in session['messages'][-1]['content']
    assert article['categorie']=='AVT'
    report={'status':'PASS','conversation_id':session['id'],'designation':article['designation'],'category':article['categorie'],'reply':session['messages'][-1]['content'],'sage_writes':0}
    Path(__file__).with_name('avt-category-live-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))
