"""Read-only replay of the user's reported Telegram failures."""
import asyncio
import json
from pathlib import Path
from prepare import prepare

CASES = [
    ('Bouchaib', 'Houssine swalam 180 sacs 35 360 sacs 45 novacim'),
    ('Abdelmajid', 'Nassiri abdelghani\n240 sacs CPJ45 CIMAT\n78 dh\nSettat\nLe chauffeur doit récupérer le règlement'),
    ('Omri Mohamed', 'Salhane Adil\n300 ciment 35\n300 ciment 45\nGara cimat'),
    ('Aicha Khayr', 'Lagrighihi hassan C00856\n300 kg rab 10 = 910 dh\nTrs = 50 dh\n( cheraoui abdellah)\n0666652685\nPayé en espèce'),
    ('Aicha Khayr', 'Iskane al mohute\n20 sac cpj 35\n20 sac cpj 45\nTrs = 100 dh\n( belmarakchi khadija )\n0662407667\nRhaihat/ berrechid'),
    ('Reda Elhouari', '15t cpj 35\nPrimo living'),
    ('Omri Mohamed', 'Salouj promo\n1 voyage sable lavé 30 m\n6500 dh berrechid'),
    ('Abdelhamid Filali', 'Alyosr promotion\n12 tonnes cpj 35 temara 75dh\nMediona\n0680797344'),
]

async def main():
    results=[]
    for contact, text in CASES:
        history=[{'role':'user','content':'Contact : '+contact+'\n\n'+text}]
        try:
            details=await prepare(history,details=True)
            result={'contact':contact,'text':text,'details':details}
        except Exception as exc:
            result={'contact':contact,'text':text,'error':type(exc).__name__}
        results.append(result)
        path=Path(__file__).resolve().parents[1]/'runtime/sob-week-20261102/reported-examples-retest.json'
        path.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        d=result.get('details',{})
        print(json.dumps({'contact':contact,'client':(d.get('client') or {}).get('BPCNUM_0'),'lines':d.get('lines'),'missing':d.get('missing_fields'),'error':result.get('error')},ensure_ascii=False),flush=True)

if __name__=='__main__':asyncio.run(main())
