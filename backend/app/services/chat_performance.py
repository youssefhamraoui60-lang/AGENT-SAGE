"""Request-scoped timings, containing durations/counters only, never credentials."""
from contextvars import ContextVar
from functools import wraps
from time import perf_counter
CURRENT=ContextVar('chat_performance',default=None)
def add(name,value):
    metrics=CURRENT.get()
    if metrics is not None:metrics[name]=metrics.get(name,0)+round(value,3)
def put(name,value):
    metrics=CURRENT.get()
    if metrics is not None:metrics[name]=value
def measured(fn):
    @wraps(fn)
    async def call(*args,**kwargs):
        metrics={'ai_calls':0};token=CURRENT.set(metrics);started=perf_counter()
        try:
            result=await fn(*args,**kwargs)
            metrics['fastapi_service_ms']=round((perf_counter()-started)*1000,3)
            result['performance']=dict(metrics)
            return result
        finally:CURRENT.reset(token)
    return call

PROGRESS=ContextVar('chat_progress',default=None)
async def emit(event,data):
    callback=PROGRESS.get()
    if callback:await callback(event,data)
