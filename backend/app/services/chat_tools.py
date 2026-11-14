"""Bounded predefined SQL tools; the model cannot submit SQL text or identifiers."""
import json,subprocess,re
from time import perf_counter
from app.services import chat_performance as performance
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
TOOLS={'search_articles','get_recent_articles','check_article_duplicate','get_article_categories','get_units','get_unit_conversions','get_sites','search_suppliers','search_customers','get_supplier_article_references','get_accounting_categories','get_tax_rules','get_tax_determination','get_article_site'}
TOOLS|={'check_supplier_fiscal_duplicates','get_supplier_preparation_profile','get_supplier_record'}
TOOLS|={'get_article_record','get_article_site_record'}
TOOLS.add('search_supplier_candidates')
TOOLS.add('get_supplier_creation_fields')
TOOLS.add('list_suppliers')
TOOLS.add('get_recent_suppliers')
TOOLS.add('get_tax_determination_by_vat')
TOOLS.add('search_units')
def pattern(value):return '%'+value.replace('~','~~').replace('%','~%').replace('_','~_').replace('[','~[')+'%'
def key(tool,args):return json.dumps([tool,args],sort_keys=True,ensure_ascii=False)
def run(calls):
    started=perf_counter()
    try:return _run(calls)
    finally:performance.add('sql_wall_ms',(perf_counter()-started)*1000)

def _run(calls):
    if len(calls)>180 or any(c['tool'] not in TOOLS for c in calls):raise ValueError('Unsupported tool plan')
    for call in calls:
        if 'Folder' in call['args'] and call['args']['Folder'] not in ('TEST','OB'):raise ValueError('Read folder denied')
        if call['tool']=='get_recent_suppliers':
            a=call['args']
            if set(a)!={'Folder','Status','PageSize'} or a['Folder'] not in ('TEST','OB') or a['Status'] not in ('active','inactive','all') or not re.fullmatch(r'[0-9]{1,2}',a['PageSize']) or not 1<=int(a['PageSize'])<=20:raise ValueError('Invalid recent supplier query')
        if call['tool']=='list_suppliers':
            a=call['args']
            if set(a)!={'Folder','Status','Offset','PageSize'} or a['Folder'] not in ('TEST','OB') or a['Status'] not in ('active','inactive','all') or not re.fullmatch(r'[0-9]{1,6}',a['Offset']) or not re.fullmatch(r'[0-9]{1,2}',a['PageSize']) or not 1<=int(a['PageSize'])<=50:raise ValueError('Invalid supplier list scope or bounds')
        if call['tool'] in ('check_supplier_fiscal_duplicates','get_supplier_preparation_profile','get_supplier_record') and call['args'].get('Folder') not in ('TEST','OB'):raise ValueError('Supplier read folder denied')
        if any(not isinstance(v,str) or len(v)>100 or any(ord(c)<32 for c in v) for v in call['args'].values()):raise ValueError('Invalid tool parameters')
    return pooled(calls)

import threading,concurrent.futures,copy,time,atexit
_EXEC=concurrent.futures.ThreadPoolExecutor(max_workers=2,thread_name_prefix='chat-sql')
_LOCAL=threading.local()
_PROCESSES=[]
_CACHE={}
_LOCK=threading.Lock()
_STABLE={'get_sites','get_article_categories','get_units','get_unit_conversions','get_accounting_categories'}
_STABLE.add('search_units')
_STABLE.add('get_supplier_creation_fields')
_FRESH={'check_article_duplicate','get_article_site','get_supplier_article_references','search_suppliers','search_customers'}
_FRESH|={'check_supplier_fiscal_duplicates','get_supplier_preparation_profile','get_supplier_record'}
_FRESH|={'get_article_record','get_article_site_record'}
_FRESH.add('search_supplier_candidates')
_FRESH.add('list_suppliers')
_FRESH.add('get_recent_suppliers')
_FRESH|={'get_tax_rules','get_tax_determination','get_tax_determination_by_vat'}
def invalidate_cache():
    with _LOCK:_CACHE.clear()
