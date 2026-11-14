from uuid import UUID
from typing import Literal
from functools import wraps
import logging
import httpx,psycopg
from fastapi import APIRouter,Depends,Request,Response,HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel,ConfigDict,Field,StrictBool
from app.services import conversation_chat as service,chat_auth as auth,sage_crud as crud

router=APIRouter(prefix='/api/v1/chat',tags=['Session-secured conversational agent'])
log=logging.getLogger('agent_sage.chat')
class Message(BaseModel):
    model_config=ConfigDict(extra='forbid')
    content:str=Field(min_length=1,max_length=12000)
    revision:int=Field(ge=1)
class Action(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)
    confirm:StrictBool=False
    confirm_duplicates:StrictBool=False
    confirm_draft_only_fields:StrictBool=False
    site:str|None=Field(default=None,pattern=r'^[A-Z0-9_-]{1,5}$')
class JobMessage(Message):
    request_id:UUID
def error(exc):
    if getattr(exc,'sqlstate',None)=='P2001':return HTTPException(507,'Votre espace de 200 Mo est plein. Supprimez des conversations ou des fichiers pour continuer.')
    if getattr(exc,'sqlstate',None)=='23505':return HTTPException(409,'Cet enregistrement existe déjà.')
    if isinstance(exc,crud.CrudError):return HTTPException(exc.status,exc.code)
    from app.services.chat_model import ExtractionTimeout
    if isinstance(exc,ExtractionTimeout):
        reasons={'queue':'Le modèle local est occupé ; l’extraction n’a pas démarré.',
            'connection':'Connexion au modèle local impossible dans le délai.',
            'stream_idle':'Le modèle local a cessé de répondre pendant l’extraction.',
            'total':'Le budget total de l’extraction IA est dépassé.'}
        return HTTPException(504,reasons.get(exc.phase,'Extraction IA interrompue.')+' La demande est conservée ; utilisez la reprise de l’analyse.')
    if isinstance(exc,httpx.TimeoutException):return HTTPException(504,'Le modèle local dépasse le délai. Votre conversation est conservée.')
    if isinstance(exc,httpx.HTTPError):return HTTPException(503,'Ollama local indisponible.')
    if isinstance(exc,psycopg.Error):return HTTPException(503,'Mémoire PostgreSQL indisponible.')
    return HTTPException(502,'Analyse non conforme : reformulez le dernier message, sans répéter les informations précédentes.')
