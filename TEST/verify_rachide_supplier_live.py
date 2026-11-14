"""Exact supplier conversation, drafts only in each explicitly selected folder."""
import json
from pathlib import Path
import httpx
from http_test_account import authenticate_test_client

base='http://127.0.0.1:8000'
reports=[]
with httpx.Client(base_url=base,headers={'Origin':base},timeout=120,trust_env=False) as client:
    account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf']
    for mode,folder in [('general','TEST'),('supplier_ob','OB')]:
        response=client.post('/api/v1/chat/conversations',json={'discussion_mode':mode});response.raise_for_status();s=response.json()
        for text in ['créer le founisseur rachide IT','le addrise est HAY RAH BERRCHIDE R56']:
            response=client.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']})
            response.raise_for_status();s=response.json()
            assert 'services IA' not in s['messages'][-1]['content']
        p=s['state']['partners'][0]
        assert len(s['state']['partners'])==1 and not s['state'].get('articles')
        assert p['nom']=='rachide IT' and p.get('dossier_cible','TEST')==folder and not p.get('approved')
        assert p['operation']['status'] in ('prepared','blocked')
        assert p['adresse']=='HAY RAH BERRCHIDE R56'
        assert not p.get('ville')
        report={'folder':folder,'name':p['nom'],'status':p['operation']['status'],'reply':s['messages'][-1]['content'],'conversation_id':s['id']}
        reports.append(report);print(json.dumps(report,ensure_ascii=True),flush=True)
Path(__file__).with_name('rachide-supplier-live-results.json').write_text(json.dumps({'status':'PASS','sage_writes':0,'cases':reports},ensure_ascii=False,indent=2),encoding='utf-8')
