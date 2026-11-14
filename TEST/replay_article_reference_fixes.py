"""Two real-provider prefix replays, no Sage approvals, within shared USD cap."""
import concurrent.futures,json
from pathlib import Path
from run_100_article_sessions import Client,OUT,save
from app.services import business_store as db

def remaining():
    with db.connection() as conn:
        r=conn.execute("SELECT used_usd FROM chat_ai_budget WHERE day=(now() AT TIME ZONE 'UTC')::date").fetchone()
    return .5-float(r['used_usd']) if r else .5

def replay(source):
    client=Client('http://127.0.0.1:8013','reference-fix',source['id'])
    s=client.new();result={'source':source['id'],'turns':[],'sage_writes':0}
    try:
        for step in source['messages'][:13]:
            if remaining()<.08:result['stopped']='budget_headroom';break
            s=client.send(s,step['utilisateur'])
            errors=[];reply=s['messages'][-1]['content'];a=s['state'].get('articles',[])
            if 'Appel non validé' in reply:errors.append('tool_rejected')
            if step['numero']==3 and (len(a)!=1 or a[0].get('designation')!=source['article_de_depart']):errors.append('name_correction')
            if step['numero']==12 and source['id']=='ART-002' and (len(a)!=1 or a[0].get('categorie')!='NEG'):errors.append('verified_negoce_mapping')
            if step['numero']==13 and source['id']=='ART-001' and (len(a)!=2 or a[1].get('site')!=a[0].get('site')):errors.append('same_site_reference')
            result['turns'].append({'number':step['numero'],'text':step['utilisateur'],'reply':reply,'errors':errors,'state':s['state']})
            save(OUT/'reference-fix-final'/f'{source["id"]}.json',result)
        result['completed']=len(result['turns'])==13
        result['errors']=sum(bool(t['errors']) for t in result['turns'])
        save(OUT/'reference-fix-final'/f'{source["id"]}.json',result)
        print(json.dumps({'case':source['id'],'turns':len(result['turns']),'errors':result['errors']}),flush=True)
    finally:client.client.close()

if __name__=='__main__':
    data=json.loads((OUT/'source.json').read_text(encoding='utf-8'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(replay,data['sessions'][:2]))
