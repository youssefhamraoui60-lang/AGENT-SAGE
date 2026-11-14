import asyncio
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services.ai import extract
from app.core.config import settings

CASES = [
    'Bonjour, crée un article Etalonnage Balance 2T avec attestation de labo, unité, catégorie FG, fournisseur PARTENAIRE SCALE Sarl.',
    "Créer l'article Câble souple 4x50 mm RVK NOIR, unité, catégorie FG, fournisseur SOTAMO.",
    'Créer POLYSTER 3 CM, unité M3, catégorie MARCH, fournisseur ISONIMA.',
]

async def main():
    results=[]
    for i,prompt in enumerate(CASES,1):
        for attempt in range(1,4):
            start=time.perf_counter()
            item={'test':i,'essai':attempt,'model':settings.ollama_model}
            try:
                item.update(status='PASS',schema_valid=True,json=(await extract(prompt)).model_dump())
            except Exception as exc:
                item.update(status='FAIL',schema_valid=False,error=f'{type(exc).__name__}: {exc}')
                if hasattr(exc,'raw'):
                    item['raw']=exc.raw
            item['seconds']=round(time.perf_counter()-start,3)
            results.append(item)
            print(f"Test {i} essai {attempt}: {item['status']} ({item['seconds']}s)",flush=True)
    folder=Path(__file__).resolve().parents[1]/'logs'
    (folder/'ollama-tests.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    text='# Tests Ollama\n\nValidation du schema uniquement; exactitude semantique a examiner.\n\n'
    for item in results:
        text+='```json\n'+json.dumps(item,ensure_ascii=False,indent=2)+'\n```\n\n'
    for i in range(1,4):
        subset=[x for x in results if x['test']==i and x['status']=='PASS']
        unique=len({json.dumps(x['json'],sort_keys=True,ensure_ascii=False) for x in subset})
        text+=f'Test {i}: {len(subset)}/3 JSON valides; {unique} sorties distinctes.\n\n'
    (folder/'ollama-tests.md').write_text(text,encoding='utf-8')
    return 0 if all(x['status']=='PASS' for x in results) else 1

if __name__=='__main__':
    sys.exit(asyncio.run(main()))
