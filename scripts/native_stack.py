"""Native local project services. No Windows service registration or system changes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import secrets

ROOT=Path(__file__).resolve().parents[1]
PG=ROOT/'.tools/postgresql-17/pgsql/bin'
DATA=ROOT/'runtime/postgres'
LOG=ROOT/'logs'
NODE=Path(os.environ['LOCALAPPDATA'])/'AGENT-SAGE-X3-tools/node-v24.20.0-win-x64/node.exe'
N8N=ROOT/'.tools/n8n/node_modules/n8n/bin/n8n'

def environment():
    values={}
    for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines():
        if line and not line.startswith('#') and '=' in line:
            key,value=line.split('=',1)
            values[key]=value
    return values

def pg_run(*args,**kwargs):
    if args[0]=='pg_ctl.exe' and 'start' in args:
        # Background postgres must not inherit PowerShell's output pipe, which
        # otherwise keeps the calling script waiting until the server stops.
        with (LOG/'pg-control.log').open('ab') as output:
            result=subprocess.run([str(PG/args[0]),*args[1:]],check=True,stdout=output,
                stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,**kwargs)
        print('pg_ctl start: PASS (details in logs/pg-control.log)',flush=True)
        return result
    return subprocess.run([str(PG/args[0]),*args[1:]],check=True,**kwargs)

def connect(database=None,autocommit=False,admin=False):
    import psycopg
    env=environment()
    return psycopg.connect(host='127.0.0.1',port=int(env['DB_PORT']),
        user='sage_admin' if admin else env['POSTGRES_USER'],
        password=env['NATIVE_PG_ADMIN_PASSWORD'] if admin else env['POSTGRES_PASSWORD'],
        dbname=database or env['POSTGRES_DB'],connect_timeout=5,autocommit=autocommit)

def init():
    from psycopg import sql
    env=environment()
    if 'NATIVE_PG_ADMIN_PASSWORD' not in env:
        with (ROOT/'.env').open('a',encoding='utf-8') as handle:
            handle.write('\nNATIVE_PG_ADMIN_PASSWORD='+secrets.token_hex(32)+'\n')
        env=environment()
    if DATA.exists():
        raise SystemExit('Existing data directory preserved; init refused')
    DATA.parent.mkdir(parents=True,exist_ok=True)
    password_file=ROOT/'runtime/init-password.tmp'
    password_file.write_text(env['NATIVE_PG_ADMIN_PASSWORD'],encoding='utf-8')
    try:
        pg_run('initdb.exe','-D',str(DATA),'-U','sage_admin','--encoding=UTF8','--locale=C',
            '--auth-host=scram-sha-256','--auth-local=scram-sha-256','--pwfile='+str(password_file))
    finally:
        password_file.unlink(missing_ok=True)
    with (DATA/'postgresql.conf').open('a',encoding='utf-8') as handle:
        handle.write("\nlisten_addresses = '127.0.0.1'\nport = "+env['DB_PORT']+"\npassword_encryption = 'scram-sha-256'\n")
    start_pg()
    with connect('postgres',autocommit=True,admin=True) as conn:
        for name,password in [(env['POSTGRES_USER'],env['POSTGRES_PASSWORD']),('n8n',env['N8N_DB_PASSWORD'])]:
            conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(name),sql.Literal(password)))
        conn.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(env['POSTGRES_DB']),sql.Identifier(env['POSTGRES_USER'])))
        conn.execute('CREATE DATABASE n8n OWNER n8n')
    with connect() as conn:
        conn.execute((ROOT/'database/001-schema.sql').read_text(encoding='utf-8-sig'))
    print('Native PostgreSQL initialized, dedicated non-superuser application roles, schema created')

def start_pg():
    pg_run('pg_ctl.exe','-D',str(DATA),'-l',str(LOG/'postgres-native.log'),'-w','start')

def n8n_env():
    env=os.environ.copy()
    values=environment()
    env.update(DB_TYPE='postgresdb',DB_POSTGRESDB_HOST='127.0.0.1',DB_POSTGRESDB_PORT=values['DB_PORT'],
        DB_POSTGRESDB_DATABASE='n8n',DB_POSTGRESDB_USER='n8n',DB_POSTGRESDB_PASSWORD=values['N8N_DB_PASSWORD'],
        N8N_ENCRYPTION_KEY=values['N8N_ENCRYPTION_KEY'],N8N_USER_FOLDER=str(ROOT/'runtime/n8n'),
        N8N_LISTEN_ADDRESS='127.0.0.1',N8N_HOST='localhost',N8N_PORT=values['N8N_PORT'],
        N8N_PROTOCOL='http',N8N_SECURE_COOKIE='false',N8N_DIAGNOSTICS_ENABLED='false',
        N8N_VERSION_NOTIFICATIONS_ENABLED='false',N8N_TEMPLATES_ENABLED='false',
        N8N_PERSONALIZATION_ENABLED='false',GENERIC_TIMEZONE='Europe/Paris',N8N_LOG_LEVEL='info',
        N8N_DISABLED_MODULES='mcp-registry')
    env['PATH']=str(NODE.parent)+os.pathsep+env['PATH']
    return env

def start_n8n():
    pidfile=ROOT/'runtime/n8n.pid'
    # A running listener is never replaced or killed by this function.
    import socket
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',int(environment()['N8N_PORT'])))==0:
            raise SystemExit('n8n port already used; start refused')
    with (LOG/'n8n-native-stdout.log').open('ab') as out,(LOG/'n8n-native-stderr.log').open('ab') as err:
        proc=subprocess.Popen([str(NODE),str(N8N),'start'],cwd=ROOT,env=n8n_env(),stdout=out,stderr=err,
            stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    pidfile.write_text(str(proc.pid),encoding='ascii')
    print(f'n8n started as user process PID {proc.pid}; check readiness separately')

def start_ollama():
    import socket
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',11434))==0:
            print('Existing Ollama listener preserved')
            return
    executable=Path(os.environ['LOCALAPPDATA'])/'Programs/Ollama/ollama.exe'
    if not executable.exists(): raise SystemExit('Existing Ollama installation not found')
    env=os.environ.copy()
    env['OLLAMA_HOST']='127.0.0.1:11434'
    with (LOG/'ollama-native-stdout.log').open('ab') as out,(LOG/'ollama-native-stderr.log').open('ab') as err:
        proc=subprocess.Popen([str(executable),'serve'],env=env,stdout=out,stderr=err,
            stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    (ROOT/'runtime/ollama.pid').write_text(str(proc.pid),encoding='ascii')
    print(f'Existing Ollama installation started locally, PID {proc.pid}')

def stop_n8n():
    pidfile=ROOT/'runtime/n8n.pid'
    if not pidfile.exists():
        raise SystemExit('No project n8n PID file; no process stopped')
    pid=int(pidfile.read_text())
    command=f"Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}' | Select-Object ExecutablePath,CommandLine | ConvertTo-Json -Compress"
    result=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,check=True)
    if not result.stdout.strip():
        print('Recorded n8n process already stopped')
        return
    info=json.loads(result.stdout)
    if (info.get('ExecutablePath') or '').lower()!=str(NODE).lower() or str(N8N).lower() not in (info.get('CommandLine') or '').lower():
        raise SystemExit('PID belongs to a different process; stop refused')
    subprocess.run(['taskkill','/PID',str(pid),'/T','/F'],check=True,capture_output=True)
    print('Only the recorded project n8n process tree stopped')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['init','start-pg','stop-pg','restart-pg','start-n8n','stop-n8n','start-ollama','n8n-cli'])
    args,extra=parser.parse_known_args()
    if args.action=='init': init()
    elif args.action=='start-pg': start_pg()
    elif args.action in ('stop-pg','restart-pg'):
        pg_run('pg_ctl.exe','-D',str(DATA),'-m','fast','-w','stop')
        if args.action=='restart-pg': start_pg()
    elif args.action=='start-n8n': start_n8n()
    elif args.action=='start-ollama': start_ollama()
    elif args.action=='stop-n8n': stop_n8n()
    elif args.action=='n8n-cli':
        subprocess.run([str(NODE),str(N8N),*extra],env=n8n_env(),cwd=ROOT,check=True)

if __name__=='__main__': main()
