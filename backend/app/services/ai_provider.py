"""Provider transport only: never tools, SQL, approvals or training authority."""
import asyncio,json,re,time,copy,threading
from decimal import Decimal
from functools import wraps
from contextvars import ContextVar
from uuid import uuid4
from urllib.parse import urlparse
import httpx,jsonschema
from app.core.config import settings
from app.services import business_store as db,chat_performance as performance
CONTEXT=ContextVar('ai_provider_context',default=None)
LOCAL_INFERENCE_SLOT=threading.Lock()

def scoped(fn):
    @wraps(fn)
    async def run(owner,identifier,*args,**kwargs):
        token=CONTEXT.set({'owner':owner,'conversation':identifier,'mode':'auto'})
        try:return await fn(owner,identifier,*args,**kwargs)
        finally:CONTEXT.reset(token)
    return run

def cloud_enabled():return settings.ai_provider=='deepseek' and (CONTEXT.get() or {}).get('mode')!='local'

def safe(value):
    value=str(value)
    key=settings.deepseek_api_key.get_secret_value()
    if key:value=value.replace(key,'[REDACTED]')
    return re.sub(r'\bsk-[A-Za-z0-9_-]{12,}\b','[REDACTED]',value)

def estimate(model,usage):
    if model=='deepseek-flash':hit,miss,out=map(Decimal,('0.006','0.3','1.2'))
    elif model=='deepseek-v4-pro':hit,miss,out=map(Decimal,('0.044','1.32','3.96'))
    else:return None
    if not all(type(usage.get(k)) is int and usage[k]>=0 for k in ('prompt_tokens','completion_tokens')):return None
    cached=min(usage.get('prompt_cache_hit_tokens',0),usage['prompt_tokens'])
    if type(cached) is not int or cached<0:cached=0
    return (Decimal(cached)*hit+Decimal(usage['prompt_tokens']-cached)*miss+Decimal(usage['completion_tokens'])*out)/Decimal(1000000)

def reserve(provider,model,purpose,reservation=Decimal(0)):
    ctx=CONTEXT.get() or {};identifier=uuid4()
    with db.connection() as conn:
        if provider=='deepseek':
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('deepseek-daily-budget'))")
            conn.execute("INSERT INTO chat_ai_budget(day) VALUES((now() AT TIME ZONE 'UTC')::date) ON CONFLICT DO NOTHING")
            used=conn.execute("SELECT used_usd FROM chat_ai_budget WHERE day=(now() AT TIME ZONE 'UTC')::date FOR UPDATE").fetchone()['used_usd']
            if used+reservation>Decimal(str(settings.ai_daily_budget_usd)):raise BudgetExceeded()
            conn.execute("UPDATE chat_ai_budget SET used_usd=used_usd+%s WHERE day=(now() AT TIME ZONE 'UTC')::date",(reservation,))
        conn.execute('INSERT INTO chat_ai_usage(id,owner_id,conversation_id,provider,model,purpose,status,reserved_cost_usd) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',(identifier,ctx.get('owner'),ctx.get('conversation'),provider,safe(model)[:128],purpose,'reserved',reservation))
    return identifier

class BudgetExceeded(Exception):pass

def normalize_optional_fiscal(content):
    data=json.loads(content)
    def visit(value):
        if isinstance(value,list):return [visit(v) for v in value]
        if not isinstance(value,dict):return value
        return {k:None if k in ('ice','identifiant_fiscal','rc') and isinstance(v,str) and v.strip().casefold() in ('','inconnu','inconnue','non renseigné','non renseigne','unknown','n/a') else visit(v) for k,v in value.items()}
    return json.dumps(visit(data),ensure_ascii=False)

def finish(identifier,status,elapsed,model=None,usage=None,http_status=None,error=None,cost=None):
    usage=usage or {}
    try:
        with db.connection() as conn:
            old=conn.execute('SELECT provider,created_at,COALESCE(estimated_cost_usd,reserved_cost_usd) AS charged FROM chat_ai_usage WHERE id=%s FOR UPDATE',(identifier,)).fetchone()
            if old and old['provider']=='deepseek' and cost is not None:
                conn.execute("UPDATE chat_ai_budget SET used_usd=greatest(0,used_usd+%s) WHERE day=(%s AT TIME ZONE 'UTC')::date",(cost-old['charged'],old['created_at']))
            conn.execute('UPDATE chat_ai_usage SET status=%s,duration_ms=%s,model=COALESCE(%s,model),input_tokens=%s,cached_tokens=%s,output_tokens=%s,http_status=%s,error_type=%s,estimated_cost_usd=%s WHERE id=%s',(status,round(elapsed*1000),model,usage.get('prompt_tokens'),usage.get('prompt_cache_hit_tokens'),usage.get('completion_tokens'),http_status,error,cost,identifier))
    except Exception:
        # A reserved cloud amount remains charged conservatively after a DB outage.
        performance.put('ai_usage_pending',True)