def _worker(calls):
    p=getattr(_LOCAL,'process',None)
    try:
        if p is None or p.poll() is not None:
            p=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'scripts/chat_sql_worker.ps1')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',bufsize=1)
            _LOCAL.process=p;_PROCESSES.append(p)
        payload=[]
        for c in calls:
            label=c['args'].get('Label','');first=next((w for w in re.findall(r'\w+',label) if len(w)>=4),'')
            near=label[:4] if c['tool']=='get_article_categories' and len(label)>=4 else first
            payload.append({**c,'args':{**c['args'],'Pattern':pattern(label),'NearPattern':pattern(near or label)}})
        p.stdin.write(json.dumps({'calls':payload},ensure_ascii=False)+'\n');p.stdin.flush()
        line=p.stdout.readline(1500001)
        if len(line)>1500000:raise ValueError()
        body=json.loads(line.lstrip('\ufeff'))
        if not body.get('ok'):raise ValueError()
        return body
    except (OSError,ValueError):
        if p is not None:p.kill()
        _LOCAL.process=None
        return {'results':[{'id':c['id'],'tool':c['tool'],'ok':False,'rows':[],'code':'sql_unavailable'} for c in calls]}
def pooled(calls):
    result={};missing=[];now=time.monotonic()
    with _LOCK:
        for c in calls:
            found=_CACHE.get(key(c['tool'],c['args']))
            catalogue=c['tool']=='get_article_categories' and not any(c['args'].get(k) for k in ('Category','Label','Site'))
            if found and found[0]>now and not catalogue:
                row=copy.deepcopy(found[1]);row.update(id=c['id'],cache_hit=True,cache_age_seconds=round(now-found[2],3));result[c['id']]=row
            else:missing.append(c)
    performance.add('sql_cache_hits',len(result));performance.add('sql_fresh_calls',len(missing))
    buckets=[missing[i::2] for i in range(min(2,len(missing)))]
    jobs=[_EXEC.submit(_worker,bucket[j:j+60]) for bucket in buckets for j in range(0,len(bucket),60)]
    for job in jobs:
        try:body=job.result(timeout=75)
        except concurrent.futures.TimeoutError:
            for p in list(_PROCESSES):
                if p.poll() is None:p.kill()
            body={'results':[]}
        performance.add('sql_connection_open_ms',body.get('connection_open_ms',0))
        for row in body['results']:
            result[row['id']]=row;performance.add('sql_query_ms',row.get('query_ms',0))
    with _LOCK:
        for c in missing:
            row=result.setdefault(c['id'],{'id':c['id'],'tool':c['tool'],'ok':False,'rows':[],'code':'sql_unavailable'})
            if row.get('ok') and c['tool'] not in _FRESH:
                ttl=300 if c['tool'] in _STABLE else 60 if c['tool'].startswith('get_tax') else 15
                _CACHE[key(c['tool'],c['args'])]=(time.monotonic()+ttl,copy.deepcopy(row),time.monotonic())
        while len(_CACHE)>512:_CACHE.pop(next(iter(_CACHE)))
    return result
@atexit.register
def _close_workers():
    for p in _PROCESSES:
        if p.poll() is None:p.kill()

class Plan:
    def __init__(self):self.calls=[];self.cache={}
    def add(self,tool,**args):
        name=key(tool,args)
        if name not in self.cache:
            self.cache[name]=str(len(self.calls));self.calls.append({'id':self.cache[name],'tool':tool,'args':args})
        return self.cache[name]

# Public controlled functions exposed to the orchestrator, never arbitrary model SQL.
def search_articles(plan,label,category=''):return plan.add('search_articles',Label=label,Category=category)
def get_recent_articles(plan,category=''):return plan.add('get_recent_articles',Category=category)
def check_article_duplicate(plan,code):return plan.add('check_article_duplicate',Code=code)
def get_article_categories(plan,category,label='',site=''):return plan.add('get_article_categories',Category=category,Label=label,Site=site)
def get_units(plan,unit,unit2=''):return plan.add('get_units',Unit=unit,Unit2=unit2)
def get_sites(plan,site):return plan.add('get_sites',Site=site)
def search_suppliers(plan,name='',code=''):return plan.add('search_suppliers',Label=name,Supplier=code)
def get_supplier_article_references(plan,supplier,article=''):return plan.add('get_supplier_article_references',Supplier=supplier,Code=article)
def get_accounting_categories(plan,label='',code=''):return plan.add('get_accounting_categories',Label=label,Code=code)
def get_tax_rules(plan,rate='',company='',code=''):return plan.add('get_tax_rules',Rate=rate,Company=company,Code=code)