def guarded(fn):
    @wraps(fn)
    def call(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except (crud.CrudError,psycopg.Error,ValueError,KeyError,TypeError) as exc:raise error(exc) from None
    return call
@router.post('/session')
@guarded
def bootstrap(request:Request,response:Response):return auth.bootstrap(request,response)
@router.get('/session')
def session(request:Request,response:Response):return auth.bootstrap(request,response)
@router.get('/conversations')
@guarded
def history(q:str='',user=Depends(auth.identity)):return {'conversations':service.history(user['owner_id'],q[:200])}
class CreateConversation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    discussion_mode:Literal['general','supplier','supplier_ob','ob']='general'

@router.post('/conversations')
@guarded
def create(body:CreateConversation|None=None,user=Depends(auth.operator)):
    return service.create(user['owner_id'],body.discussion_mode if body else 'general')
@router.get('/conversations/{identifier}')
@guarded
def read(identifier:UUID,user=Depends(auth.identity)):return service.read(user['owner_id'],identifier)

@router.get('/conversations/{identifier}/operation-state.json')
@guarded
def operation_state(identifier:UUID,user=Depends(auth.identity)):
    from app.services.conversation_state import export
    return Response(content=export(user['owner_id'],identifier),media_type='application/json',headers={
        'Content-Disposition':f'attachment; filename="session-{identifier}.json"',
        'Cache-Control':'no-store',
    })

@router.post('/conversations/{identifier}/analysis-jobs',status_code=202)
async def submit_job(identifier:UUID,body:JobMessage,user=Depends(auth.operator)):
    from app.services import chat_jobs
    try:return await chat_jobs.submit(user['owner_id'],identifier,body.content,body.revision,body.request_id)
    except (crud.CrudError,psycopg.Error,ValueError) as exc:raise error(exc) from None

@router.get('/conversations/{identifier}/analysis-jobs/{job_id}')
@guarded
def job_status(identifier:UUID,job_id:UUID,user=Depends(auth.identity)):
    from app.services import chat_jobs
    return chat_jobs.status(user['owner_id'],identifier,job_id)

@router.post('/conversations/{identifier}/analysis-jobs/{job_id}/resume',status_code=202)
async def resume_job(identifier:UUID,job_id:UUID,body:Action,user=Depends(auth.operator)):
    from app.services import chat_jobs
    try:return await chat_jobs.resume(user['owner_id'],identifier,job_id,body.revision)
    except (crud.CrudError,psycopg.Error,ValueError) as exc:raise error(exc) from None
@router.post('/conversations/{identifier}/messages')
async def send(identifier:UUID,body:Message,user=Depends(auth.operator)):
    try:return await service.send(user['owner_id'],identifier,body.content,body.revision)
    except (crud.CrudError,psycopg.Error,ValueError,KeyError,TypeError,httpx.HTTPError) as exc:
        log.warning('chat_turn_failed:%s',type(exc).__name__)
        raise error(exc) from None
@router.post('/conversations/{identifier}/articles/{article_id}/review')
@guarded
def review(identifier:UUID,article_id:UUID,body:Action,user=Depends(auth.operator)):
    if body.confirm is not True:raise HTTPException(422,'Confirmation explicite requise.')
    return service.review(user['owner_id'],identifier,article_id,body.revision)

@router.post('/conversations/{identifier}/partners/{partner_id}/review')
@guarded
def review_partner(identifier:UUID,partner_id:UUID,body:Action,user=Depends(auth.operator)):
    if body.confirm is not True:raise HTTPException(422,'Confirmation explicite requise.')
    return service.review_partner(user['owner_id'],identifier,partner_id,body.revision)

@router.post('/conversations/{identifier}/partners/{partner_id}/{action}')
@guarded
def supplier_action(identifier:UUID,partner_id:UUID,action:str,body:Action,user=Depends(auth.operator)):
    import requests
    from app.services.chat_supplier_actions import action as supplier_write
    from app.services.sage_soap import SageError
    from contextlib import nullcontext
    from app.services.chat_storage import execution_space
    try:
        with execution_space(user,identifier) if action=='execute' else nullcontext():
            return supplier_write(user['owner_id'],identifier,partner_id,action,body.revision,body.confirm,body.confirm_duplicates,body.confirm_draft_only_fields)
    except crud.CrudError as exc:
        messages={'stale_revision':'La fiche a changé ; relisez sa version actuelle.',
                  'human_review_required':'Relisez les données du fournisseur avant de préparer son enregistrement.',
                  'supplier_checks_or_duplicates_require_review':'Les contrôles fournisseur ou un risque de doublon demandent une vérification.',
                  'supplier_exact_fields_and_mapping_required':'Complétez les données exactes et validez leur correspondance Sage avant de préparer la création.',
                  'specific_confirmation_required':'Une approbation des données exactes préparées est nécessaire.',
                  'fresh_specific_approval_required':'Une nouvelle approbation spécifique est nécessaire ; aucune création automatique.',
                  'existing_attempt_requires_readback_no_retry':'Une tentative existe déjà : vérifiez son résultat avant toute nouvelle décision.',
                  'OB_read_only_no_creation':'Le dossier OB est exclusivement en lecture seule.'}
        detail=messages.get(exc.code,exc.code if exc.status==423 else 'Opération fournisseur indisponible pour cette version de la fiche. Vos données sont conservées.')
        raise HTTPException(exc.status,detail) from None
    except SageError as exc:raise HTTPException(exc.status,'Préparation fournisseur indisponible ; vérifications Sage requises.') from None
    except requests.RequestException:raise HTTPException(503,'Connexion Sage indisponible ; vos données sont conservées. Vérifiez le résultat avant toute nouvelle tentative.') from None
@router.post('/conversations/{identifier}/articles/{article_id}/{action}')
@guarded
def write(identifier:UUID,article_id:UUID,action:str,body:Action,user=Depends(auth.operator)):
    import requests
    from app.services.sage_soap import SageError
    from contextlib import nullcontext
    from app.services.chat_storage import execution_space
    try:
        with execution_space(user,identifier) if action.endswith('execute') else nullcontext():
            return service.write_action(user['owner_id'],identifier,article_id,action,body.revision,body.confirm,body.site)
    except SageError as exc:
        from app.services.article_execution import reason
        raise HTTPException(exc.status,'BLOQUÉ : article non créé. Cause : '+reason(exc.code)) from None
    except requests.RequestException:
        raise HTTPException(503,'Connexion Sage indisponible. Vos données sont conservées ; vérifiez toute tentative existante avant un nouvel envoi.') from None

@router.post('/conversations/{identifier}/messages/stream')
async def stream(identifier:UUID,body:Message,user=Depends(auth.operator)):
    import asyncio,json
    from fastapi.responses import StreamingResponse
    from app.services import chat_performance as perf
    try:
        current=await run_in_threadpool(service.read,user['owner_id'],identifier)
        if current['revision']!=body.revision:raise crud.CrudError('Conversation modifiée : rechargez-la.',409)
    except (crud.CrudError,psycopg.Error,ValueError,KeyError,TypeError) as exc:raise error(exc) from None
    async def events():
        queue=asyncio.Queue()
        async def emit(event,data):await queue.put({'event':event,'data':data})
        async def produce():
            token=perf.PROGRESS.set(emit)
            try:
                await emit('accepted',{'text':"J'analyse votre demande et je vérifie les informations Sage X3…"})
                result=await service.send(user['owner_id'],identifier,body.content,body.revision)
                for message in reversed(result.get('messages',[])):
                    if message['role']=='assistant':
                        await emit('text',{'text':message['content']});break
                await emit('result',result)
            except Exception as exc:await emit('error',{'detail':error(exc).detail})
            finally:perf.PROGRESS.reset(token);await queue.put(None)
        task=asyncio.create_task(produce())
        _STREAM_TASKS.add(task);task.add_done_callback(_STREAM_TASKS.discard)
        while True:
            item=await queue.get()
            if item is None:break
            yield 'data: '+json.dumps(item,ensure_ascii=False,default=str)+'\n\n'
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
_STREAM_TASKS=set()
