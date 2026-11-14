"""Recheck changed guards/aliases and preview two source-verified TEST plans."""
import asyncio,json,sys,concurrent.futures
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'telegram-test'))
import learning_memory
from document_memory import decode
from read_documents_layout import read
from prepare import prepare,canonical_article
from source_article_safety import brick_dimension_supported
from creation import build_payload,run_script
OUT=ROOT/'runtime/sob-improvements-20261113';OLD=ROOT/'runtime/sob-quality-audit-20261112'
def load(n):return json.loads((OUT/n).read_text(encoding='utf-8'))
def save(n,v):(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def main():
    results=load('preparations-after.json');docs=load('documents-after.json')
    rows={r['id']:r for r in json.loads((OLD/'messages-layout.json').read_text(encoding='utf-8'))}
    # Identity-only corrections keep all original OCR rows, without re-running
    # the visual model or importing any values from manual OB orders.
    for mid in [5237,5241,5325]:
        docs[str(mid)]=decode(OLD/rows[mid]['file'],lambda path:{'pages':[{'text':docs[str(mid)]['text'],'uncertain':True,'method':'previous_frozen_ocr'}]})
    save('documents-after.json',docs)
    chosen=[]
    for i,r in enumerate(results):
        d=r.get('details',{});source=r['source']
        own=(d.get('client') or {}).get('BPCNUM_0','').strip()=='C00191' and 'DOCUMENT JOINT' in source
        unsupported=any(not brick_dimension_supported(source,l['article']) for l in d.get('lines',[]))
        if not r.get('ok') or own or unsupported or 'DOCUMENT JOINT' in source:chosen.append(i)
    def one(i):
        r=results[i].copy();source=r['source']
        mids=[mid for mid in r['ids'] if str(mid) in docs]
        if 5153 in mids and 5168 in mids:mids=[5168]
        if mids:
            source=source.split('DOCUMENT JOINT',1)[0]
            for mid in mids:source+='\nDOCUMENT JOINT :\n'+docs[str(mid)]['text']
        r['source']=source
        try:
            d=asyncio.run(prepare([{'role':'user','content':source}],details=True,reference_date=date(2026,11,13) if min(r['ids'])>=5368 else date.fromisoformat(next(c['date'][:10] for c in json.loads((OLD/'analysis-reviewed.json').read_text(encoding='utf-8'))['cases'] if c['case']==r['case']))))
            r.update(ok=True,details=d,status='Préparation sans manque signalé' if d['intent']=='order' and not d['missing_fields'] else 'Clarification / contrôle encore nécessaire')
        except Exception as e:r.update(ok=False,status='Erreur technique',error=type(e).__name__+': '+str(e)[:160])
        return i,r
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for i,r in pool.map(one,chosen):
            results[i]=r;save('preparations-after.json',results)
            print(json.dumps({'refreshed':r['ids'],'status':r['status']}),flush=True)
    previews=[]
    for mid in [5377,5379]:
        r=next(r for r in results if mid in r['ids']);d=r['details']
        if d['missing_fields'] or not d['client']:
            previews.append({'message':mid,'mode':'preview','result':{'ok':False,'error':'Préparation bloquée : '+', '.join(d['missing_fields'])}})
            continue
        try:payload=build_payload(d,reference_date=date(2026,11,13))
        except Exception as e:
            previews.append({'message':mid,'mode':'preview','result':{'ok':False,'error':str(e)}})
            continue
        payload['mode']='preview'
        assert payload['mode']=='preview'
        preview=run_script('sob-execute.ps1',payload)
        previews.append({'message':mid,'mode':'preview','payload':payload,'result':preview})
        print(json.dumps({'sql_preview':mid,'ok':preview.get('ok'),'code':preview.get('code')}),flush=True)
    save('sql-previews-final.json',previews)
    # Regression checks from source documents, not copied OB values.
    for mid,expected in [(5377,[('RAB16',8000,9.3),('RAB14',6000,9.3),('RAB12',4000,9.3),('RAB10',10000,9.3),('RABT6',2000,9.3)]),(5379,[('CPJ45',40,80.5),('CPJ35',260,78.5)])]:
        d=next(r['details'] for r in results if mid in r['ids'])
        assert [(l['article'],l['quantity'],l['price']) for l in d['lines']]==expected
    from psycopg.types.json import Jsonb
    with learning_memory.db.connection() as conn:
        for r in results:
            conn.execute('''UPDATE sob_learning_examples SET observed=%s,status=%s WHERE source_key=%s''',
                (Jsonb(r),'replayed_needs_source_review','improvements-20261113-'+','.join(map(str,r['ids']))))
    save('learning-after.json',learning_memory.rules())
    summary={'documents':len(docs),'preparations':len(results),'ready':sum(r['status']=='Préparation sans manque signalé' for r in results),
             'administrative':sum(r['status'].startswith('Message administratif') for r in results),'technical_errors':sum(not r['ok'] for r in results),
             'sage_creations_by_script':0,'telegram_sends_by_script':0,'source_today_last':'2026-11-13T10:31:10+01:00','final_refresh_cases':len(chosen),
             'sql_previews_passed':sum(p['result'].get('ok',False) for p in previews)}
    save('summary-after.json',summary);print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