def remember(provider,model,elapsed,usage=None,cost=None,fallback=None):
    event={'provider':provider,'model':safe(model),'seconds':round(elapsed,3),'input_tokens':(usage or {}).get('prompt_tokens'),'output_tokens':(usage or {}).get('completion_tokens'),'estimated_cost_usd':str(cost) if cost is not None else None,'fallback_reason':fallback}
    ctx=CONTEXT.get()
    if ctx is not None:ctx.setdefault('calls',[]).append(event)
    performance.put('ai_provider',event)

async def complete(messages,*,schema=None,max_tokens=256,local=None,purpose='conversation',cloud_timeout=None,local_timeout=None):
    messages=[{'role':m['role'],'content':safe(m['content'])} for m in messages]
    # Bound cloud context. Provider data never includes SQL plans, permits or credentials.
    if sum(len(m['content']) for m in messages)>64000:raise ValueError('ai_context_limit')
    reason=None
    if cloud_enabled():
        started=time.monotonic();record=None;status=None;cloud_cost=None;cloud_usage=None
        try:
            url=urlparse(settings.deepseek_base_url)
            if url.scheme!='https' or url.hostname!='api.deepseek.com' or url.username or url.password or url.query or url.fragment:raise ValueError('invalid_provider_endpoint')
            key=settings.deepseek_api_key.get_secret_value()
            if not key:raise ValueError('missing_provider_key')
            limit=min(max_tokens,settings.ai_max_output_tokens)
            if schema:messages=messages+[{'role':'system','content':'JSON uniquement. Respecte ce schema: '+json.dumps(schema,separators=(',',':'))}]
            # UTF8 bytes upper-bound ordinary tokenization; reserve worst published peak rates.
            input_bound=sum(len(m['content'].encode('utf-8'))+64 for m in messages)+512
            held=(Decimal(input_bound)*Decimal('1.32')+Decimal(limit)*Decimal('3.96'))/Decimal(1000000)
            record=await asyncio.to_thread(reserve,'deepseek',settings.deepseek_model,purpose,held)
            body={'model':settings.deepseek_model,'messages':messages,'max_tokens':limit,'temperature':0,'stream':False,'thinking':{'type':'disabled'}}
            if schema:body['response_format']={'type':'json_object'}
            performance.add('ai_calls',1)
            budget=min(settings.deepseek_timeout_seconds,cloud_timeout or settings.deepseek_timeout_seconds)
            async with asyncio.timeout(budget),httpx.AsyncClient(timeout=budget,trust_env=False,follow_redirects=False) as client:
                response=await client.post(settings.deepseek_base_url.rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key},json=body)
            status=response.status_code;response.raise_for_status();data=response.json();usage=data.get('usage') or {};model=safe(data.get('model') or settings.deepseek_model)[:128]
            cost=estimate(model,usage);cloud_cost=cost;cloud_usage=usage;elapsed=time.monotonic()-started
            await asyncio.to_thread(finish,record,'succeeded',elapsed,model,usage,status,None,cost)
            content=data['choices'][0]['message']['content']
            if data['choices'][0].get('finish_reason')!='stop' or not isinstance(content,str) or not content.strip():raise ValueError('incomplete_provider_output')
            if schema:
                content=normalize_optional_fiscal(content)
                jsonschema.validate(json.loads(content),schema)
            remember('deepseek',model,elapsed,usage,cost)
            return {'message':{'content':safe(content)},'done':True,'done_reason':'stop','provider':'deepseek','model':model,'usage':usage}
        except asyncio.CancelledError:
            if record:await asyncio.to_thread(finish,record,'uncertain',time.monotonic()-started,None,None,status,'CancelledError',None)
            raise
        except Exception as exc:
            reason=type(exc).__name__
            if record:
                no_charge=cloud_cost if cloud_cost is not None else Decimal(0) if status in (400,401,402,403,404,422,429) else None
                await asyncio.to_thread(finish,record,'failed' if no_charge is not None else 'uncertain',time.monotonic()-started,None,cloud_usage,status,reason,no_charge)
            if settings.ai_fallback_provider!='ollama':raise httpx.RequestError('AI provider unavailable') from None
    started=time.monotonic()
    # Manual local mode and fallback never send anything to a remote provider here.
    if local:
        async with asyncio.timeout(min(settings.ai_timeout,local_timeout or 60)):result=await local()
    else:
        payload={'model':settings.ollama_model,'messages':messages,'stream':False,'options':{'temperature':0,'num_predict':min(max_tokens,settings.ai_max_output_tokens),'num_ctx':8192}}
        if schema:payload['format']=schema
        performance.add('ai_calls',1)
        # The installed 7B model runs on CPU. Never enqueue many requests
        # behind timed-out generations when cloud access is exhausted.
        if not LOCAL_INFERENCE_SLOT.acquire(blocking=False):raise httpx.RequestError('Local model busy; conversation retained')
        try:
            async with asyncio.timeout(min(settings.ai_timeout,local_timeout or 60)),httpx.AsyncClient(timeout=min(settings.ai_timeout,local_timeout or 60),trust_env=False) as client:
                response=await client.post(settings.ollama_url+'/api/chat',json=payload);response.raise_for_status();result=response.json()
        finally:LOCAL_INFERENCE_SLOT.release()
        if not result.get('done') or result.get('done_reason')=='length':raise ValueError('incomplete_local_output')
        if schema:
            result['message']['content']=normalize_optional_fiscal(result['message']['content'])
            jsonschema.validate(json.loads(result['message']['content']),schema)
    elapsed=time.monotonic()-started;usage={'prompt_tokens':result.get('prompt_eval_count'),'completion_tokens':result.get('eval_count')}
    try:
        record=await asyncio.to_thread(reserve,'ollama',settings.ollama_model,purpose)
        await asyncio.to_thread(finish,record,'succeeded',elapsed,None,usage,200,None,Decimal(0))
    except Exception:performance.put('ai_usage_pending',True)
    remember('ollama',settings.ollama_model,elapsed,usage,Decimal(0),reason)
    result['message']['content']=safe(result['message']['content'])
    result['provider']='ollama';return result

