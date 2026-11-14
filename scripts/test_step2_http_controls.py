"""Real localhost HTTP validation, correction, denial and rejection using synthetic requests."""
import json
import httpx
import native_stack as stack

ROOT=stack.ROOT
rows=json.loads((ROOT/'logs/step2-live-v1-results.json').read_text(encoding='utf-8'))
identifier=next(row['response']['id'] for row in rows if row['case']=='single')
headers={'X-Approval-Token':stack.environment()['APPROVAL_TOKEN']}
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=20) as client:
    original=client.get('/api/v1/ai/requests/'+identifier);original.raise_for_status();before=original.json()
    response=client.post('/api/v1/ai/validate',json={'proposition':before['proposition']});response.raise_for_status()
    assert response.json()['business_valid'] is False
    response=client.post('/api/v1/ai/check-duplicates',json={'designation':'Cosse à sertir SC 70-10'})
    response.raise_for_status()
    base='/api/v1/ai/requests/'+identifier
    patch={'revision_attendue':before['revision'],'acteur':'test-http-local','raison':'Correction synthétique de vérification HTTP','articles':[{'index':0,'champs':{'unite':'UN'}}]}
    assert client.post(base+'/corrections',json=patch).status_code==403
    response=client.post(base+'/corrections',json=patch,headers=headers);response.raise_for_status();corrected=response.json()
    assert corrected['extraction_initiale']==before['extraction_initiale']
    assert corrected['proposition']['articles'][0]['unite']=='UN'
    decision={'revision_attendue':corrected['revision'],'acteur':'test-http-local','raison':'Vérification refus approbation sans règles validées','decision':'approve'}
    assert client.post(base+'/decision',json=decision,headers=headers).status_code==409
    decision.update(decision='reject',raison='Clôture du dossier synthétique de test HTTP')
    response=client.post(base+'/decision',json=decision,headers=headers);response.raise_for_status();after=response.json()
    assert after['statut']=='rejected' and not after['execution_sage_autorisee']
    assert len(after['historique'])==len(before['historique'])+2
proof={'status':'PASS','request_id':identifier,'checks':6,'real_http':True,'correction_retained':True,'initial_extraction_preserved':True,'approval_without_validated_rules':409,'missing_token':403,'final_status':'rejected','sage_execution':False}
(ROOT/'logs/step2-http-controls.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
print(json.dumps(proof,indent=2))
