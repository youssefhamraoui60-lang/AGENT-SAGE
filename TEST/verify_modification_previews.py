"""Real TEST reads/previews only. Never execute=True, never GRANT or Sage DML."""
import sys,json,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import erp_modification as mod,sage_crud as crud

def main():
    schema=mod.catalog();views={r:mod.snapshot(r,c) for r,c in [('supplier','F994'),('article','TESTART201'),('unit','QZ9')]};results=[];plans=[]
    cases=[('supplier','F994',{'phone':'0600000099'}),('supplier','F994',{'email':'verification-readonly@example.test'}),('article','TESTART201',{'add_sites':['202']})]
    for resource,code,changes in cases:
        d={'id':'readonly-preview','resource':resource,'folder':'TEST','code':code,'changes':changes}
        op=mod.prepare(d,schema,views[resource]);r=op['preview'];assert r['ok'] and r['transaction_state']=='VALIDATED_NO_WRITE' and not r['executed'] and r['affected']==0,r
        results.append({'case':changes,**r});plans.append(op['plan'])
    blocked=[]
    for resource,code,changes in [('article','TESTART201',{'accounting':'61253000'}),('supplier','F994',{'ice':'000000000000001'}),('unit','QZ9',{'model':'SAC','stock_unit':'KG','coefficient':'25','inverse':'.04'})]:
        try:mod.build({'resource':resource,'code':code,'folder':'TEST','changes':changes},schema,views[resource])
        except crud.CrudError as e:blocked.append({'resource':resource,'code':code,'message':e.code})
        else:raise AssertionError('Expected safe block missing')
    negatives=[]
    stale=copy.deepcopy(plans[0]);stale['nodes'][0]['source_hash']='0'*64
    changed=copy.deepcopy(plans[0]);changed['dependencies']['sources'][0]['has_matches']=not changed['dependencies']['sources'][0]['has_matches']
    forbidden=copy.deepcopy(plans[0]);forbidden['nodes'][0]['values']['BPANUM_0']='F007'
    for name,plan,number in [('stale_row',stale,50319),('changed_dependencies',changed,50304),('immutable_key',forbidden,50310)]:
        r=mod.transport('plan',plan['resource'],plan['code'],plan,False);assert r.get('ok') is False and r.get('transaction_state')=='ROLLBACK' and r.get('sql_error_number')==number,r
        negatives.append({'case':name,**r})
    report={'sage_writes':0,'permission_changes':0,'previews':results,'blocked_operations':blocked,'negative_previews':negatives,'dependency_sources':{k:len(v['dependencies'].get('sources') or []) for k,v in views.items()}}
    (ROOT/'TEST/modification-real-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'PASS','previews':len(results),'safe_blocks':len(blocked),'negative_previews':len(negatives),'sage_writes':0,'permission_changes':0}))

if __name__=='__main__':main()
