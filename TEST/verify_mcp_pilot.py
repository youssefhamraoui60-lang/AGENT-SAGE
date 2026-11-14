"""Real SDK stdio, existing SELECTs and real Qwen selection; no write endpoints."""
import sys,os,json,asyncio,time,statistics,secrets
from pathlib import Path
from uuid import UUID
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
import httpx
from mcp import Client,StdioServerParameters
from app.mcp_sage.server import build_server
from app.mcp_sage import client as agent
from app.services import business_store as db,chat_tools
from http_test_account import authenticate_test_client
BASE='http://127.0.0.1:8001'

async def verify():
    owner=None
    with httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=50,trust_env=False) as http:
        try:
            account=authenticate_test_client(http);owner=UUID(account['user']['id']);http.headers['X-Chat-CSRF']=account['csrf']
            s=http.post('/api/v1/chat/conversations').json();conversation=s['id']
            prefix='/api/v1/chat/conversations/'+conversation+'/mcp/tools'
            response=http.get(prefix);response.raise_for_status();assert response.json()['scope']=='TEST'
            params=StdioServerParameters(command=str(ROOT/'backend/.venv/Scripts/python.exe'),args=['-m','app.mcp_sage.stdio'],cwd=str(ROOT/'backend'),env={'SAGE_MCP_SESSION':http.cookies.get('sage_chat_session'),'SAGE_MCP_CSRF':account['csrf'],'SAGE_MCP_CONVERSATION':conversation,'SAGE_MCP_BACKEND_PORT':'8001'})
            async with Client(params,read_timeout_seconds=30) as client:
                tools=await client.list_tools();assert len(tools.tools)==12
                first=await client.call_tool('sage_get_supplier',{'code':'F103'})
                assert first.structured_content['ok'] and first.structured_content['writes']==0
                assert first.structured_content['rows']
                assert first.structured_content['folder']=='TEST'
                sites=await client.call_tool('sage_get_sites',{})
                assert sites.structured_content['ok'] and sites.structured_content['rows']
                site=str(sites.structured_content['rows'][0]['FCY_0']).strip()
                stock=await client.call_tool('sage_get_stock',{'code':'EXT_POUDRE','site':site})
                assert stock.structured_content['ok'] and stock.structured_content['training_excluded']
                # Same existing SELECT before/after: transport overhead only.
                baseline=[];mcp=[]
                for _ in range(3):
                    t=time.perf_counter();raw=await asyncio.to_thread(chat_tools.run,[{'id':'mcp','tool':'get_supplier_record','args':{'Supplier':'F103','Folder':'TEST'}}]);baseline.append((time.perf_counter()-t)*1000)
                    t=time.perf_counter();wrapped=await client.call_tool('sage_get_supplier',{'code':'F103'});mcp.append((time.perf_counter()-t)*1000)
                    assert wrapped.structured_content['rows']==raw['mcp']['rows'][:10]
                report={'stdio_discovery_and_call':'PASS','tools':len(tools.tools),'same_rows_before_after':True,'real_stock_read_ok':True,'stock_rows':len(stock.structured_content['rows']),'transport_only_benchmark':{'iterations':3,'existing_select_median_ms':round(statistics.median(baseline),2),'mcp_stdio_and_auth_median_ms':round(statistics.median(mcp),2),'sql_calls_per_read_before':1,'sql_calls_per_read_after':1},'qwen_cases':[],'sage_writes':0}
                for text,expected in [('Consulte le fournisseur F103','sage_get_supplier'),('rechrche le fourniseur AISSAOUI','sage_search_suppliers'),('Vérifie les doublons fournisseur ICE 001859517000047','sage_check_supplier_duplicates'),('Consulte cet article EXT_POUDRE','sage_get_article'),('Affiche le stock article EXT_POUDRE site '+site,'sage_get_stock')]:
                    t=time.perf_counter()
                    try:
                        async with asyncio.timeout(25):calls=await agent.select(text,tools.tools,{},[])
                        names=[c.get('function',{}).get('name') for c in calls]
                        passed=expected in names and len(calls)<=2 and all(agent.literal_identifiers(c.get('function',{}).get('arguments',{}),text,{},[]) for c in calls)
                        row={'expected':expected,'selected':names,'passed':passed,'elapsed_ms':round((time.perf_counter()-t)*1000,2)}
                    except Exception:row={'expected':expected,'passed':False,'error':'model_unavailable_or_timeout','elapsed_ms':round((time.perf_counter()-t)*1000,2)}
                    report['qwen_cases'].append(row);print(json.dumps(row),flush=True)
                report['qwen_selection_correct']=sum(r['passed'] for r in report['qwen_cases']);report['qwen_selection_total']=len(report['qwen_cases'])
                # Actual authenticated chat, no approval/execution route.
                t=time.perf_counter();message=http.post('/api/v1/chat/conversations/'+conversation+'/messages',json={'content':'Consulte le fournisseur F103','revision':s['revision']});message.raise_for_status();value=message.json()
                report['chat_read_completed']=value['state'].get('analysis_job',{}).get('status')=='completed'
                report['chat_mcp_calls']=value['state'].get('last_mcp_read',{}).get('calls')
                report['chat_elapsed_ms']=round((time.perf_counter()-t)*1000,2)
                assert report['chat_read_completed'] and not value['state'].get('_pending')
                smoke={'sage_search_suppliers':{'code':'F103'},'sage_get_supplier':{'code':'F103'},'sage_check_supplier_duplicates':{'name':'MCP_SMOKE_NO_MATCH'},'sage_search_customers':{'name':'MCP_SMOKE_NO_MATCH'},'sage_search_articles':{'name':'MCP_SMOKE_NO_MATCH'},'sage_get_article':{'code':'EXT_POUDRE'},'sage_get_categories':{'code':'MCP_NO_MATCH'},'sage_get_units':{'unit':'UN'},'sage_get_sites':{'site':site},'sage_get_tax_rules':{'rate':'20'},'sage_get_article_site':{'code':'EXT_POUDRE','site':site},'sage_get_stock':{'code':'EXT_POUDRE','site':site}}
                report['real_sage_tool_smoke']=[]
                for name,args in smoke.items():
                    result=await client.call_tool(name,args);body=result.structured_content or {}
                    report['real_sage_tool_smoke'].append({'tool':name,'ok':body.get('ok',False),'row_count':len(body.get('rows',[]))})
                print(json.dumps({'real_sage_tool_smoke':report['real_sage_tool_smoke']}),flush=True)
                # Revoked session stops a previously connected MCP client.
                http.post('/api/v1/chat/auth/logout').raise_for_status()
                denied=await client.call_tool('sage_get_supplier',{'code':'F103'})
                assert denied.is_error and not denied.structured_content['ok']
                report['logout_revokes_existing_stdio_client']=True
            (ROOT/'TEST/mcp-pilot-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False),flush=True)
        finally:
            if owner:
                with db.connection() as conn:
                    conn.execute("UPDATE chat_accounts SET active=false WHERE id=%s AND email LIKE 'verification-%%@example.test'",(owner,))
                    conn.execute('DELETE FROM chat_web_sessions WHERE owner_id=%s',(owner,))

if __name__=='__main__':asyncio.run(verify())
