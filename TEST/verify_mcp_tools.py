"""Smoke every exposed MCP read against Sage TEST; never a write endpoint."""
import sys,asyncio,json
from pathlib import Path
from uuid import UUID
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
import httpx
from mcp import Client,StdioServerParameters
from http_test_account import authenticate_test_client
from app.services import business_store as db
BASE='http://127.0.0.1:8001'
async def main():
    owner=None
    with httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=40,trust_env=False) as http:
        try:
            a=authenticate_test_client(http);owner=UUID(a['user']['id']);http.headers['X-Chat-CSRF']=a['csrf']
            s=http.post('/api/v1/chat/conversations').json()
            params=StdioServerParameters(command=str(ROOT/'backend/.venv/Scripts/python.exe'),args=['-m','app.mcp_sage.stdio'],cwd=str(ROOT/'backend'),env={'SAGE_MCP_SESSION':http.cookies.get('sage_chat_session'),'SAGE_MCP_CSRF':a['csrf'],'SAGE_MCP_CONVERSATION':s['id'],'SAGE_MCP_BACKEND_PORT':'8001'})
            async with Client(params,read_timeout_seconds=35) as client:
                sites=await client.call_tool('sage_get_sites',{});site=str(sites.structured_content['rows'][0]['FCY_0']).strip()
                cases={'sage_search_suppliers':{'code':'F103'},'sage_get_supplier':{'code':'F103'},'sage_check_supplier_duplicates':{'name':'MCP_SMOKE_NO_MATCH'},'sage_search_customers':{'name':'MCP_SMOKE_NO_MATCH'},'sage_search_articles':{'name':'MCP_SMOKE_NO_MATCH'},'sage_get_article':{'code':'EXT_POUDRE'},'sage_get_categories':{'code':'MCP_NO_MATCH'},'sage_get_units':{'unit':'UN'},'sage_get_sites':{'site':site},'sage_get_tax_rules':{'rate':'20'},'sage_get_article_site':{'code':'EXT_POUDRE','site':site},'sage_get_stock':{'code':'EXT_POUDRE','site':site}}
                report={'sage_writes':0,'scope':'TEST','tools':[]}
                for name,args in cases.items():
                    r=await client.call_tool(name,args);body=r.structured_content or {}
                    row={'tool':name,'ok':body.get('ok') is True and body.get('folder')=='TEST' and body.get('writes')==0,'row_count':len(body.get('rows',[]))}
                    report['tools'].append(row);print(json.dumps(row),flush=True)
                report['passed']=all(row['ok'] for row in report['tools'])
                (ROOT/'TEST/mcp-tools-smoke-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        finally:
            if owner:
                with db.connection() as conn:
                    conn.execute("UPDATE chat_accounts SET active=false WHERE id=%s AND email LIKE 'verification-%%@example.test'",(owner,))
                    conn.execute('DELETE FROM chat_web_sessions WHERE owner_id=%s',(owner,))
if __name__=='__main__':asyncio.run(main())