def complete_sync(messages,**kwargs):return asyncio.run(complete(messages,**kwargs))

async def tool_chat(messages,tools,*,max_tokens=900,require_tool=False):
    """Native function calling; transport only, never dispatch or Sage consent."""
    if len(messages)>45 or len(json.dumps(messages,ensure_ascii=False))>64000:raise ValueError('tool_context_limit')
    messages=json.loads(safe(json.dumps(messages,ensure_ascii=False)))
    reason=None
    if cloud_enabled():
        started=time.monotonic();record=None;status=None;usage=None;cost=None
        try:
            url=urlparse(settings.deepseek_base_url)
            if url.scheme!='https' or url.hostname!='api.deepseek.com' or url.username or url.password or url.query or url.fragment:raise ValueError('invalid_provider_endpoint')
            key=settings.deepseek_api_key.get_secret_value()
            if not key:raise ValueError('missing_provider_key')
            limit=min(max_tokens,settings.ai_max_output_tokens)
            bound=len(json.dumps([messages,tools],ensure_ascii=False).encode('utf-8'))+512
            held=(Decimal(bound)*Decimal('1.32')+Decimal(limit)*Decimal('3.96'))/Decimal(1000000)
            record=await asyncio.to_thread(reserve,'deepseek',settings.deepseek_model,'native_tool_chat',held)
            body={'model':settings.deepseek_model,'messages':messages,'tools':tools,'tool_choice':'required' if require_tool else 'auto','parallel_tool_calls':False,'max_tokens':limit,'temperature':0,'stream':False,'thinking':{'type':'disabled'}}
            performance.add('ai_calls',1)
            budget=min(settings.deepseek_timeout_seconds,settings.conversation_analysis_cloud_timeout)
            async with asyncio.timeout(budget),httpx.AsyncClient(timeout=budget,trust_env=False,follow_redirects=False) as client:
                r=await client.post(settings.deepseek_base_url.rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key},json=body)
            status=r.status_code;r.raise_for_status();data=r.json();usage=data.get('usage') or {};model=safe(data.get('model') or settings.deepseek_model);cost=estimate(model,usage)
            choice=data['choices'][0];message=choice['message']
            if choice.get('finish_reason') not in ('stop','tool_calls') or not isinstance(message,dict):raise ValueError('incomplete_tool_output')
            if not message.get('tool_calls') and not str(message.get('content') or '').strip():raise ValueError('empty_tool_output')
            await asyncio.to_thread(finish,record,'succeeded',time.monotonic()-started,model,usage,status,None,cost)
            remember('deepseek',model,time.monotonic()-started,usage,cost)
            return {'message':json.loads(safe(json.dumps(message,ensure_ascii=False))),'provider':'deepseek','model':model}
        except asyncio.CancelledError:
            if record:await asyncio.to_thread(finish,record,'uncertain',time.monotonic()-started,None,None,status,'CancelledError',None)
            raise
        except Exception as exc:
            reason=type(exc).__name__
            if record:await asyncio.to_thread(finish,record,'failed',time.monotonic()-started,None,usage,status,reason,cost if cost is not None else Decimal(0) if status in (400,401,402,403,404,422,429) else None)
            if settings.ai_fallback_provider!='ollama':raise httpx.RequestError('Tool provider unavailable') from None
    async def local_text():
        ctx=CONTEXT.get() or {};token=CONTEXT.set({**ctx,'mode':'local'})
        try:
            recent=[{'role':m['role'],'content':str(m.get('content') or '')[:400]} for m in messages if m['role'] in ('user','assistant') and m.get('content')][-2:]
            light=await complete([{'role':'system','content':'Tu es l’assistant ERP Sage X3. Article signifie produit ou service dans Sage, jamais texte, blog ou publicité. Réponds en français, une phrase de 20 mots maximum. Ne demande pas de prix sans exigence métier vérifiée. Ne propose aucune action Sage et n’invente aucune donnée ni résultat métier.'}]+recent,max_tokens=64,local_timeout=min(30,settings.conversation_analysis_local_timeout),purpose='native_text_fallback')
            return {**light,'text_only_fallback':True,'fallback_reason':reason}
        finally:CONTEXT.reset(token)
    if not settings.conversation_local_tool_calling_enabled:return await local_text()
    started=time.monotonic();performance.add('ai_calls',1)
    local_messages=copy.deepcopy(messages)
    for m in local_messages:
        for c in m.get('tool_calls',[]):
            if isinstance(c.get('function',{}).get('arguments'),str):c['function']['arguments']=json.loads(c['function']['arguments'])
    budget=settings.conversation_analysis_local_timeout
    try:
        async with asyncio.timeout(budget),httpx.AsyncClient(timeout=budget,trust_env=False) as client:
            r=await client.post(settings.ollama_url+'/api/chat',json={'model':settings.ollama_model,'messages':local_messages,'tools':tools,'stream':False,'options':{'temperature':0,'num_predict':max_tokens,'num_ctx':8192}})
            r.raise_for_status();data=r.json()
    except (TimeoutError,httpx.HTTPError) as exc:
        from app.services.chat_diagnostics import record as diagnostic
        diagnostic(exc,'native_local_tools')
        # One explicitly lighter local attempt. Never repeat the cloud request
        # or recursively restart the tool loop after native tools time out.
        return await local_text()
    if not data.get('done') or data.get('done_reason')=='length':raise ValueError('incomplete_local_tool_output')
    message=data['message'];usage={'prompt_tokens':data.get('prompt_eval_count'),'completion_tokens':data.get('eval_count')}
    record=await asyncio.to_thread(reserve,'ollama',settings.ollama_model,'native_tool_chat')
    await asyncio.to_thread(finish,record,'succeeded',time.monotonic()-started,settings.ollama_model,usage,200,None,Decimal(0))
    remember('ollama',settings.ollama_model,time.monotonic()-started,usage,Decimal(0),reason)
    return {'message':json.loads(safe(json.dumps(message,ensure_ascii=False))),'provider':'ollama','model':settings.ollama_model}

