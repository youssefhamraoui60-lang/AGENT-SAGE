"""Independent local SOB application; does not register routes in the existing agent."""
import asyncio
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from prepare import prepare
import creation
import learning_memory

@asynccontextmanager
async def learning_lifespan(application):
    await asyncio.to_thread(learning_memory.migrate)
    await asyncio.to_thread(learning_memory.seed)
    yield


app = FastAPI(title='SOB — API interne', version='1.0', docs_url=None, redoc_url=None, openapi_url=None,lifespan=learning_lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
sessions = {}
gate = asyncio.Semaphore(2)


@app.middleware('http')
async def local_session(request: Request, call_next):
    origin = request.headers.get('origin')
    if request.method not in ('GET', 'HEAD') and origin and origin != str(request.base_url).rstrip('/'):
        return JSONResponse({'detail': 'Origine refusée'}, status_code=403)
    now = time.monotonic()
    for key in list(sessions):
        if now - sessions[key]['seen'] > 8 * 3600:
            sessions.pop(key, None)
    token = request.cookies.get('sob_session')
    if token not in sessions:
        if len(sessions) >= 100:
            return JSONResponse({'detail': 'Trop de sessions'}, status_code=503)
        token = secrets.token_urlsafe(32)
        sessions[token] = {'seen': now, 'history': [], 'id': str(uuid4()), 'busy': False}
    request.state.sob = sessions[token]
    sessions[token]['seen'] = now
    response = await call_next(request)
    response.set_cookie('sob_session', token, httponly=True, samesite='strict', max_age=28800)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'"
    return response


class Message(BaseModel):
    message: str = Field(min_length=1, max_length=10000)


class Confirmation(BaseModel):
    review_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class ArticleLesson(BaseModel):
    model_config = {'str_strip_whitespace':True,'extra':'forbid'}
    alias: str = Field(min_length=1,max_length=80)
    code: str = Field(pattern=r'^[A-Z][A-Z0-9_./-]{0,39}$')

class PreparationCode(BaseModel):
    code:str=Field(pattern=r'^[a-f0-9]{32}$')

@app.post('/api/sob/preparations/load')
async def load_preparation(body:PreparationCode,request:Request):
    import drafts
    state=request.state.sob
    if state['busy'] or state.get('receipt'):raise HTTPException(409,'Ouvrir une nouvelle préparation ou attendre la réponse en cours.')
    state['busy']=True
    history=None
    try:
        actor=request.headers.get('x-sob-actor',state['id'])
        try:history=await asyncio.to_thread(drafts.claim,body.code,actor)
        except ValueError as exc:raise HTTPException(404,str(exc)) from None
        await asyncio.to_thread(creation.invalidate,state['id'])
        state.pop('review',None)
        async with gate,asyncio.timeout(180):details=await prepare(history,details=True)
        await asyncio.to_thread(drafts.save,state['id'],details,history)
        review=None;reply=details['reply']
        try:review=await asyncio.to_thread(creation.review,state['id'],details)
        except creation.CreationError as exc:reply+='\n\nValidation à préparer : '+str(exc)
        state['history']=history+[{'role':'assistant','content':reply}];state['review']=review;state['draft']=details
        return {'messages':state['history'],'review':review,'sage_writes':False}
    except HTTPException:raise
    except creation.CreationError as exc:raise HTTPException(409,str(exc)) from None
    except Exception:
        if history is None:raise HTTPException(503,'Chargement indisponible. Code conservé, aucune commande créée.') from None
        state['history']=history+[{'role':'assistant','content':'Vérification momentanément indisponible. Le brouillon source est conservé ; réessayer avec le même code. Aucune commande créée.'}]
        state['review']=None
        return {'messages':state['history'],'review':None,'sage_writes':False}
    finally:state['busy']=False


@app.get('/api/sob/learning')
async def learning():
    records=await asyncio.to_thread(learning_memory.rules)
    def count_examples():
        with learning_memory.db.connection() as conn:
            return conn.execute('SELECT status,count(*) AS count FROM sob_learning_examples GROUP BY status').fetchall()
    examples=await asyncio.to_thread(count_examples)
    return {'rules':records,'examples':examples,'storage':'PostgreSQL','sage_writes':False}


@app.post('/api/sob/learning/article-alias')
async def learn_article(body: ArticleLesson,request: Request):
    from prepare import lookup
    rows=await asyncio.to_thread(lookup,'article',body.code)
    if not any(row['ITMREF_0'].strip()==body.code for row in rows):
        raise HTTPException(422,'Code article introuvable dans Sage TEST.')
    identifier=await asyncio.to_thread(learning_memory.save,'article_alias',body.alias,{'code':body.code},
        actor='web:'+request.headers.get('x-sob-actor',request.state.sob['id']),source='Correction explicite interface SOB',approved=True)
    return {'saved':True,'id':identifier,'sage_writes':False}


@app.get('/api/sob/status')
async def status():
    from app.core.config import settings
    return {'service': 'SOB', 'mode': 'creation_after_validation', 'sage_writes': False,
            'creation_permissions': await asyncio.to_thread(creation.permissions),
            'provider': settings.ai_provider, 'model': settings.deepseek_model,
            'configured': bool(settings.deepseek_api_key.get_secret_value()),
            'defaults': {'company': '20', 'site': '201', 'order_type': 'SON'}}


@app.get('/api/sob/creation-permissions.sql')
async def permissions_sql():
    return FileResponse(Path(__file__).with_name('sage-sob-enable-creation.sql'), media_type='text/plain', filename='sage-sob-enable-creation.sql')


@app.get('/api/sob/conversation')
async def conversation(request: Request):
    state = request.state.sob
    return {'id': state['id'], 'messages': state['history'], 'review': state.get('review'), 'receipt': state.get('receipt'), 'busy': state['busy']}


@app.delete('/api/sob/conversation')
async def reset(request: Request):
    state = request.state.sob
    if state['busy']:
        raise HTTPException(409, 'Attendre la réponse en cours.')
    try:
        await asyncio.to_thread(creation.invalidate, state['id'])
    except creation.CreationError as exc:
        raise HTTPException(409, str(exc)) from None
    state.pop('review', None)
    state.pop('receipt', None)
    state['history'] = []
    state['id'] = str(uuid4())
    return {'id': state['id'], 'messages': []}


@app.post('/api/sob/chat')
async def chat(body: Message, request: Request):
    state = request.state.sob
    message = body.message.strip()
    if not message:
        raise HTTPException(422, 'Message vide.')
    if state.get('receipt'):
        raise HTTPException(409, 'Commande déjà créée. Utiliser Nouvelle préparation pour une autre commande.')
    if state['busy']:
        raise HTTPException(409, 'Une réponse est déjà en cours.')
    if len(state['history']) >= 24:
        raise HTTPException(409, 'Ouvrir une nouvelle préparation pour continuer.')
    state['busy'] = True
    try:
        await asyncio.to_thread(creation.invalidate, state['id'])
        state.pop('review', None)
        state.pop('receipt', None)
        candidate = state['history'] + [{'role': 'user', 'content': message}]
        if sum(len(m['content']) for m in candidate) > 40000:
            raise HTTPException(413, 'Conversation trop longue. Ouvrir une nouvelle préparation.')
        async with gate, asyncio.timeout(180):
            details = await prepare(candidate, details=True)
        reply = details['reply']
        import drafts
        await asyncio.to_thread(drafts.save,state['id'],details,candidate)
        state['draft']=details
        review = None
        try:
            review = await asyncio.to_thread(creation.review, state['id'], details)
        except creation.CreationError as exc:
            reply += '\n\nCréation : ' + str(exc)
        state['review'] = review
        state['history'] = candidate + [{'role': 'assistant', 'content': reply}]
        return {'reply': reply, 'review': review, 'sage_writes': False, 'conversation_id': state['id']}
    except HTTPException:
        raise
    except creation.CreationError as exc:
        raise HTTPException(409, str(exc)) from None
    except Exception:
        raise HTTPException(503, 'Préparation indisponible. Aucun brouillon modifié, aucune commande créée. Réessaie dans un instant.') from None
    finally:
        state['busy'] = False


@app.post('/api/sob/orders/confirm')
async def confirm(body: Confirmation, request: Request):
    state = request.state.sob
    if state['busy']:
        raise HTTPException(409, 'Une opération est déjà en cours.')
    review = state.get('review')
    if not review or review['id'] != body.review_id:
        raise HTTPException(409, 'Ce récapitulatif ne correspond plus à la conversation.')
    state['busy'] = True
    async def execute():
        try:
            receipt = await asyncio.to_thread(creation.confirm, state['id'], body.review_id, human_validated=True)
            state['receipt'] = receipt
            return receipt
        finally:
            state['busy'] = False
    task = asyncio.create_task(execute())
    try:
        # The task also owns the busy flag and receipt if the browser disconnects.
        return await asyncio.shield(task)
    except creation.CreationError as exc:
        raise HTTPException(409, str(exc)) from None
