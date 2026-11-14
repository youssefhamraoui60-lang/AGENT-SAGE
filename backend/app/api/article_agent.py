from uuid import UUID
from functools import wraps
import httpx,psycopg,requests
from fastapi import APIRouter,Depends,HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel,ConfigDict,Field
from app.api.business import require_operator,analyze as analyze_business,translate
from app.schemas.business import AnalyzeInput
from app.schemas.sage_crud import Approval,Execution
from app.services import article_agent as service,sage_crud as crud
from app.services.sage_soap import SageError
from app.services.business_ai import InvalidModelOutput
from app.core.config import settings
from zeep.exceptions import Error as ZeepError

router=APIRouter(prefix='/api/v1/article-agent',tags=['Article conversation'],dependencies=[Depends(require_operator)])

class Message(BaseModel):
    model_config=ConfigDict(extra='forbid')
    message:str=Field(min_length=3,max_length=8000)

class Revision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)

class Edit(Revision):
    draft:service.Draft

class Approve(Revision):
    approval:Approval

class Execute(Revision):
    execution:Execution

def guarded(fn):
    @wraps(fn)
    def call(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except (crud.CrudError,SageError) as exc:raise HTTPException(exc.status,exc.code) from None
        except psycopg.Error:raise HTTPException(503,'Historique PostgreSQL indisponible') from None
        except requests.RequestException:raise HTTPException(503,'Connexion Sage indisponible') from None
        except (ZeepError,ValueError,KeyError,TypeError):raise HTTPException(502,'Réponse ou mapping Sage invalide') from None
    return call

@router.post('/conversations')
async def create(body:Message):
    import re
    # Reject obvious credential pastes before storing or sending them to Ollama.
    secrets=[settings.approval_token.get_secret_value(),settings.sage_soap_password.get_secret_value()]
    if any(value and value in body.message for value in secrets) or re.search(r'(?:password|mot\s+de\s+passe|SAGE_SOAP_PASSWORD|APPROVAL_TOKEN)\s*(?:[:=]|est\b)|Authorization\s*:|\bBearer\s+[A-Za-z0-9._~-]+',body.message,re.I):
        raise HTTPException(422,'Ne saisissez aucun mot de passe ou jeton dans la conversation.')
    request=await analyze_business(AnalyzeInput(demande=body.message))
    try:return await run_in_threadpool(service.create,request['id'],request['proposition'] or {})
    except psycopg.Error:raise HTTPException(503,'Historique PostgreSQL indisponible') from None

@router.get('/conversations')
@guarded
def history():return {'conversations':service.history()}

@router.get('/conversations/{identifier}')
@guarded
def read(identifier:UUID):return service.read(identifier)

@router.patch('/conversations/{identifier}')
@guarded
def edit(identifier:UUID,body:Edit):return service.update(identifier,body.revision,body.draft)

@router.post('/conversations/{identifier}/check')
@guarded
def check(identifier:UUID,body:Revision):return service.validate(identifier,body.revision)

@router.post('/conversations/{identifier}/validate')
@guarded
def validate(identifier:UUID,body:Revision):return service.validate(identifier,body.revision,True)

@router.post('/conversations/{identifier}/prepare')
@guarded
def prepare(identifier:UUID,body:Revision):return service.prepare(identifier,body.revision)

@router.post('/conversations/{identifier}/approve')
@guarded
def approve(identifier:UUID,body:Approve):return service.approve(identifier,body.revision,body.approval)

@router.post('/conversations/{identifier}/execute')
@guarded
def execute(identifier:UUID,body:Execute):return service.execute(identifier,body.revision,body.execution)
