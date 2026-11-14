"""Re-test completed controlled probes after fixes. No blind INSERT retries."""
import concurrent.futures,json,os,time
from pathlib import Path
from run_100_article_sessions import Client,controlled_writes,save,OUT
from app.services import erp_modification as sql

RUN='b26e71c4'

def retry(source):
    identifier=source['id'];original=OUT/RUN/identifier
    out=OUT/(RUN+'-write-retests')/identifier
    if (out/'real-writes.json').exists():return json.loads((out/'real-writes.json').read_text(encoding='utf-8'))
    prior=json.loads((original/'real-writes.json').read_text(encoding='utf-8')) if (original/'real-writes.json').exists() else {}
    if prior.get('status')=='verified':return prior
    code='CX'+RUN[:6].upper()+identifier[-3:];name='CXTEST '+RUN[:6].upper()+' '+identifier[-3:]
    client=Client('http://127.0.0.1:8000',RUN+'retry',int(identifier[-3:]))
    try:
        view=sql.snapshot('article',code)
        if not view.get('articles'):
            if prior.get('status') in ('creation_attempted','modification_attempted','creation_unconfirmed') or source.get('real_writes',{}).get('status')=='stopped_no_retry':
                result={'code':code,'status':'needs_manual_reconciliation','reason':'An unconfirmed attempt exists; no INSERT retry'}
                save(out/'real-writes.json',result);return result
            return controlled_writes(client,identifier,RUN,out)
        rows=view['articles']
        assert len(rows)==1 and rows[0]['ITMREF_0'].strip()==code and rows[0]['ITMDES1_0'].strip()==name
        assert prior.get('creation',{}).get('status')=='succeeded','Only a campaign-confirmed created record is eligible'
        sites={r['STOFCY_0'].strip() for r in view['sites']}
        result={'code':code,'designation':name,'creation':'independently_verified','creation_readback':{'code':code,'sites':sorted(sites)},'folder':'TEST'}
        if sites=={'201','202'}:
            result.update(status='verified',modification_readback={'sites':sorted(sites)});save(out/'real-writes.json',result);return result
        assert sites=={'201'}
        session=client.new()
        session=client.post('/conversations/'+session['id']+'/modifications/drafts',{'revision':session['revision'],'resource':'article','code':code,'changes':{'add_sites':['202']}})
        draft=session['state']['modification_drafts'][-1];result['modification']=draft
        assert draft['operation']['status']=='prepared'
        assert all(n['kind']=='insert' and n['table']=='ITMFACILIT' and n['keys']=={'ITMREF_0':code,'STOFCY_0':'202'} for n in draft['operation']['plan']['nodes'])
        result.update(status='reviewed_existing_fixture',confirmation_authority='User explicitly authorized TEST modifications; exact site 202 addition reviewed')
        save(out/'real-writes.json',result)
        session=client.act(session,'modifications',draft['id'],'approve',True)
        result['status']='modification_attempted';save(out/'real-writes.json',result)
        session=client.act(session,'modifications',draft['id'],'execute',True)
        modified=next(d for d in session['state']['modification_drafts'] if d['id']==draft['id'])
        final=sql.snapshot('article',code);sites={r['STOFCY_0'].strip() for r in final['sites']}
        result.update(status='verified' if modified['operation']['status']=='succeeded' and sites=={'201','202'} else 'unconfirmed',modification=modified,modification_readback={'sites':sorted(sites)})
        save(out/'real-writes.json',result);return result
    finally:client.client.close()

def main():
    if os.environ.get('RUN_REAL_TEST_WRITES')!='USER_AUTHORIZED_TEST_ONLY':raise SystemExit('Explicit TEST guard missing')
    submitted=set();results={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={}
        while len(results)<100:
            for path in (OUT/RUN).glob('ART-*/conversation.json'):
                d=json.loads(path.read_text(encoding='utf-8'))
                if d.get('completed') and d['id'] not in submitted:
                    submitted.add(d['id']);futures[pool.submit(retry,d)]=d['id']
            for future in list(futures):
                if not future.done():continue
                identifier=futures.pop(future)
                try:results[identifier]=future.result()
                except Exception as exc:results[identifier]={'status':'stopped_no_retry','error':type(exc).__name__+': '+str(exc)[:500]}
                save(OUT/(RUN+'-write-retests')/'summary.json',results)
                print(json.dumps({'case':identifier,'status':results[identifier]['status']}),flush=True)
            time.sleep(3)

if __name__=='__main__':main()
