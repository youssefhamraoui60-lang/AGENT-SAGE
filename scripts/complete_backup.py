"""Private, self contained Windows backup. Never uploads private contents."""
import hashlib,json,os,sqlite3,subprocess,sys,time,zipfile,shutil,urllib.request,socket
from pathlib import Path
from datetime import datetime,timezone
import native_stack as stack
from concurrent.futures import ThreadPoolExecutor

ROOT=stack.ROOT
BASE=Path('C:/AGENT-SAGE-BACKUPS')
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
OUT=Path(os.environ.get('AGENT_BACKUP_RESUME_PATH',str(BASE/('AGENT-SAGE-COMPLET-'+STAMP)))).resolve()
if OUT.parent!=BASE or not OUT.name.startswith('AGENT-SAGE-COMPLET-'):raise ValueError('Invalid backup path')

def run(args,**kw):
    return subprocess.run([str(a) for a in args],check=True,**kw)

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    OUT.mkdir(parents=True,exist_ok=bool(os.environ.get('AGENT_BACKUP_RESUME_PATH')))
    # Limit inheritance before any secrets are written.
    run(['icacls',OUT,'/inheritance:r','/grant:r',os.environ['USERDOMAIN']+'\\'+os.environ['USERNAME']+':(OI)(CI)F','*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F'],stdout=subprocess.DEVNULL)
    state={'started_utc':datetime.now(timezone.utc).isoformat(),'output':str(OUT),'status':'RUNNING'}
    def progress(**kw):
        state.update(kw);(OUT/'progress.json').write_text(json.dumps(state,indent=2,default=str),encoding='utf-8')
        print(json.dumps(kw,ensure_ascii=True),flush=True)
    env=stack.environment();pg_env=os.environ.copy();pg_env['PGPASSWORD']=env['NATIVE_PG_ADMIN_PASSWORD']
    pg_args=['-h','127.0.0.1','-p',env['DB_PORT'],'-U','sage_admin']
    dbdir=OUT/'database';dbdir.mkdir(exist_ok=True)
    # Numerous historical test schemas exceed the live server's lock budget
    # for one pg_dump. Clone via the PostgreSQL backup protocol, then dump the
    # isolated clone with a larger lock table. The live service is not restarted.
    clone=dbdir/'physical-postgres';clone_port=55435
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',clone_port))==0:raise RuntimeError('Backup validation port occupied')
    progress(phase='consistent_physical_snapshot')
    if not (clone/'backup_manifest').exists():
        run([stack.PG/'pg_basebackup.exe',*pg_args,'-D',clone,'-X','stream','-c','fast'],env=pg_env,stdout=subprocess.DEVNULL)
    with (OUT/'clone-control.log').open('ab') as log:
        run([stack.PG/'pg_ctl.exe','-D',clone,'-l',OUT/'clone-server.log','-o','-p '+str(clone_port)+' -c max_locks_per_transaction=2048 -c listen_addresses=127.0.0.1','-w','start'],stdout=log,stderr=log,stdin=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    pg_args=['-h','127.0.0.1','-p',str(clone_port),'-U','sage_admin']
    with stack.connect('postgres',admin=True) as c:
        databases=[r[0] for r in c.execute("SELECT datname FROM pg_database WHERE NOT datistemplate ORDER BY datname")]
    run([stack.PG/'pg_dumpall.exe',*pg_args,'--globals-only','-f',dbdir/'globals.sql'],env=pg_env,stdout=subprocess.DEVNULL)
    inventories={}
    for name in databases:
        if not all(ch.isalnum() or ch in '_-' for ch in name):raise ValueError('Unexpected database name')
        run([stack.PG/'pg_dump.exe',*pg_args,'-d',name,'-Fc','-f',dbdir/(name+'.dump')],env=pg_env,stdout=subprocess.DEVNULL)
        toc=run([stack.PG/'pg_restore.exe','-l',dbdir/(name+'.dump')],capture_output=True)
        (dbdir/(name+'-toc.txt')).write_bytes(toc.stdout)
        inventories[name]={'dump_bytes':(dbdir/(name+'.dump')).stat().st_size,'toc_verified':True}
        progress(database_dumped=name)
    run([stack.PG/'pg_ctl.exe','-D',clone,'-m','fast','-w','stop'],stdout=subprocess.DEVNULL)
    (dbdir/'inventory.json').write_text(json.dumps(inventories,indent=2),encoding='utf-8')
    software=OUT/'inventory';software.mkdir(exist_ok=True)
    for label,python in [('backend',ROOT/'backend/.venv/Scripts/python.exe'),('telegram',ROOT/'telegram-test/.venv/Scripts/python.exe')]:
        r=run([python,'-m','pip','freeze'],capture_output=True)
        (software/(label+'-requirements.lock.txt')).write_bytes(r.stdout)
    try:
        models=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=15))
        (software/'ollama-models.json').write_text(json.dumps(models,indent=2),encoding='utf-8')
    except Exception as e:progress(ollama_inventory_error=type(e).__name__)
    sqlite_dir=OUT/'sqlite-snapshots';sqlite_dir.mkdir(exist_ok=True)
    snapshots={};sqlite_checks={}
    for current,dirs,files in os.walk(ROOT/'runtime'):
        dirs[:]=[d for d in dirs if d!='postgres' and not d.startswith('restore-validation-')]
        for name in files:
            src=Path(current)/name
            if src.suffix not in ('.sqlite','.sqlite3','.session','.db'):continue
            try:
                with src.open('rb') as f:header=f.read(16)
                if header!=b'SQLite format 3\x00':continue
                relative=src.relative_to(ROOT);dest=sqlite_dir/relative;dest.parent.mkdir(parents=True,exist_ok=True)
                a=sqlite3.connect(src.as_uri()+'?mode=ro',uri=True,timeout=30);b=sqlite3.connect(dest)
                try:
                    a.backup(b);check=b.execute('PRAGMA integrity_check').fetchone()[0]
                    if check!='ok':raise ValueError(check)
                finally:a.close();b.close()
                snapshots[str(src)]=dest;sqlite_checks[relative.as_posix()]=check
            except Exception as e:
                raise RuntimeError('SQLite snapshot failed: '+str(src)) from e
    progress(sqlite_snapshots=len(snapshots))
    (software/'sqlite-checks.json').write_text(json.dumps(sqlite_checks,indent=2),encoding='utf-8')
    local=Path(os.environ['LOCALAPPDATA'])
    sources=[(ROOT,'application'),(local/'AGENT-SAGE-X3-tools','software/windows-tools'),
        (local/'Python/pythoncore-3.15-64','software/python315'),
        (local/'Programs/Ollama','software/ollama'),(Path.home()/'.ollama/models','software/ollama-models')]
    # Private source data stays in this archive, including .env, certs and sessions.
    archive_path=OUT.with_suffix('.zip');manifest=[];omissions=[];changed=[]
    started=time.monotonic()
    with zipfile.ZipFile(archive_path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
        run(['icacls',archive_path,'/inheritance:r','/grant:r',os.environ['USERDOMAIN']+'\\'+os.environ['USERNAME']+':F','*S-1-5-18:F','*S-1-5-32-544:F'],stdout=subprocess.DEVNULL)
        def add(src,arc,prepared=None):
            before=prepared[0] if prepared else src.stat();original=src;src=snapshots.get(str(src),src)
            h=hashlib.sha256();size=0
            info=zipfile.ZipInfo(arc);info.compress_type=zipfile.ZIP_DEFLATED
            info._compresslevel=1
            if '/ollama-models/blobs/' in arc or src.suffix.lower() in ('.zip','.7z','.gz','.png','.jpg','.jpeg','.pdf','.mp4','.dump'):info.compress_type=zipfile.ZIP_STORED
            if prepared:
                data=prepared[2];h.update(data);size=len(data)
                z.writestr(info,data)
            else:
                with src.open('rb') as inp,z.open(info,'w',force_zip64=True) as out:
                    for data in iter(lambda:inp.read(1024*1024),b''):out.write(data);h.update(data);size+=len(data)
            manifest.append({'path':arc,'bytes':size,'sha256':h.hexdigest(),'sqlite_snapshot':str(original) in snapshots})
            after=prepared[1] if prepared else original.stat()
            if str(original) not in snapshots and (before.st_mtime_ns!=after.st_mtime_ns or before.st_size!=after.st_size):changed.append(arc)
        def preload(item):
            src,arc=item
            try:
                before=src.stat()
                if before.st_size>4*1024*1024:return src,arc,None,None
                data=snapshots.get(str(src),src).read_bytes()
                return src,arc,(before,src.stat(),data),None
            except OSError as e:return src,arc,None,e
        def source_files(source,prefix):
            if not source.exists():raise FileNotFoundError(source)
            for current,dirs,files in os.walk(source):
                current=Path(current)
                if source==ROOT and current==ROOT/'runtime':
                    if 'postgres' in dirs:dirs.remove('postgres');omissions.append({'path':'application/runtime/postgres','reason':'Live physical cluster replaced by consistent PostgreSQL logical dumps of all databases and roles.'})
                for name in files:
                    src=current/name;rel=src.relative_to(source);arc=prefix+'/'+rel.as_posix()
                    if src.name.endswith(('-wal','-shm','-journal')) and any(str(src).startswith(k) for k in snapshots):
                        omissions.append({'path':arc,'reason':'SQLite journal incorporated in consistent snapshot.'});continue
                    yield src,arc
        for source,prefix in sources:
            with ThreadPoolExecutor(max_workers=16) as pool:
                for src,arc,prepared,error in pool.map(preload,source_files(source,prefix),buffersize=48):
                    try:
                        if error:raise error
                        add(src,arc,prepared)
                    except (PermissionError,FileNotFoundError) as e:
                        if src.suffix in ('.pid','.log') or src.name.endswith('.lock'):
                            omissions.append({'path':arc,'reason':'Transient runtime file: '+type(e).__name__});continue
                        raise
                    if len(manifest)%10000==0:progress(files_archived=len(manifest),zip_bytes=archive_path.stat().st_size,elapsed_seconds=round(time.monotonic()-started))
            progress(component_archived=prefix,files_archived=len(manifest))
        for name in ['SOB-MESSAGES-AVEC-CORRECTIONS-OB.xlsx','BC N_ 088 OULD BOUAZZA OKD CIMENT.pdf']:
            document=Path.home()/'Desktop'/name
            if document.exists():add(document,'documents-utilisateur/'+name)
            else:omissions.append({'path':str(document),'reason':'Previously referenced desktop file not present at capture time.'})
        for folder in [dbdir,software]:
            for p in folder.rglob('*'):
                if p.is_file():add(p,'backup/'+p.relative_to(OUT).as_posix())
        report={'databases':inventories,'sqlite_databases':sqlite_checks,'omissions':omissions,'files_changed_during_capture':changed,
            'external_sage_database':'Remote SQL Server x3v12 is not dumped. Sage SQL integration source is included; separate DBA .bak required to move the ERP itself.',
            'scope':'Entire local application tree, all local PostgreSQL databases/roles, runtime, history, documents, secrets, portable tools, Python, Ollama binaries and model weights. Windows OS, registered components, DPAPI master keys and Sage licensed server are not portable.',
            'warning':'PRIVATE UNENCRYPTED ZIP. Never publish. DPAPI credentials need recreation on new Windows user/machine; activate only one Telegram/email worker.'}
        z.writestr('backup/REPORT.json',json.dumps(report,ensure_ascii=False,indent=2))
        z.writestr('backup/MANIFEST-SHA256.json',json.dumps(manifest,ensure_ascii=False,separators=(',',':')))
    progress(phase='verifying_zip_crc',archive=str(archive_path))
    with zipfile.ZipFile(archive_path) as z:
        bad=z.testzip()
        if bad:raise RuntimeError('ZIP CRC failed '+bad)
        assert 'application/.env' in z.namelist()
        assert all('backup/database/'+n+'.dump' in z.namelist() for n in databases)
    sha=digest(archive_path)
    archive_path.with_suffix('.zip.sha256').write_text(sha+'  '+archive_path.name+'\n',encoding='ascii')
    progress(status='PASS',files_archived=len(manifest),archive_bytes=archive_path.stat().st_size,sha256=sha,changed_files=len(changed),omissions=len(omissions),zip_crc_verified=True)

if __name__=='__main__':main()
