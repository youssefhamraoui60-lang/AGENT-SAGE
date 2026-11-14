"""Separate cold/warm real model profiling; no database and no ERP writes."""
import asyncio,json,sys
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import chat_model as model
from app.core.config import settings
TEXT="Bonjour, j'ai besoin de la création de ces deux articles : Modern foam boards A XPS 4 CM et Modern foam boards B XPS 4 CM. Unité M2, fournisseur Modern for Foam and Plastic, catégorie AR."
async def main():
    out={'sage_writes':0,'mode':'FORCED_MODEL_PROFILING_ONLY_NOT_HTTP_ROUTING','cases':[]}
    token=model.FORCE_AI.set(True)
    try:
        async with httpx.AsyncClient(timeout=600,trust_env=False) as client:
            for mode in ['cold','warm']:
                if mode=='cold':
                    response=await client.post(settings.ollama_url+'/api/generate',json={'model':settings.ollama_model,'keep_alive':0});response.raise_for_status()
                value,proof=await model.extract(TEXT,{},[],[])
                valid=len(value.articles)==2 and all((a.unite or value.shared.unite)=='M2' and (a.categorie or value.shared.categorie)=='AR' and not a.taux_tva for a in value.articles) and not value.shared.taux_tva
                out['cases'].append({'articles':2,'mode':mode,'status':'PASS' if valid else 'FAILED','performance':{'qwen':proof['timings']},'provenance':proof,'extraction':value.model_dump(exclude_none=True,exclude_unset=True)})
                (ROOT/'logs/chat-performance-qwen-profile.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
                print(mode,'PASS' if valid else 'FAILED_EXTRACTION',proof['seconds'],flush=True)
    finally:model.FORCE_AI.reset(token)
if __name__=='__main__':asyncio.run(main())
