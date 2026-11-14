"""Pause this campaign's driver, drain requests, reload backend, always resume.

Never stops SQL Server, PostgreSQL, Ollama, or unrelated Python processes.
"""
import ctypes,json,subprocess,time,argparse,re
from pathlib import Path
from app.services import business_store as db

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--run',default='b26e71c4');parser.add_argument('--port',type=int,default=8000);args=parser.parse_args()
run=args.run;port=args.port
assert re.fullmatch('[a-f0-9]{8}',run) and port in (8000,8013)
def shell(cmd):return subprocess.run(['powershell.exe','-NoProfile','-Command',cmd],capture_output=True,text=True,check=True).stdout
drivers=json.loads(shell("@(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'run_100_article_sessions.py.*--run "+run+"' } | Select-Object -ExpandProperty ProcessId) | ConvertTo-Json -Compress"))
if isinstance(drivers,int):drivers=[drivers]
if not drivers:raise SystemExit('No exact campaign driver found')
kernel=ctypes.WinDLL('kernel32',use_last_error=True);native=ctypes.WinDLL('ntdll')
kernel.OpenProcess.restype=ctypes.c_void_p
kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
kernel.CloseHandle.argtypes=[ctypes.c_void_p]
native.NtSuspendProcess.argtypes=[ctypes.c_void_p];native.NtResumeProcess.argtypes=[ctypes.c_void_p]
handles=[];result={'run':run,'driver_pids':drivers,'reloaded':False}
try:
    for pid in drivers:
        handle=kernel.OpenProcess(0x0800,False,pid)
        if not handle:raise RuntimeError('Cannot open campaign process')
        handles.append(handle)
        if native.NtSuspendProcess(handle)!=0:raise RuntimeError('Cannot pause campaign process')
    allowed=set()
    for folder in (run,'d713a9f2'):
        for path in (root/'TEST/article-100-session-campaign'/folder).glob('ART-*/*.json'):
            item=json.loads(path.read_text(encoding='utf-8'))
            if item.get('conversation_id'):allowed.add(item['conversation_id'])
    for attempt in range(8):
        with db.connection() as conn:
            rows=conn.execute("SELECT id,state,updated_at < now()-interval '3 minutes' AS old FROM chat_conversations WHERE updated_at > now()-interval '1 hour'").fetchall()
        active=[r for r in rows if r['state'].get('_pending') and not (r['old'] and str(r['id']) in allowed)]
        writes=[r for r in rows if any(d.get('operation',{}).get('status') in ('executing','approved') for k in ('articles','partners','modification_drafts') for d in r['state'].get(k,[]))]
        if not active and not writes:break
        time.sleep(4)
    if active or writes:raise RuntimeError('Active analysis or approval: backend reload postponed')
    command="""$servers=Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'uvicorn app.main:app.*--port 8000' }; foreach($server in $servers){Stop-Process -Id $server.ProcessId -ErrorAction SilentlyContinue}; Start-Process -FilePath 'C:\\AGENT-SAGE-X3\\backend\\.venv\\Scripts\\python.exe' -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory 'C:\\AGENT-SAGE-X3\\backend' -WindowStyle Hidden -RedirectStandardOutput 'C:\\AGENT-SAGE-X3\\TEST\\article-campaign-server-out.log' -RedirectStandardError 'C:\\AGENT-SAGE-X3\\TEST\\article-campaign-server-err.log'"""
    command=command.replace('8000',str(port)).replace('article-campaign-server-out.log',f'article-campaign-{port}-server-out.log').replace('article-campaign-server-err.log',f'article-campaign-{port}-server-err.log')
    subprocess.run(['powershell.exe','-NoProfile','-Command',command],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=15)
    import httpx
    for _ in range(15):
        try:
            if httpx.get(f'http://127.0.0.1:{port}/sage/',timeout=2).status_code==200:break
        except Exception:pass
        time.sleep(.5)
    else:raise RuntimeError('Backend health check failed')
    result['reloaded']=True
finally:
    for handle in reversed(handles):native.NtResumeProcess(handle);kernel.CloseHandle(handle)
    (root/'TEST/article-100-session-campaign'/run/'rollout.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
