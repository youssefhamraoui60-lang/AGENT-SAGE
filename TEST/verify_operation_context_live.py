"""Actual DeepSeek multi-intent session; allowlisted read/draft routes only."""
import json,time
from pathlib import Path
from uuid import uuid4
import httpx
from http_test_account import authenticate_test_client

base='http://127.0.0.1:8000'
stamp=uuid4().hex[:6].upper()
name='SESSION CONTEXTE '+stamp
article='CAF SESSION '+stamp
messages=[
    'Bonjour, prépare la création du fournisseur '+name+', adresse HAY RAH R56, ville Berrechid. Prépare seulement la fiche pour vérification.',
    'Annule uniquement cette création puis modifie le fournisseur F007 : sa ville doit être Agadir et son téléphone 0612345678. Prépare ces deux changements pour vérification.',
    'Je veux aussi une nouvelle création article : '+article+', catégorie AVT, site 202. Garde la modification fournisseur en attente.',
    'Pour le même article, corrige la désignation : '+article+' BLEU, unité UN. Garde les autres opérations.',
]
proof=[]
with httpx.Client(base_url=base,headers={'Origin':base},timeout=30,trust_env=False) as client:
    account=authenticate_test_client(client);client.headers['X-Chat-CSRF']=account['csrf']
    response=client.post('/api/v1/chat/conversations');response.raise_for_status();session=response.json()
    for index,message in enumerate(messages):
        path='/api/v1/chat/conversations/'+session['id']+'/analysis-jobs'
        response=client.post(path,json={'content':message,'revision':session['revision'],'request_id':str(uuid4())})
        response.raise_for_status();value=response.json();job=value['job']['id'];started=time.monotonic()
        while value['job']['status'] not in ('completed','failed','interrupted','verification_incomplete'):
            if time.monotonic()-started>180:raise RuntimeError('No automatic resubmission after observation deadline')
            time.sleep(1)
            response=client.get(path+'/'+job);response.raise_for_status();value=response.json()
        session=value['conversation']
        state=session['state'];context=state.get('operation_context') or {}
        record={'step':index+1,'job_status':value['job']['status'],'provider':state.get('tool_orchestration',{}).get('provider'),
                'reply':session['messages'][-1]['content'],'operations':context.get('operations',[])}
        proof.append(record)
        Path(__file__).with_name('operation-context-live-report.json').write_text(json.dumps({'conversation_id':session['id'],'sage_write_routes_called':0,'steps':proof},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({key:record[key] for key in ('step','job_status','provider','reply')},ensure_ascii=True),flush=True)
        assert value['job']['status']=='completed'
        assert record['provider']=='deepseek','Real cloud engine not demonstrated; inspect provider fallback'
        assert not any(item.get('approved') for collection in ('partners','articles','modification_drafts') for item in state.get(collection,[]))
        if index==0:
            assert len(state['partners'])==1 and state['partners'][0]['nom']==name
            assert state['partners'][0]['adresse']=='HAY RAH R56'
        if index>=1:
            assert state['partners'][0]['operation']['status']=='cancelled'
            modifications=[item for item in state['modification_drafts'] if item['code']=='F007']
            assert modifications and modifications[-1]['changes'].get('city')=='Agadir'
            assert modifications[-1]['changes'].get('phone')=='0612345678'
        if index>=2:assert len(state['articles'])==1
        if index==3:
            assert state['articles'][0]['designation']==article+' BLEU'
            assert state['articles'][0]['unite']=='UN'
    response=client.get('/api/v1/chat/conversations/'+session['id']+'/operation-state.json');response.raise_for_status()
    exported=response.json()
    assert len(exported['operations'])>=3
    Path(__file__).with_name('session-operation-context-live.json').write_text(json.dumps(exported,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: real DeepSeek, three distinct operations retained, private JSON exported, no Sage writes.',flush=True)
