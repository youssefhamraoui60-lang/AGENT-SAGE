"""Real draft-only fiscal clarification in TEST and OB; no write routes."""
import json
from pathlib import Path
import httpx
from http_test_account import authenticate_test_client

base='http://127.0.0.1:8000';reports=[]
with httpx.Client(base_url=base,headers={'Origin':base},timeout=120,trust_env=False) as client:
    account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf']
    for mode,folder in [('general','TEST'),('supplier_ob','OB')]:
        response=client.post('/api/v1/chat/conversations',json={'discussion_mode':mode});response.raise_for_status();s=response.json()
        identifier=None
        for message in ['bonjour je veux créer un fournisseur rachide H','CETTE FOURNIISEUR AVCE LE ICE 12343234565456']:
            response=client.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':message,'revision':s['revision']})
            response.raise_for_status();s=response.json()
            assert 'services IA' not in s['messages'][-1]['content']
            assert len(s['state']['partners'])==1
            p=s['state']['partners'][0]
            if identifier is not None:assert p['id']==identifier
            identifier=p['id']
        assert p['nom']=='rachide H' and p.get('dossier_cible','TEST')==folder
        assert p['ice']=='12343234565456' and not p.get('approved')
        assert p['operation']['status']=='blocked'
        assert '14 chiffres' in s['messages'][-1]['content'] and '15' in s['messages'][-1]['content']
        report={'folder':folder,'conversation_id':s['id'],'name':p['nom'],'ice':p['ice'],'reply':s['messages'][-1]['content']}
        response=client.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':'012343234565456','revision':s['revision']})
        response.raise_for_status();corrected=response.json()
        corrected_partner=corrected['state']['partners'][0]
        assert corrected_partner['id']==identifier and corrected_partner['ice']=='012343234565456'
        assert not corrected_partner.get('approved')
        assert 'services IA' not in corrected['messages'][-1]['content']
        report['bare_number_correction_accepted']=True
        reports.append(report);print(json.dumps(report,ensure_ascii=True),flush=True)
Path(__file__).with_name('supplier-ice-sentence-live-results.json').write_text(json.dumps({'status':'PASS','sage_writes':0,'cases':reports},ensure_ascii=False,indent=2),encoding='utf-8')
