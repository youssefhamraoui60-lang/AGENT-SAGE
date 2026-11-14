"""Dedicated Ubuntu VM operations from Windows; SSH keys and verified host required.
No default Docker context is changed. Secrets are never printed.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
SSH_OPTIONS=['-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10']

def config():
    path=ROOT/'docker/vm.local.json'
    if not path.exists():
        raise SystemExit('BLOCKED: docker/vm.local.json absent; VM SSH access required. See docker/UBUNTU-VM.md')
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    if not re.fullmatch(r'[a-zA-Z0-9_@.:-]+',data['ssh_target']) or data['ssh_target'].startswith('-'):
        raise SystemExit('Invalid SSH target')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',data['remote_dir']):
        raise SystemExit('remote_dir must be a simple directory name relative to the SSH home')
    return data

def ssh(data,command,**kwargs):
    return subprocess.run(['ssh',*SSH_OPTIONS,data['ssh_target'],command],check=True,**kwargs)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['check','deploy','provision','start','stop','status','tunnel','backup','restart','logs','dbcheck','connectivity'])
    args=parser.parse_args()
    data=config()
    remote=data['remote_dir']
    dc='sudo -n docker compose -f compose.yaml -f compose.ubuntu-vm.yaml'
    prefix=f'cd {shlex.quote(remote)} && '
    if args.action=='check':
        ssh(data,'uname -a && cat /etc/os-release && command -v docker && sudo -n docker info && sudo -n docker compose version')
    elif args.action=='deploy':
        folder=ROOT/'backups'
        folder.mkdir(exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        archive=folder/f'vm-deploy-{stamp}.tar.gz'
        allowed=['compose.yaml','compose.ubuntu-vm.yaml','.env','database','workflows','scripts','backend','README.md']
        def filter_member(item):
            if any(part in ('.venv','__pycache__','.pytest_cache') for part in Path(item.name).parts): return None
            if item.name=='.env': item.mode=0o600
            return item
        with tarfile.open(archive,'x:gz') as tar:
            for name in allowed: tar.add(ROOT/name,arcname=name,filter=filter_member)
        # Stream archive over encrypted SSH, never place the secret bundle on a public share.
        with archive.open('rb') as handle:
            ssh(data,f'umask 077; mkdir {shlex.quote(remote)} && tar -xzf - -C {shlex.quote(remote)}',stdin=handle)
        print('Project copied to a new directory. No services started.')
    elif args.action=='provision':
        ssh(data,prefix+'sudo -n bash scripts/ubuntu-install-docker.sh')
    elif args.action=='tunnel':
        subprocess.run(['ssh',*SSH_OPTIONS,'-N','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=15',
                        '-o','ServerAliveCountMax=3','-L','127.0.0.1:55432:127.0.0.1:55432',
                        '-L','127.0.0.1:5678:127.0.0.1:5678',
                        '-R','127.0.0.1:18000:127.0.0.1:8000',data['ssh_target']],check=True)
    elif args.action=='dbcheck':
        sql="SELECT current_database(), count(*) FROM information_schema.tables WHERE table_schema='public';"
        inner='psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d n8n -c '+shlex.quote(sql)
        ssh(data,prefix+dc+' exec -T postgres sh -ec '+shlex.quote(inner))
    elif args.action=='connectivity':
        script="fetch('http://127.0.0.1:18000/health').then(async r=>{if(!r.ok)process.exit(1);console.log(await r.text())}).catch(()=>process.exit(1))"
        ssh(data,prefix+dc+' exec -T n8n node -e '+shlex.quote(script))
    elif args.action=='backup':
        completed=ssh(data,prefix+'sudo -n bash scripts/ubuntu-backup.sh',capture_output=True,text=True)
        print(completed.stdout)
        match=re.search(r'Backup created: (backups/[0-9TZ-]+\.tar\.gz)',completed.stdout)
        if not match: raise SystemExit('Remote backup path missing; inspect SSH output')
        folder=ROOT/'backups'
        folder.mkdir(exist_ok=True)
        target=folder/Path(match[1]).name
        with target.open('xb') as handle:
            ssh(data,prefix+'sudo -n cat '+shlex.quote(match[1]),stdout=handle)
        print(f'Backup copied locally: {target}')
    else:
        operations={'start':'config --quiet && '+dc+' up -d --wait --wait-timeout 240 postgres n8n',
                    'stop':'stop n8n postgres','status':'ps --all',
                    'restart':'restart postgres n8n && '+dc+' up -d --wait --wait-timeout 180 postgres n8n',
                    'logs':'logs --no-color --tail 200 postgres n8n'}
        ssh(data,prefix+dc+' '+operations[args.action])

if __name__=='__main__':
    main()
