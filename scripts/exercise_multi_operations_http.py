"""Exercise authenticated local analysis jobs only. Never calls a Sage write route."""
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from uuid import uuid4
import httpx

ROOT=Path(__file__).resolve().parents[1]


def main():
    tree=ast.parse((ROOT/'scripts/diagnose_multi_operations.py').read_text(encoding='utf-8'))
    text=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MULTILINE' for t in n.targets))
    report={'at':datetime.now(timezone.utc).isoformat(),'mode':'LOCAL_AUTHENTICATED_HTTP_ANALYSIS_JOBS_REAL_TEST_SELECT','sage_writes':0,'cases':[]}
    with httpx.Client(base_url='http://127.0.0.1:8000',headers={'Origin':'http://127.0.0.1:8000'},timeout=httpx.Timeout(connect=5,read=15,write=10,pool=5),trust_env=False) as client:
        def call(method,path,body=None):
            if method=='POST' and not (path=='/session' or path=='/conversations' or re.fullmatch(r'/conversations/[0-9a-f-]+/analysis-jobs',path)):
                raise RuntimeError('HTTP_WRITE_ROUTE_DENIED')
            response=client.request(method,'/api/v1/chat'+path,json=body)
            response.raise_for_status();return response
        auth=call('POST','/session').json();client.headers['X-Chat-CSRF']=auth['csrf']
        twenty='Créer un fournisseur AHMNDE, forme juridique SARL AU, capital 100 000 DH ; créer les 20 articles suivants, unité UN :\n'+'\n'.join(f'{i}. Expo mobilité {i}, site {"201" if i%2 else "202"}' for i in range(1,21))
        for label,message,count in [('exact_ahmnde',text,1),('one_supplier_twenty_articles',twenty,20)]:
            session=call('POST','/conversations').json();request_id=str(uuid4());start=time.perf_counter()
            accepted=call('POST','/conversations/'+session['id']+'/analysis-jobs',{'content':message,'revision':session['revision'],'request_id':request_id})
            accepted_ms=round((time.perf_counter()-start)*1000,3);assert accepted.status_code==202
            value=accepted.json();job_id=value['job']['id'];statuses=[value['job']['status']]
            while value['job']['status'] not in ('completed','failed','interrupted','verification_incomplete'):
                if time.perf_counter()-start>60:raise RuntimeError('Read-only analysis did not finish in observation window; no resubmission')
                time.sleep(0.2);value=call('GET','/conversations/'+session['id']+'/analysis-jobs/'+job_id).json();statuses.append(value['job']['status'])
            assert value['job']['status']=='completed',value['job'].get('error_type')
            state=value['conversation']['state'];assert len(state['articles'])==count and len(state['partners'])==1
            assert all(a['unite']=='UN' and a['fournisseur_nom']=='AHMNDE' and not a['categorie'] and not a['code_tva'] and not a['code_fournisseur'] for a in state['articles'])
            if count==1:
                p=state['partners'][0];a=state['articles'][0]
                assert p['ice']=='002033808000048' and p['rc']=='129251' and p['ville_rc']=='Rabat'
                assert p['forme_juridique']=='SARL AU' and p['capital']=='100 000 DH' and p['annee_creation']=='2018'
                assert a['designation']=='Africa EV Mobility Expo' and a['site']=='202' and a['gestion_stock']=='1' and a['taux_tva']=='10'
            else:assert [a['site'] for a in state['articles']]==['201' if i%2 else '202' for i in range(1,21)]
            assert sum(m['content']==message for m in value['conversation']['messages'])==1
            # Repeating exactly the same HTTP request ID returns the same job.
            repeated=call('POST','/conversations/'+session['id']+'/analysis-jobs',{'content':message,'revision':session['revision'],'request_id':request_id}).json()
            assert repeated['job']['id']==job_id and len(repeated['conversation']['state']['articles'])==count
            report['cases'].append({'label':label,'request_sha256':hashlib.sha256(message.encode()).hexdigest(),'conversation_id':session['id'],
                'job_id':job_id,'accepted_http_status':accepted.status_code,'acceptance_ms':accepted_ms,'observed_statuses':statuses,
                'observation_total_ms':round((time.perf_counter()-start)*1000,3),'performance':value['job'].get('performance'),
                'article_count':count,'supplier_count':1,'idempotent_replay':True,'state':state,'assertions_passed':True})
    target=ROOT/'tests/ai-evaluation/reports/timeout-multi-http-live.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(target),'passed':True,'cases':[{k:v for k,v in c.items() if k not in ('state',)} for c in report['cases']]},ensure_ascii=True))


if __name__=='__main__':main()
