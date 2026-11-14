"""Real FastAPI reads/preparations and locked-endpoint checks. NEVER authorizes or sends a Sage write."""
import json,secrets,time
from pathlib import Path
from uuid import uuid4
import httpx
import native_stack as stack
ROOT=stack.ROOT
for _ in range(30):
    try:
        if httpx.get('http://127.0.0.1:8000/health',timeout=2).is_success:break
    except httpx.HTTPError:pass
    time.sleep(.5)
plan_file=ROOT/'runtime/crud-live-plan.json'
if plan_file.exists():plan=json.loads(plan_file.read_text(encoding='utf-8'))
else:
    suffix=secrets.token_hex(2).upper()
    plan={'article':'TAI261017'+suffix,'supplier':'TB261017'+suffix}
    plan_file.write_text(json.dumps(plan,indent=2),encoding='utf-8')
out={'mode':'REAL_READS_AND_PREPARATION_ONLY','resources':{},'real_api_creations':0,'real_api_updates':0,'approvals_granted':0}
with httpx.Client(base_url='http://127.0.0.1:8000',headers={'X-Approval-Token':stack.environment()['APPROVAL_TOKEN']},timeout=90,trust_env=False) as client:
    out['security']=client.get('/api/v1/sage/security').json();assert not out['security']['ready']
    observed={}
    for resource,keys in [('articles',['ITMREF']),('suppliers',['BPSNUM']),('article-sites',['ITMREF','STOFCY'])]:
        schema=client.get('/api/v1/sage/'+resource+'/schema');schema.raise_for_status()
        listed=client.get('/api/v1/sage/'+resource+'?limit=3');listed.raise_for_status();rows=listed.json()['records'];assert rows
        selected={key:rows[0][key] for key in keys}
        read=client.get('/api/v1/sage/'+resource+'/'+'/'.join(selected[k] for k in keys));read.raise_for_status()
        record=read.json()['record'];assert record['exists']
        observed[resource]=record
        out['resources'][resource]={'publication':schema.json()['publication'],'list_http':listed.status_code,'read_http':read.status_code,'sample_keys':selected,'record':record,'schema_fields':len(schema.json()['fields'])}
    plan['site']=out['resources']['article-sites']['sample_keys']['STOFCY']
    plan_file.write_text(json.dumps(plan,indent=2),encoding='utf-8')
    article_fields=[{'group':'ITM0_1','name':'TCLCOD','value':'NEG'},{'group':'ITM0_1','name':'DES1AXX','value':'TEST API ITM - AUCUN ENVOI'},
        {'group':'ITM0_1','name':'ITMSTA','value':'1'},{'group':'ITM2_1','name':'STOMGTCOD','value':'2'},{'group':'ITM2_3','name':'LOTMGTCOD','value':'3'},
        *[{'group':'ITM3_1','name':key,'value':value} for key,value in [('STU','SAC'),('PUU','SAC'),('PUUSTUCOE','1'),('SAU','SAC'),('SAUSTUCOE','1')]],
        {'group':'ITM5_1','name':'ACCCOD','value':'CPJ35'}]
    supplier_fields=[{'group':'BPRS_1','name':'BPRNAM','value':['FOURNISSEUR FICTIF TEST API','']},{'group':'BPRS_1','name':'BPRSHO','value':'TESTAPI'}]
    for group,name in [('BPS0_1','BSGCOD'),('BPRS_1','CRY')]:
        value=observed['suppliers']['fields'].get(group+'.'+name)
        if value:supplier_fields.append({'group':group,'name':name,'value':value})
    abc=observed['article-sites']['fields'].get('ITF1_2.ABCCLS')
    assert abc is not None
    site_fields=[{'group':'ITF1_2','name':'ABCCLS','value':abc}]
    requests={
        'articles':({'ITMREF':plan['article']},article_fields,[{'group':'ITM0_1','name':'DES1AXX','value':'TEST API ITM - MODIFICATION'}]),
        'suppliers':({'BPSNUM':plan['supplier']},supplier_fields,[{'group':'BPRS_1','name':'BPRSHO','value':'TSTAPIMOD'}]),
        'article-sites':({'ITMREF':plan['article'],'STOFCY':plan['site']},site_fields,[{'group':'ITF1_2','name':'ABCCLS','value':'2' if abc!='2' else '1'}])}
    for resource,(keys,fields,updates) in requests.items():
        for action,changes in [('create',fields),('update',updates)]:
            payload={'action':action,'keys':keys,'fields':changes}
            response=client.post('/api/v1/sage/'+resource+'/prepare',json=payload);response.raise_for_status();operation=response.json()
            assert operation['before_record']['exists'] is False
            out['resources'][resource][action+'_preparation']={'http':response.status_code,'request':payload,'operation':operation}
            # A negative check is not a grant of approval. No operation-specific consent is recorded.
            denied=client.post('/api/v1/sage/operations/'+operation['id']+'/approve',json={'digest':operation['digest'],'confirm':False,'actor':'NO APPROVAL','reason':'Negative security test only'})
            assert denied.status_code==423
            suffix='/'+'/'.join(keys[k] for k in (['ITMREF','STOFCY'] if resource=='article-sites' else list(keys))) if action=='update' else ''
            blocked=getattr(client,'patch' if action=='update' else 'post')('/api/v1/sage/'+resource+suffix,json={'operation_id':operation['id'],'approval_token':'NO_AUTHORIZATION'})
            assert blocked.status_code==423
            out['resources'][resource][action+'_blocked_http']=blocked.status_code
        assert client.get('/api/v1/sage/'+resource+'/history').status_code==200
    out['status']='PASS'
(ROOT/'logs/step4-crud-live-tests.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'PASS','publications_read':3,'real_reads':3,'prepared_operations':6,'write_routes_blocked':6,'approvals_granted':0,'sage_creations':0,'sage_updates':0,'plan':plan},ensure_ascii=False,indent=2))
