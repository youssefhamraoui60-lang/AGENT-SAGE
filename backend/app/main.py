import json
import logging
import time
from contextlib import asynccontextmanager
import httpx
import psycopg
from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError
from app.core.config import settings
from app.schemas.extraction import ExtractRequest, Extraction
from app.services.ai import extract

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('agent_sage')
@asynccontextmanager
async def learning_lifespan(application):
    import asyncio
    from app.services.chat_storage import migrate as migrate_accounts
    await asyncio.to_thread(migrate_accounts)
    from app.services.learning_training import periodic
    task=asyncio.create_task(periodic()) if settings.learning_enabled and settings.learning_scheduler_enabled else None
    from app.services.learning_auto import periodic as improvement_periodic
    improvement_task=asyncio.create_task(improvement_periodic()) if settings.learning_enabled and settings.learning_scheduler_enabled else None
    try:yield
    finally:
        if improvement_task:
            improvement_task.cancel()
            try:await improvement_task
            except asyncio.CancelledError:pass
        if task:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass

app = FastAPI(title='AGENT-SAGE-X3 - Etape 1', docs_url='/docs',lifespan=learning_lifespan)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
@app.exception_handler(RequestValidationError)
async def safe_validation_error(request,exc):
    return JSONResponse(status_code=422,content={'detail':[{'loc':list(e['loc']),'msg':e['msg'],'type':e['type']} for e in exc.errors()]})
from app.api.pki_publication import router as pki_router,restrict_lan_to_public_pki
app.include_router(pki_router)
app.middleware('http')(restrict_lan_to_public_pki)
from app.api.business import router as business_router
app.include_router(business_router)
from app.api.sage import router as sage_router
from app.api.sage_crud import router as sage_crud_router
app.include_router(sage_crud_router)
app.include_router(sage_router)
from app.api.article_agent import router as article_agent_router
app.include_router(article_agent_router)
from app.api.chat import router as chat_router
app.include_router(chat_router)
from app.api.learning import router as learning_router
app.include_router(learning_router)
from app.api.accounts import router as accounts_router
app.include_router(accounts_router)
from app.api.mcp_sage import router as mcp_sage_router
app.include_router(mcp_sage_router)
from app.api.article_sql import router as article_sql_router
app.include_router(article_sql_router)
from app.api.modification import router as modification_router
app.include_router(modification_router)
from app.api.ai_provider import router as ai_provider_router
app.include_router(ai_provider_router)
from app.api.sob import router as sob_router
app.include_router(sob_router)

from pathlib import Path
from fastapi.staticfiles import StaticFiles
sage_ui=Path(__file__).resolve().parents[2]/'frontend'/'dist'
if sage_ui.is_dir():
    app.mount('/sage',StaticFiles(directory=str(sage_ui),html=True),name='sage-ui')

@app.middleware('http')
async def log_request(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    if request.url.path in ('/sage','/sage/','/sage/index.html'):
        response.headers['Cache-Control']='no-store, max-age=0'
    if request.url.path.startswith('/api/v1/chat'):
        response.headers['Cache-Control']='no-store'
        response.headers['Vary']='Cookie'
    logger.info(json.dumps({'event':'http','path':request.url.path,'status':response.status_code,
                            'duration_ms':round((time.perf_counter()-start)*1000)}))
    return response

@app.get('/health')
async def health():
    return {'status':'ok','stage':1}

@app.get('/health/db')
def health_db():
    try:
        # FastAPI runs sync handlers in its thread pool; psycopg async cannot use
        # the default Windows Proactor loop used by this native Uvicorn setup.
        with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
            row = conn.execute('SELECT 1').fetchone()
            if row != (1,):
                raise ValueError('Unexpected database result')
        return {'status':'ok'}
    except (psycopg.Error, ValueError):
        raise HTTPException(503, 'PostgreSQL indisponible')

@app.get('/health/ollama')
async def health_ollama():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(settings.ollama_url+'/api/tags')
            r.raise_for_status()
            if settings.ollama_model not in [m['name'] for m in r.json()['models']]:
                raise ValueError('Model missing')
        return {'status':'ok','model':settings.ollama_model}
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(503,'Ollama ou modele indisponible')

@app.post('/api/ai/extract', response_model=Extraction)
async def extract_article(body: ExtractRequest):
    try:
        return await extract(body.demande)
    except httpx.TimeoutException:
        raise HTTPException(504,'Delai Ollama depasse')
    except httpx.HTTPError:
        raise HTTPException(503,'Ollama indisponible')
    except (ValidationError, ValueError, KeyError, TypeError):
        raise HTTPException(502,'Reponse IA non conforme')