def summary(owner):
    with db.connection() as conn:
        rows=conn.execute("SELECT provider,count(*) AS calls,COALESCE(sum(input_tokens),0) AS input_tokens,COALESCE(sum(output_tokens),0) AS output_tokens,COALESCE(sum(estimated_cost_usd),0) AS estimated_cost_usd,count(*) FILTER(WHERE estimated_cost_usd IS NULL) AS pending_estimates,count(*) FILTER(WHERE status IN ('failed','uncertain')) AS failures,COALESCE(sum(reserved_cost_usd) FILTER(WHERE estimated_cost_usd IS NULL),0) AS reserved_or_unknown_cost_usd FROM chat_ai_usage WHERE owner_id=%s AND created_at>=now()-interval '30 days' GROUP BY provider",(owner,)).fetchall()
    return {'provider':settings.ai_provider,'fallback':settings.ai_fallback_provider,'configured':bool(settings.deepseek_api_key.get_secret_value()),'model':settings.deepseek_model if settings.ai_provider=='deepseek' else settings.ollama_model,'local_model':settings.ollama_model,'daily_budget_usd':settings.ai_daily_budget_usd,'usage_30_days':rows,'price_note':'Estimation USD aux tarifs de pointe du 05/11/2026, hors facture; les estimations absentes restent reservees.','price_source':'https://api-docs.deepseek.com/quick_start/pricing/'}
