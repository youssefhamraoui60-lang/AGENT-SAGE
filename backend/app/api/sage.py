import logging
from uuid import UUID
import requests
import psycopg
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from app.api.business import require_operator
from app.core.config import settings
from app.services.sage_soap import SageReader,SageError
from app.schemas.sage_preparation import ArticlePreparation
from app.services import sage_preparations,business_store

router=APIRouter(prefix='/api/v1/sage',tags=['Sage lecture seule'],dependencies=[Depends(require_operator)])
logger=logging.getLogger('agent_sage')
def invoke(method,**kwargs):
    try: return getattr(SageReader(),method)(**kwargs)
    except SageError as exc:
        logger.warning('sage_read_error code=%s',exc.code)
        raise HTTPException(exc.status,detail=exc.code) from None

@router.get('/status')
def status():
    return {'credentials_configured':bool(settings.sage_soap_username.get_secret_value() and settings.sage_soap_password.get_secret_value()),
            'base_url':settings.sage_soap_base_url,'pool':settings.sage_soap_pool,'publication':settings.sage_soap_publication,'read_only':True,
            'connection_tested':False}
@router.get('/description')
def description(): return invoke('describe')
@router.get('/articles')
def articles(response:Response,limit:int=Query(default=20,ge=1,le=50)):
    response.headers['Cache-Control']='no-store'
    return invoke('articles',limit=limit)

@router.get('/articles/{reference}')
def read_article(reference:str,response:Response):
    response.headers['Cache-Control']='no-store'
    return invoke('read_article',reference=reference)

@router.post('/article-preparations')
def prepare_article(body:ArticlePreparation,response:Response):
    response.headers['Cache-Control']='no-store'
    try:return sage_preparations.prepare(body)
    except SageError as exc:raise HTTPException(exc.status,exc.code) from None
    except requests.Timeout:raise HTTPException(504,'sage_timeout') from None
    except requests.RequestException:raise HTTPException(503,'sage_network_error') from None
    except psycopg.Error:raise HTTPException(503,'local_preparation_database_unavailable') from None

@router.get('/article-preparations/{identifier}')
def read_preparation(identifier:UUID,response:Response):
    response.headers['Cache-Control']='no-store'
    try:return sage_preparations.read(identifier)
    except business_store.NotFound:raise HTTPException(404,'preparation_not_found') from None
    except psycopg.Error:raise HTTPException(503,'local_preparation_database_unavailable') from None
