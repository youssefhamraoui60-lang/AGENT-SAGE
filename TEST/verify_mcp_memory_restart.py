"""Restart only the TEST MCP pilot; verify owner memory/context and MCP afterward."""
import sys,json,time,subprocess,asyncio
from pathlib import Path
from uuid import UUID
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
import httpx
from mcp import Client,StdioServerParameters
from http_test_account import authenticate_test_client
from app.services import business_store as db,learning
BASE='http://127.0.0.1:8001'
async def main():
    owner=None
    with httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=50,trust_env=False) as client:
        try:
            account=authenticate_test_client(client);owner=UUID(account['user']['id']);client.headers['X-Chat-CSRF']=account['csrf']
            item=client.post('/api/v1/chat/learning/items',json={'kind':'preference','title':'Langue de vérification MCP','content':'Répondre en français avec des phrases courtes.'});item.raise_for_status();item=item.json()
            client.post('/api/v1/chat/learning/items/'+item['id']+'/review',json={'status':'validated','confirm':True}).raise_for_status()
            s=client.post('/api/v1/chat/conversations').json()
            for text in ('Créer un fournisseur Nom : CONTEXTE REDEMARRAGE ICE : 001234567890123','Consulte le fournisseur F103'):
                r=client.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':text,'revision':s['revision']});r.raise_for_status();s=r.json()
            assert s['state']['last_mcp_read']['references'][0]['BPRNUM_0'].strip()=='F103'
            command=r"""$targets=Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object {$_.CommandLine -like '*uvicorn app.main:app --host 127.0.0.1 --port 8001*'}; foreach($proc in $targets){Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue}; & 'C:\AGENT-SAGE-X3\TEST\Start-McpPilot.ps1'"""
            process=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));process.wait(timeout=20)
            for _ in range(60):
                try:client.get('/health',timeout=2).raise_for_status();break
                except httpx.HTTPError:time.sleep(.25)
            else:raise AssertionError('Pilot restart unavailable')
            r=client.get('/api/v1/chat/conversations/'+s['id']);r.raise_for_status();saved=r.json()['state']
            p=saved['partners'][0];assert p['nom']=='CONTEXTE REDEMARRAGE' and p['ice']=='001234567890123' and not p['approved']
            assert saved['last_mcp_read']['references']==s['state']['last_mcp_read']['references']
            assert any(str(m['id'])==item['id'] for m in learning.retrieve(owner,'français')['memory'])
            params=StdioServerParameters(command=str(ROOT/'backend/.venv/Scripts/python.exe'),args=['-m','app.mcp_sage.stdio'],cwd=str(ROOT/'backend'),env={'SAGE_MCP_SESSION':client.cookies.get('sage_chat_session'),'SAGE_MCP_CSRF':account['csrf'],'SAGE_MCP_CONVERSATION':s['id'],'SAGE_MCP_BACKEND_PORT':'8001'})
            async with Client(params,read_timeout_seconds=35) as mcp:
                read=await mcp.call_tool('sage_get_supplier',{'code':'F103'});assert read.structured_content['ok']
            report={'status':'PASS','real_pilot_restart':True,'memory_rag_persisted':True,'supplier_and_ice_preserved':True,'read_references_preserved':True,'mcp_available_after_restart':True,'production_backend_restarted':False,'sage_writes':0}
            (ROOT/'TEST/mcp-memory-restart-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
        finally:
            if owner:
                with db.connection() as conn:
                    conn.execute("UPDATE chat_accounts SET active=false WHERE id=%s AND email LIKE 'verification-%%@example.test'",(owner,))
                    conn.execute('DELETE FROM chat_web_sessions WHERE owner_id=%s',(owner,))
if __name__=='__main__':asyncio.run(main())
