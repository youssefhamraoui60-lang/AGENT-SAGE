"""Read-only regression on source requests and documents; never create orders."""
import asyncio,json,sys,concurrent.futures,hashlib
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'telegram-test'))
from document_memory import decode
from read_documents_layout import read
from prepare import prepare
import learning_memory
OUT=ROOT/'runtime/sob-improvements-20261113';OLD=ROOT/'runtime/sob-quality-audit-20261112'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def write(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str),encoding='utf-8')

def main():
    original=load(OLD/'analysis-reviewed.json');today=load(OUT/'messages-week.json')
    files={r['id']:(OLD,r) for r in original['source'] if r.get('file')}
    files.update({r['id']:(OUT,r) for r in today if r.get('file')})
    decoded=load(OUT/'documents-after.json') if (OUT/'documents-after.json').exists() else {}
    cache={}
    # Today's two new printed orders and exact reviewed cases first, then the
    # remaining historical corpus. No data from manual OB orders is injected.
    ordered=sorted(files,key=lambda i:(0 if i>=5371 else 1,i))
    for mid in ordered:
        folder,r=files[mid];path=folder/r['file'];sha=hashlib.sha256(path.read_bytes()).hexdigest()
        if decoded.get(str(mid),{}).get('sha256')==sha:
            cache[sha]=decoded[str(mid)]
            continue
        try:
            d=cache.get(sha) or decode(path,read);cache[sha]=d;decoded[str(mid)]=d
        except Exception as e:decoded[str(mid)]={'ok':False,'error':type(e).__name__}
        write('documents-after.json',decoded)
        print(json.dumps({'document':mid,'ok':decoded[str(mid)].get('ok'),'done':len(decoded),'total':len(files)}),flush=True)
    old_failed={tuple(r['ids']) for r in load(OLD/'readonly-replays.json') if not r['ok'] or r.get('details',{}).get('missing_fields')}
    cases=[c.copy() for c in original['cases'] if tuple(c['ids']) in old_failed or 5204 in c['ids']]
    used=set()
    for r in today:
        if r['id'] in used or '[associatedChildMessage]' in r['text']:continue
        mids=[r['id']]
        if r['id']==5371:mids=[5371,5372,5373]
        if r['id']==5380:mids=[5380,5381,5382]
        if r['id']==5388:mids=[5388,5389]
        if r['id']==5373:continue
        used.update(mids)
        rs=[x for x in today if x['id'] in mids]
        cases.append({'case':'today-'+str(r['id']),'ids':mids,'source_text':'\n\n'.join(x['text'] for x in rs),
                      'date':r['date'],'files':[x['id'] for x in rs if x.get('file')],'agent_reply':'Historique du 13/11 à consulter séparément'})
    results=[]
    def one(c):
        try:
            source=c['source_text']
            if c['files']:
                # 5153 is explicitly superseded by the rectified 5168 file.
                for mid in (c['files'][-1:] if 5153 in c['files'] else c['files']):
                    d=decoded[str(mid)]
                    if not d.get('ok'):raise ValueError('Document unreadable')
                    source+='\nDOCUMENT JOINT :\n'+d['text']
            from message_intent import administrative_reply
            from delivery_status import is_followup
            admin=administrative_reply(source)
            if admin or is_followup(source):
                return {'ids':c['ids'],'case':c['case'],'source':source,'before':c['agent_reply'],'ok':True,
                        'status':'Message administratif / relance, pas une nouvelle commande','details':{'intent':'other','reply':admin or 'Relance reconnue : traitement par le module de suivi, sans création.','missing_fields':[],'lines':[]}}
            d=asyncio.run(prepare([{'role':'user','content':source}],details=True,reference_date=date.fromisoformat(c['date'][:10])))
            return {'ids':c['ids'],'case':c['case'],'source':source,'before':c['agent_reply'],'ok':True,'details':d,
                    'status':'Préparation sans manque signalé' if d.get('intent')=='order' and not d.get('missing_fields') else 'Clarification / contrôle encore nécessaire'}
        except Exception as e:return {'ids':c['ids'],'case':c['case'],'source':c['source_text'],'ok':False,'status':'Erreur technique','error':type(e).__name__+': '+str(e)[:160]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for r in pool.map(one,cases):
            results.append(r);write('preparations-after.json',results)
            print(json.dumps({'messages':r['ids'],'status':r['status'],'done':len(results),'total':len(cases)}),flush=True)
    from psycopg.types.json import Jsonb
    with learning_memory.db.connection() as conn:
        for r in results:
            conn.execute('''INSERT INTO sob_learning_examples(source_key,input_data,expected,observed,status)
                VALUES(%s,%s,NULL,%s,%s) ON CONFLICT(source_key) DO UPDATE SET observed=EXCLUDED.observed,status=EXCLUDED.status''',
                ('improvements-20261113-'+','.join(map(str,r['ids'])),Jsonb({'text':r['source']}),Jsonb(r),'replayed_needs_source_review'))
    write('summary-after.json',{'documents':len(decoded),'preparations':len(results),'ready':sum(r['status']=='Préparation sans manque signalé' for r in results),'technical_errors':sum(not r['ok'] for r in results),'sage_creations_by_script':0,'telegram_sends_by_script':0})
if __name__=='__main__':main()
