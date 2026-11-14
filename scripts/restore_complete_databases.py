"""Restore private PostgreSQL backups into a new cluster, never an existing DB."""
import argparse,os,secrets,socket,subprocess,json
from pathlib import Path
import native_stack as stack

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--backup',type=Path,required=True)
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--port',type=int,default=55432)
    a=p.parse_args();a.backup=a.backup.resolve();a.data=a.data.resolve()
    if a.data.exists():raise SystemExit('Existing directory: restore refused')
    if not 1024<=a.port<=65535:raise SystemExit('Invalid port')
    with socket.socket() as s:
        if s.connect_ex(('127.0.0.1',a.port))==0:raise SystemExit('Port occupied: restore refused')
    inventory=json.loads((a.backup/'inventory.json').read_text(encoding='utf-8'))
    for name in inventory:
        if not all(ch.isalnum() or ch in '_-' for ch in name):raise ValueError('Invalid database name')
        if not (a.backup/(name+'.dump')).is_file():raise FileNotFoundError(name)
    if not (a.backup/'globals.sql').is_file():raise FileNotFoundError('globals.sql')
    user='backup_restore_'+secrets.token_hex(6);password=secrets.token_urlsafe(40)
    a.data.parent.mkdir(parents=True,exist_ok=True)
    pw=a.data.parent/(user+'.tmp');pw.write_text(password,encoding='ascii')
    env=os.environ.copy();env['PGPASSWORD']=password
    args=['-h','127.0.0.1','-p',str(a.port),'-U',user]
    def run(exe,*rest,**kw):
        return subprocess.run([str(stack.PG/exe),*rest],env=env,check=True,**kw)
    try:
        run('initdb.exe','-D',str(a.data),'-U',user,'--encoding=UTF8','--locale=C','--auth-host=scram-sha-256','--auth-local=scram-sha-256','--pwfile='+str(pw),stdout=subprocess.DEVNULL)
    finally:pw.unlink(missing_ok=True)
    with (a.data/'postgresql.conf').open('a',encoding='utf-8') as f:f.write("\nlisten_addresses='127.0.0.1'\nport="+str(a.port)+'\n')
    log=a.data.parent/(a.data.name+'-restore.log')
    with (a.data.parent/(a.data.name+'-control.log')).open('ab') as out:
        run('pg_ctl.exe','-D',str(a.data),'-l',str(log),'-w','start',stdout=out,stderr=out,stdin=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    restored={}
    try:
        run('psql.exe',*args,'-d','postgres','-v','ON_ERROR_STOP=1','-f',str(a.backup/'globals.sql'),stdout=subprocess.DEVNULL)
        for name in inventory:
            # postgres exists in every fresh cluster; other DBs are recreated
            # from the dump's original CREATE DATABASE attributes and ownership.
            if name=='postgres':run('pg_restore.exe',*args,'--exit-on-error','-d','postgres',str(a.backup/(name+'.dump')),stdout=subprocess.DEVNULL)
            else:run('pg_restore.exe',*args,'--exit-on-error','--create','-d','postgres',str(a.backup/(name+'.dump')),stdout=subprocess.DEVNULL)
            r=run('psql.exe',*args,'-d',name,'-tAc',"SELECT count(*) FROM pg_class WHERE relkind='r' AND relnamespace IN (SELECT oid FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname<>'information_schema')",capture_output=True,text=True)
            restored[name]={'tables':int(r.stdout.strip())}
        # Retain the cluster owner as a non-login role; no orphaned superuser login.
        run('psql.exe',*args,'-d','postgres','-v','ON_ERROR_STOP=1','-c','ALTER ROLE '+user+' NOLOGIN PASSWORD NULL',stdout=subprocess.DEVNULL)
    finally:
        run('pg_ctl.exe','-D',str(a.data),'-m','fast','-w','stop',stdout=subprocess.DEVNULL)
    result={'status':'PASS','restored':restored,'cluster':str(a.data),'port':a.port,'stopped':True}
    (a.data.parent/(a.data.name+'-restore-proof.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main()
