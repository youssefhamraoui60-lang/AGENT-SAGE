import asyncio,json,sys
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'telegram-test'))
from prepare import prepare
OUT=ROOT/'runtime/sob-improvements-20261113'
async def main():
    decoded=json.loads((OUT/'documents-after.json').read_text(encoding='utf-8'))
    raw=json.loads((OUT/'messages-week.json').read_text(encoding='utf-8'))
    results=[];sem=asyncio.Semaphore(2)
    async def one(mid):
        async with sem:
            r=next(x for x in raw if x['id']==mid)
            text=r['text']+'\nDOCUMENT JOINT :\n'+decoded[str(mid)]['text']
            d=await prepare([{'role':'user','content':text}],details=True,reference_date=date(2026,11,13))
            result={'id':mid,'client':(d.get('client') or {}).get('BPCNUM_0'),'lines':d['lines'],'missing':d['missing_fields'],'details':d}
            results.append(result)
            (OUT/'today-preparations-verified.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in result.items() if k!='details'},ensure_ascii=True),flush=True)
    await asyncio.gather(*(one(mid) for mid in [5371,5377,5379]))
    steel=next(x for x in results if x['id']==5377)
    assert [(r['article'],r['quantity'],r['price']) for r in steel['lines']]==[('RAB16',8000,9.3),('RAB14',6000,9.3),('RAB12',4000,9.3),('RAB10',10000,9.3),('RABT6',2000,9.3)]
    cement=next(x for x in results if x['id']==5379)
    assert [(r['article'],r['quantity'],r['price']) for r in cement['lines']]==[('CPJ45',40,80.5),('CPJ35',260,78.5)]
    print('Source quantities / prices verified; no order creation called.',flush=True)
if __name__=='__main__':asyncio.run(main())
