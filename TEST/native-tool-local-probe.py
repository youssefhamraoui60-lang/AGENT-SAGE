"""Real native Ollama transport only; never dispatch a returned tool."""
import sys,asyncio,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import ai_provider,conversation_tools
async def main():
    token=ai_provider.CONTEXT.set({'mode':'local'});start=time.monotonic()
    try:
        result=await ai_provider.tool_chat([{'role':'system','content':'Tu es un assistant. Pour une salutation, utilise respond avec intent CHAT et une phrase courte.'},{'role':'user','content':'Bonjour'}],conversation_tools.TOOLS,max_tokens=100,require_tool=True)
        record={'status':'PASS','provider':result.get('provider'),'native_tool_calls':bool(result['message'].get('tool_calls')),'text_only_fallback':result.get('text_only_fallback',False),'message':result['message'],'seconds':round(time.monotonic()-start,3),'sage_writes':0,'cloud_calls':0}
    except Exception as exc:record={'status':'UNAVAILABLE','error_type':type(exc).__name__,'seconds':round(time.monotonic()-start,3),'sage_writes':0,'cloud_calls':0}
    finally:ai_provider.CONTEXT.reset(token)
    (ROOT/'TEST/native-tool-local-probe.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(record,ensure_ascii=True))
asyncio.run(main())
