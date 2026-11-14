"""Replay the two reported dialogues as drafts; never approve a Sage operation."""
import json
from pathlib import Path
import httpx
from http_test_account import authenticate_test_client

base='http://127.0.0.1:8000'
cases=[('CAF G56 L',[
    'je veux créer un article',
    'le nom de articles est CAF G56 L dans la catiégorier negos',
    'Négoce',"c'est le negose",'NEG','la catigorier est NEG','un','le uniter est UN',
]),('CAF56 HY',[
    'je veux créer un articles',
    'le articne est CAF56 HY dasn le site 202 ET son catigorier est NEGOSE',
]),('CAF 798K',[
    'je veux créer un articele',
    'le nom de l"articles est CAF 798K dans la catigorier negose',
    'le nom de article est CAF 798K',
    'et la catigorier negose',
]),('CAF HT78 3',[
    'JE VEUX CR2ER UN ARTICLMES CAF HT78 3',
    'le nom compléte est CAF HT78 3',
    'la catigorer est NEGOSE',
    'crer les artice',
    'crée le articles',
    'CAF HT78',
    'negose',
    '4415',
])]
reports=[]
with httpx.Client(base_url=base,headers={'Origin':base},timeout=90,trust_env=False) as client:
    account=authenticate_test_client(client)
    client.headers['X-Chat-CSRF']=account['csrf']
    for name,messages in cases:
        response=client.post('/api/v1/chat/conversations');response.raise_for_status();session=response.json()
        for text in messages:
            response=client.post('/api/v1/chat/conversations/'+session['id']+'/messages',json={'content':text,'revision':session['revision']})
            response.raise_for_status();session=response.json()
            assert 'services IA' not in session['messages'][-1]['content']
        articles=session['state']['articles']
        assert len(articles)==1 and articles[0]['designation']==name
        article=articles[0]
        assert article['categorie']=='NEG' and not article.get('approved')
        if name=='CAF G56 L':assert article['unite']=='UN'
        elif name=='CAF56 HY':assert article['site']=='202'
        elif name=='CAF HT78 3':assert article['compte_general']=='4415'
        reports.append({'name':name,'conversation_id':session['id'],'category':article['categorie'],'unit':article.get('unite'),'site':article.get('site'),'reply':session['messages'][-1]['content']})
        print(json.dumps(reports[-1],ensure_ascii=True),flush=True)
Path(__file__).with_name('caf-dialogues-live-results.json').write_text(json.dumps({'status':'PASS','sage_writes':0,'cases':reports},ensure_ascii=False,indent=2),encoding='utf-8')
