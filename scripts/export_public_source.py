"""Export a new public working tree; never add private backup/data to Git."""
import hashlib,json,os,re,shutil,subprocess,zipfile
from pathlib import Path
from datetime import datetime,timezone
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
DEST=Path('C:/AGENT-SAGE-PUBLIC')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
ALLOWED={'.py','.ps1','.psm1','.sql','.md','.txt','.json','.yaml','.yml','.sh','.html','.css','.ts','.tsx','.js','.jsx','.toml','.svg','.gitignore'}
FOLDERS=['backend','frontend','telegram-test','scripts','TEST','sql','database','docker','docs','workflows','knowledge','examples','tests','config']
EXCLUDE={'.venv','node_modules','__pycache__','.pytest_cache','dist','logs','runtime','backups','.git','security-evidence','pki','remote-access','certs','screenshots','fixtures','artifacts','__snapshots__','pdf','documents','uploads'}

def main():
    DEST.mkdir(parents=True,exist_ok=False)
    values=dotenv_values(ROOT/'.env');secret_values=[]
    for k,v in values.items():
        if v and len(v)>=6 and re.search(r'password|secret|token|api.?key|encryption|database_url',k,re.I):secret_values.append(v)
    redactions=[];files=[];skipped=[]
    def export(src):
        rel=src.relative_to(ROOT)
        if src.suffix.lower()=='.json' and not (
            rel.as_posix() in ('frontend/package.json','frontend/package-lock.json')
            or rel.parts[0] in ('workflows','examples')
            or rel.parts[0]=='config' and len(rel.parts)==2):return
        if rel.parts[0]=='TEST' and (len(rel.parts)>2 or src.suffix.lower() not in ('.py','.ps1','.psm1','.sql') or src.name.startswith('SOB-CORRECTION')):return
        if src.name.startswith('.env') or src.suffix.lower() not in ALLOWED:return
        if src.stat().st_size>2_000_000:skipped.append(rel.as_posix());return
        if any(x in src.name.lower() for x in ('credential','private-key','secret-export','vm.local')):return
        try:text=src.read_text(encoding='utf-8-sig')
        except UnicodeError:return
        original=text
        for value in sorted(set(secret_values),key=len,reverse=True):
            for candidate in {value,value.replace(' ',''),value.replace('\\','\\\\')}:
                if len(candidate)>=6:text=text.replace(candidate,'REDACTED_CONFIGURE_LOCALLY')
        # Remove literals only, retaining ordinary variable accesses and prompts.
        literal=re.compile(r'''(?im)((?:password|passwd|pwd|api_key|app_password|client_secret|access_token)\s*[:=]\s*['"])([^'"\r\n]{6,})(['"])''')
        def hide(m):
            v=m[2]
            if '(' in v or ')' in v or v.startswith(('$','{','<','REDACTED')) or re.fullmatch(r'[A-Z_]{6,}',v) or any(s in v.lower() for s in ('example','placeholder','changeme','test','password','mot de passe')):return m[0]
            return m[1]+'REDACTED_CONFIGURE_LOCALLY'+m[3]
        text=literal.sub(hide,text)
        text=re.sub(r'(?i)(https?://)[^\s/:@]+:[^\s/@]+@',r'\1REDACTED_CONFIGURE_LOCALLY@',text)
        text=re.sub(r'(?i)\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{24,})\b','REDACTED_CONFIGURE_LOCALLY',text)
        if re.search(r'-----BEGIN (?:OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/=]{30}',text):skipped.append(rel.as_posix());return
        dst=DEST/rel;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(text,encoding='utf-8')
        files.append(rel.as_posix())
        if text!=original:redactions.append(rel.as_posix())
    for folder in FOLDERS:
        for current,dirs,names in os.walk(ROOT/folder):
            dirs[:]=[n for n in dirs if n not in EXCLUDE and not n.startswith('.')]
            for name in names:export(Path(current)/name)
    for name in ['README.md','compose.yaml','compose.ubuntu-vm.yaml']:export(ROOT/name)
    (DEST/'.env.example').write_text('# Configure locally. No real credentials are included.\n'+'\n'.join(k+'=' for k in values)+'\n',encoding='utf-8')
    (DEST/'.gitignore').write_text('''# Private local state must never be published
.env
.env.*
!.env.example
*.clixml
*.session*
*.sqlite*
*.db
*.dump
*.bak
*.zip
*.pfx
*.p12
*.pem
*.key
*.log
*.pid
*.pdf
*.xlsx
*.xls
*.docx
*.csv
.venv/
node_modules/
__pycache__/
.pytest_cache/
.tools/
runtime/
backups/
logs/
certs/
config/security-evidence/
frontend/dist/
''',encoding='utf-8')
    (DEST/'README.md').write_text('''# AGENT SAGE X3

Agent IA Windows pour Sage X3 : interface web, commandes Telegram SOB,
fournisseurs par e-mail, lecture de PDF/photos et mémoire PostgreSQL.

## Installation et utilisation

- [Guide de restauration de A à Z](docs/INSTALLATION-RESTAURATION-A-Z.md)
- [SQL Sage : lecture, création et modification](docs/SQL-SAGE-CREATION-MODIFICATION.md)
- [Module commandes SOB](telegram-test/README.md)
- [Lecture des documents et voyages ciment](telegram-test/SOB-LECTURE-ET-CHARGEMENTS.md)

Ce dépôt public contient le code et la documentation. La sauvegarde privée avec
les bases, `.env`, sessions, modèles et documents est conservée séparément.
Copier `.env.example` vers `.env`, puis renseigner localement les paramètres.
Le dossier `TEST` contient aussi des workers utilisés en exploitation : le garder.
Les fonctions Sage nécessitent un serveur et des comptes autorisés ; les scripts
de création/modification doivent passer par leurs validations et simulations.

Depuis le 14 novembre 2026, les messages Telegram sont traités séparément.
''',encoding='utf-8')
    proof={'files':len(files),'redacted_files':redactions,'excluded_large_or_private_key_files':skipped,'private_data_included':False,'repository':'https://github.com/youssefhamraoui60-lang/AGENT-SAGE.git'}
    (DEST/'PUBLIC-EXPORT-REPORT.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
    for f in DEST.rglob('*'):
        if not f.is_file():continue
        content=f.read_text(encoding='utf-8')
        assert not any(v in content for v in secret_values if len(v)>=8),(str(f),'secret value')
        assert f.suffix.lower() not in {'.clixml','.session','.dump','.sqlite3','.pfx','.key','.pdf','.xlsx'}
    archive=DEST.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in DEST.rglob('*'):
            if f.is_file():z.write(f,'AGENT-SAGE/'+f.relative_to(DEST).as_posix())
    git=Path(os.environ['LOCALAPPDATA'])/'AGENT-SAGE-X3-tools/mingit/cmd/git.exe'
    def g(*args,check=True):return subprocess.run([str(git),*args],cwd=DEST,check=check,capture_output=True,text=True)
    g('init','-b','main');g('config','user.name','youssefhamraoui60-lang');g('config','user.email','youssefhamraoui60-lang@users.noreply.github.com')
    g('add','.');g('commit','-m','Backup public du code AGENT SAGE avec guide installation et SQL')
    g('remote','add','origin',proof['repository'])
    print(json.dumps({'public_directory':str(DEST),'public_zip':str(archive),'files':len(files),'redacted_files':len(redactions),'commit':g('rev-parse','HEAD').stdout.strip()},ensure_ascii=True))

if __name__=='__main__':main()
