"""Backup native project state and optionally validate dumps in a new isolated cluster."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import zipfile
import native_stack as stack

def command(exe,*args,password,**kwargs):
    env=os.environ.copy()
    env['PGPASSWORD']=password
    return subprocess.run([str(stack.PG/exe),*args],env=env,check=True,**kwargs)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--validate-restore',action='store_true')
    args=parser.parse_args()
    root=stack.ROOT
    values=stack.environment()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder=root/'backups'/('native-'+stamp)
    folder.mkdir(exist_ok=False)
    stack.stop_n8n()
    try:
        for database,filename,user,password in [
            (values['POSTGRES_DB'],'backend.dump',values['POSTGRES_USER'],values['POSTGRES_PASSWORD']),
            ('n8n','n8n.dump','n8n',values['N8N_DB_PASSWORD'])]:
            command('pg_dump.exe','-h','127.0.0.1','-p',values['DB_PORT'],'-U',user,'-d',database,'-Fc','-f',str(folder/filename),password=password)
        shutil.copy2(root/'.env',folder/'environment.env')
        shutil.copytree(root/'runtime/n8n',folder/'n8n-home')
        for name in ['package.json','package-lock.json']:
            shutil.copy2(root/'.tools/n8n'/name,folder/('n8n-'+name))
        with zipfile.ZipFile(folder/'source.zip','x',compression=zipfile.ZIP_DEFLATED) as archive:
            excluded={'.tools','runtime','backups','.git','.venv','__pycache__','.pytest_cache','logs','models','node_modules'}
            for current,directories,files in os.walk(root):
                directories[:]=[name for name in directories if name not in excluded]
                for name in files:
                    file=Path(current)/name
                    relative=file.relative_to(root)
                    if relative.as_posix() in {'.env','docker/vm.local.json'}: continue
                    archive.write(file,relative.as_posix())
        hashes={file.relative_to(folder).as_posix():hashlib.sha256(file.read_bytes()).hexdigest()
                for file in folder.rglob('*') if file.is_file()}
        (folder/'manifest.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    finally:
        stack.start_n8n()
    proof={'backup':str(folder),'status':'PASS','files':len(hashes),'restore':'SKIPPED'}
    if args.validate_restore:
        import psycopg
        from psycopg import sql
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',55433))==0:
                raise SystemExit('Restore port occupied; original services preserved')
        target=root/'runtime'/('restore-validation-'+stamp)
        target.mkdir(exist_ok=False)
        cluster=target/'postgres'
        pw=target/'init-password.tmp'
        pw.write_text(values['NATIVE_PG_ADMIN_PASSWORD'],encoding='utf-8')
        try:
            stack.pg_run('initdb.exe','-D',str(cluster),'-U','sage_admin','--encoding=UTF8','--locale=C',
                '--auth-host=scram-sha-256','--auth-local=scram-sha-256','--pwfile='+str(pw))
        finally:
            pw.unlink(missing_ok=True)
        with (cluster/'postgresql.conf').open('a') as handle:
            handle.write("\nlisten_addresses = '127.0.0.1'\nport = 55433\n")
        stack.pg_run('pg_ctl.exe','-D',str(cluster),'-l',str(target/'postgres.log'),'-w','start')
        try:
            with psycopg.connect(host='127.0.0.1',port=55433,user='sage_admin',password=values['NATIVE_PG_ADMIN_PASSWORD'],dbname='postgres',autocommit=True) as conn:
                for user,password in [(values['POSTGRES_USER'],values['POSTGRES_PASSWORD']),('n8n',values['N8N_DB_PASSWORD'])]:
                    conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(user),sql.Literal(password)))
                for database,owner in [(values['POSTGRES_DB'],values['POSTGRES_USER']),('n8n','n8n')]:
                    conn.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(database),sql.Identifier(owner)))
            for database,filename in [(values['POSTGRES_DB'],'backend.dump'),('n8n','n8n.dump')]:
                command('pg_restore.exe','--exit-on-error','-h','127.0.0.1','-p','55433','-U','sage_admin','-d',database,str(folder/filename),password=values['NATIVE_PG_ADMIN_PASSWORD'])
            counts={}
            for database,table in [(values['POSTGRES_DB'],'agent_execution_logs'),('n8n','workflow_entity')]:
                with psycopg.connect(host='127.0.0.1',port=55433,user='sage_admin',password=values['NATIVE_PG_ADMIN_PASSWORD'],dbname=database) as conn:
                    count=conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]
                with stack.connect(database,admin=True) as conn:
                    original=conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]
                assert count==original,(database,count,original)
                counts[database]=count
            shutil.copytree(folder/'n8n-home',target/'n8n-home')
            for name,digest in hashes.items():
                if name.startswith('n8n-home/'):
                    assert hashlib.sha256((target/name).read_bytes()).hexdigest()==digest,name
            proof.update(restore='PASS',restored_row_counts=counts,restore_directory=str(target))
        finally:
            stack.pg_run('pg_ctl.exe','-D',str(cluster),'-m','fast','-w','stop')
    (root/'logs/native-backup-tests.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
    print(json.dumps(proof,indent=2))

if __name__=='__main__': main()
