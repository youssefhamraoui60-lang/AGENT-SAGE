import hmac
import logging
from uuid import UUID
import httpx
import psycopg
from fastapi import APIRouter,Depends,Header,HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from app.core.config import settings
from app.schemas.business import (AnalyzeInput,ValidateInput,DuplicateInput,CorrectionInput,
    DecisionInput,Proposal,RequestResult)
from app.services import business_ai as ai,business_engine as engine,business_store as store
from app.services.knowledge import suspicious

router=APIRouter(prefix='/api/v1/ai',tags=['Business proposals - no Sage execution'])
logger=logging.getLogger('agent_sage.business')

def translate(exc):
    if isinstance(exc,store.NotFound): return HTTPException(404,'Demande locale introuvable')
    if isinstance(exc,store.Conflict): return HTTPException(409,'Revision ou statut incompatible')
    if isinstance(exc,store.BusinessBlocked): return HTTPException(409,'Controle metier ou correction non satisfait')
    if isinstance(exc,psycopg.Error): return HTTPException(503,'Base locale indisponible')
    if isinstance(exc,httpx.TimeoutException): return HTTPException(504,'Delai du modele local depasse')
    if isinstance(exc,httpx.HTTPError): return HTTPException(503,'Modele local indisponible')
    if isinstance(exc,ai.InvalidModelOutput): return HTTPException(502,'Reponse du modele non conforme; aucune operation executee')
    if isinstance(exc,ValidationError): return HTTPException(422,'Correction ou proposition non conforme')
    logger.error('business_configuration_error',extra={'error_type':type(exc).__name__})
    return HTTPException(503,'Configuration metier locale indisponible')

def require_operator(x_approval_token: str | None=Header(default=None)):
    expected=settings.approval_token.get_secret_value()
    if not expected or not x_approval_token or not hmac.compare_digest(expected,x_approval_token):
        raise HTTPException(403,'Jeton operateur local requis')

@router.post('/analyze',response_model=RequestResult)
async def analyze(body: AnalyzeInput):
    request_id=None
    try:
        request_id=await run_in_threadpool(store.create_request,body.demande,
            {'prompt_version':ai.PROMPT_VERSION,'model':settings.ollama_model,'execution_sage_autorisee':False})
        rag,examples=await run_in_threadpool(engine.context,body.demande)
        if suspicious(body.demande):
            proposal=Proposal(intention='unknown',articles=[],fournisseurs=[],ambigu=True,
                questions=['Instructions non fiables detectees: reformuler la demande metier.'])
            provenance={'prompt_version':ai.PROMPT_VERSION,'model':None,'model_called':False,'reason':'untrusted_instruction_detected','retrieval':rag}
        else:
            proposal,provenance=await ai.analyze(body.demande,rag,examples)
        evaluation=await run_in_threadpool(engine.validate,proposal)
        await run_in_threadpool(store.complete_request,request_id,proposal.model_dump(),evaluation,provenance)
        return await run_in_threadpool(store.read_request,request_id)
    except (psycopg.Error,httpx.HTTPError,ai.InvalidModelOutput,ValidationError,ValueError,KeyError,OSError) as exc:
        if request_id is not None:
            try: await run_in_threadpool(store.fail_request,request_id,type(exc).__name__)
            except psycopg.Error: logger.error('business_failure_audit_unavailable')
        logger.warning('business_analysis_failed:%s',type(exc).__name__)
        error=translate(exc)
        if request_id is not None: error.headers={'X-Request-ID':str(request_id)}
        raise error from None

@router.post('/validate')
def validate(body: ValidateInput):
    try: return engine.validate(body.proposition)
    except (psycopg.Error,ValueError,OSError,KeyError) as exc: raise translate(exc) from None

@router.post('/check-duplicates')
def duplicates(body: DuplicateInput):
    try: return engine.duplicates(body.designation,body.type_objet,body.limit)
    except psycopg.Error as exc: raise translate(exc) from None

@router.get('/requests/{request_id}',response_model=RequestResult)
def read(request_id: UUID):
    try: return store.read_request(request_id)
    except (psycopg.Error,store.NotFound) as exc: raise translate(exc) from None

@router.post('/requests/{request_id}/corrections',response_model=RequestResult,dependencies=[Depends(require_operator)])
def correct(request_id: UUID,body: CorrectionInput):
    try: return engine.correct(request_id,body)
    except (psycopg.Error,store.NotFound,store.Conflict,store.BusinessBlocked,ValidationError,ValueError,OSError) as exc:
        raise translate(exc) from None

@router.post('/requests/{request_id}/decision',response_model=RequestResult,dependencies=[Depends(require_operator)])
def decide(request_id: UUID,body: DecisionInput):
    try: return engine.decide(request_id,body)
    except (psycopg.Error,store.NotFound,store.Conflict,store.BusinessBlocked,ValidationError,ValueError,OSError) as exc:
        raise translate(exc) from None

@router.get('/health')
async def health():
    try:
        def db_state():
            with store.connection() as conn:
                migration=conn.execute('SELECT version FROM schema_migrations ORDER BY version').fetchall()
                return {'schema':store.schema_name(),'migrations':[row['version'] for row in migration],
                    'reference_count':len(store.references(conn)),
                    'document_count':conn.execute('SELECT count(*) AS count FROM knowledge_documents WHERE synthetic=false').fetchone()['count']}
        state=await run_in_threadpool(db_state)
        async with httpx.AsyncClient(timeout=5,trust_env=False) as client:
            response=await client.get(settings.ollama_url+'/api/tags')
            response.raise_for_status()
            if settings.ollama_model not in [item['name'] for item in response.json()['models']]:
                raise ai.InvalidModelOutput('model_missing')
        return {'status':'ok','db':state,'model':settings.ollama_model,'execution_sage_autorisee':False,
            'rag_status':'empty_corpus' if not state['document_count'] else 'local_documents_available'}
    except (psycopg.Error,httpx.HTTPError,ai.InvalidModelOutput,ValueError) as exc:
        raise translate(exc) from None
