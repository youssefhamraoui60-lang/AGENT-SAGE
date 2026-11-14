"""MCP stdio endpoint. Existing login cookie/CSRF stay outside model arguments."""
import asyncio,os,sys,json
from uuid import UUID
import httpx
from mcp.server.stdio import stdio_server
from .server import build_server

async def main():
    session=os.environ.get('SAGE_MCP_SESSION','');csrf=os.environ.get('SAGE_MCP_CSRF','')
    conversation=str(UUID(os.environ['SAGE_MCP_CONVERSATION']))
    if not session or not csrf:raise ValueError('Existing authenticated chat session required')
    # No arbitrary remote URL, credentials or SQL connection is accepted here.
    port=os.environ.get('SAGE_MCP_BACKEND_PORT','8000')
    if port not in ('8000','8001'):raise ValueError('Local backend port required')
    base='http://127.0.0.1:'+port
    async with httpx.AsyncClient(base_url=base,cookies={'sage_chat_session':session},headers={'Origin':base,'X-Chat-CSRF':csrf},timeout=25,trust_env=False) as client:
        prefix='/api/v1/chat/conversations/'+conversation+'/mcp/tools'
        ready=await client.get(prefix);ready.raise_for_status()
        async def gateway(name,args):
            response=await client.post(prefix+'/'+name,json={'arguments':args});response.raise_for_status();return response.json()
        server=build_server(gateway)
        async with stdio_server() as (read,write):await server.run(read,write,server.create_initialization_options())

if __name__=='__main__':
    try:asyncio.run(main())
    except Exception:
        print('MCP indisponible : vérifiez le backend, le pilote TEST et votre session de chat.',file=sys.stderr);sys.exit(1)
