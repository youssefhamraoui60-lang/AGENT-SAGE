import asyncio,time,threading,logging,json
from collections import OrderedDict
from datetime import datetime,timezone
from app.services import business_store as db,chat_tools,conversation_chat as chat,sage_crud as crud,learning
from app.core.config import settings
from .catalog import CATALOG,UNAVAILABLE

_LOCK=threading.Lock();_COUNTS=OrderedDict()
log=logging.getLogger('agent_sage.mcp')
def authorize(owner,conversation):
    if not settings.sage_mcp_enabled:raise crud.CrudError('MCP pilote désactivé.',423)
    with db.connection() as conn:
        row=chat.get_row(conn,owner,conversation)
        if not conn.execute('SELECT id FROM chat_accounts WHERE id=%s AND active=true',(owner,)).fetchone():raise crud.CrudError('Compte indisponible.',403)
    state=row['state']
    if state.get('supplier_target','TEST')!='TEST' or any(p.get('dossier_cible','TEST')!='TEST' for p in state.get('partners',[])):
        raise crud.CrudError('Le pilote MCP est disponible uniquement dans TEST.',403)
    return row

def consume(owner):
    now=time.monotonic()
    with _LOCK:
        hits=[t for t in _COUNTS.pop(str(owner),[]) if now-t<60]
        if len(hits)>=20:raise crud.CrudError('Limite MCP : 20 appels par minute.',429)
        hits.append(now);_COUNTS[str(owner)]=hits
        while len(_COUNTS)>1024:_COUNTS.popitem(last=False)

async def dispatch(owner,conversation,name,arguments):
    started=time.perf_counter();status='unavailable'
    await asyncio.to_thread(authorize,owner,conversation)
    if name not in CATALOG:raise crud.CrudError('Outil MCP interdit ou inconnu.',403)
    schema,tool,mapping,_=CATALOG[name];args=schema.model_validate(arguments)
    consume(owner)
    values={target:getattr(args,source) for source,target in mapping.items()}
    if tool in ('get_supplier_record','check_supplier_fiscal_duplicates'):values['Folder']='TEST'
    try:
        # Reuse the existing pooled, predefined, parameterized SELECT connection.
        definition=None
        if tool=='live_stock':
            from app.services.learning_live import read
            result=await asyncio.wait_for(asyncio.to_thread(read,'stock',**values),timeout=settings.sage_mcp_timeout)
            definition=result.get('definition')
        else:
            body=await asyncio.wait_for(asyncio.to_thread(chat_tools.run,[{'id':'mcp','tool':tool,'args':values}]),timeout=settings.sage_mcp_timeout)
            result=body.get('mcp') or {}
        rows=result.get('rows',[])[:10] if result.get('ok') else []
        if not result.get('ok'):raise ValueError('read_unavailable')
        if result.get('folder','TEST')!='TEST':raise ValueError('folder_mismatch')
        if len(json.dumps(rows,default=str))>40000:raise ValueError('result_too_large')
        safe=[]
        for row in rows:
            safe.append({k:v for k,v in row.items() if not learning.SECRET.search(str(k)+' '+str(v))})
        status='ok'
        return {'ok':True,'tool':name,'folder':'TEST','source':'SQL TEST','checked_at':datetime.now(timezone.utc).isoformat(),'rows':safe,'truncated':len(result.get('rows',[]))>10,'writes':0,'authority':'data_only','cache_hit':bool(result.get('cache_hit')),'definition':definition,'training_excluded':True}
    except (TimeoutError,ValueError,OSError,crud.CrudError):
        return {'ok':False,'tool':name,'code':'sage_read_unavailable','folder':'TEST','rows':[],'writes':0,'authority':'data_only'}
    finally:
        log.info('mcp_read owner=%s conversation=%s tool=%s status=%s elapsed_ms=%s',owner,conversation,name,status,round((time.perf_counter()-started)*1000))

def manifest():return {'transport':['in_process','stdio'],'scope':'TEST','read_only':True,'tools':list(CATALOG),'unavailable':UNAVAILABLE,'arbitrary_sql':False,'writes':0}
