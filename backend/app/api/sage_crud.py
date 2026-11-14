from uuid import UUID
from functools import wraps
import logging
import psycopg,requests
from zeep.exceptions import Error as ZeepError
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from app.api.business import require_operator
from app.schemas.sage_crud import Preparation,Approval,Execution
from app.services import sage_crud as service
from app.services.sage_gateway import Gateway
from app.services.sage_soap import SageError

router=APIRouter(prefix='/api/v1/sage',tags=['Sage TEST - approved operations'],dependencies=[Depends(require_operator)])
log=logging.getLogger('agent_sage.crud')
def guarded(fn):
    @wraps(fn)
    def handler(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except (service.CrudError,SageError) as exc:
            log.warning('sage_crud_error code=%s',exc.code)
            raise HTTPException(exc.status,exc.code) from None
        except requests.exceptions.SSLError:raise HTTPException(503,'sage_tls_validation_failed') from None
        except requests.Timeout:raise HTTPException(504,'sage_timeout') from None
        except requests.RequestException:raise HTTPException(503,'sage_network_unavailable') from None
        except psycopg.Error:raise HTTPException(503,'local_operation_database_unavailable') from None
        except (ZeepError,ValueError,TypeError,KeyError):raise HTTPException(502,'sage_invalid_response_or_schema') from None
    return handler

def writes_ready(request:Request):
    result=service.security()
    if not result['ready']:raise HTTPException(423,{'code':'sage_writes_disabled','blockers':result['blockers']})
    if result.get('scope') and not (request.method=='POST' and
        (request.url.path=='/api/v1/sage/articles' or
         request.url.path.startswith('/api/v1/sage/operations/') and request.url.path.endswith('/approve'))):
        raise HTTPException(423,'outside_single_article_test_scope')

@router.get('/security')
def security_status():return service.security()

@router.get('/diagnostics/runtime')
def runtime_status():
    """Protected boolean-only inspection of settings loaded in this worker."""
    import os,getpass
    from pathlib import Path
    from app.core.config import settings
    return {'pid':os.getpid(),'windows_user':getpass.getuser(),
        'soap_username':settings.sage_soap_username.get_secret_value(),
        'soap_secret_loaded':bool(settings.sage_soap_password.get_secret_value()),
        'dpapi_configured':bool(settings.sage_soap_credential_file),
        'ca_bundle_exists':Path(settings.sage_soap_ca_bundle).is_file(),
        'crl_bundle_exists':Path(settings.sage_soap_crl_bundle).is_file(),
        'writes_enabled':settings.sage_writes_enabled,
        'powershell_chat_enabled':settings.sage_powershell_chat_enabled}

@router.get('/{resource}/schema')
@guarded
def schema(resource:str):return service.schema(resource)

@router.get('/{resource}/history')
@guarded
def history(resource:str):
    Gateway(resource)
    return service.history(resource)

@router.post('/{resource}/prepare')
@guarded
def prepare(resource:str,body:Preparation):return service.prepare(resource,body)

@router.get('/operations/{identifier}')
@guarded
def operation(identifier:UUID):return service.read(identifier)

@router.post('/operations/{identifier}/approve',dependencies=[Depends(writes_ready)])
@guarded
def approve(identifier:UUID,body:Approval):return service.approve(identifier,body)

@router.post('/operations/{identifier}/reconcile')
@guarded
def reconcile(identifier:UUID):return service.reconcile(identifier)

def collection(resource):
    @guarded
    def list_records(limit:int=Query(default=10,ge=1,le=50)):return Gateway(resource).query(limit)
    return list_records

for resource in ['suppliers','article-sites']:
    router.add_api_route('/'+resource,collection(resource),methods=['GET'],name='list_'+resource)

@router.get('/articles')
@guarded
def list_articles(limit:int=Query(default=20,ge=1,le=50)):
    result=Gateway('articles').query(limit)
    return {**result,'articles':result['records'],'count':len(result['records']),'read_only':True,'source':'sage_live'}

@router.get('/articles/{code:path}')
@guarded
def read_article(code:str):
    record=Gateway('articles').read({'ITMREF':code})
    if not record['exists']:raise HTTPException(404,'article_not_found')
    visible={'ITMREF','DES1AXX','DES2AXX','DES3AXX','TCLCOD','ITMSTA','STU','SAU','PUU','XBPS','SEAKEY','EANCOD','PUUSTUCOE','SAUSTUCOE','LOTMGTCOD','ACCCOD','STOMGTCOD'}
    article={key.rsplit('.',1)[-1]:value for key,value in record['fields'].items() if key.rsplit('.',1)[-1] in visible}
    return {'article':article,'record':record,'publication':'WS_ARTICLE','source':'sage_live','read_only':True,'folder':'TEST'}

@router.get('/suppliers/{code:path}')
@guarded
def read_supplier(code:str):
    keys=Preparation(action='create',keys={'BPSNUM':code},fields=[{'group':'BPRS_1','name':'BPRSHO','value':'validation'}]).keys
    return {'resource':'suppliers','folder':'TEST','record':Gateway('suppliers').read(keys)}

@router.get('/article-sites/{article:path}/{site}')
@guarded
def read_site(article:str,site:str):
    keys=Preparation(action='create',keys={'ITMREF':article,'STOFCY':site},fields=[{'group':'ITF1_2','name':'ABCCLS','value':'1'}]).keys
    return {'resource':'article-sites','folder':'TEST','record':Gateway('article-sites').read(keys)}

def create_handler(resource):
    @guarded
    def create(body:Execution):
        row=service.read(body.operation_id)
        return service.execute(resource,'create',row['record_keys'],body)
    return create

for resource in ['articles','suppliers','article-sites']:
    router.add_api_route('/'+resource,create_handler(resource),methods=['POST'],dependencies=[Depends(writes_ready)],name='create_'+resource)

@router.patch('/articles/{code:path}',dependencies=[Depends(writes_ready)])
@guarded
def update_article(code:str,body:Execution):return service.execute('articles','update',{'ITMREF':code},body)

@router.patch('/suppliers/{code:path}',dependencies=[Depends(writes_ready)])
@guarded
def update_supplier(code:str,body:Execution):return service.execute('suppliers','update',{'BPSNUM':code},body)

@router.patch('/article-sites/{article:path}/{site}',dependencies=[Depends(writes_ready)])
@guarded
def update_site(article:str,site:str,body:Execution):return service.execute('article-sites','update',{'ITMREF':article,'STOFCY':site},body)
