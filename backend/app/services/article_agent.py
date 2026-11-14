"""Conversation bridge: local drafts, SELECT-only SQL checks, existing one-shot SOAP guard."""
import hashlib,json,re,subprocess
from pathlib import Path
from uuid import UUID,uuid4
from pydantic import BaseModel,ConfigDict,Field,field_validator
from psycopg.types.json import Jsonb
from app.services import business_store as db,sage_crud as crud
from app.schemas.sage_crud import Preparation

ROOT=Path(__file__).resolve().parents[3]

class Draft(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    designation:str=Field(default='',max_length=70)
    code_article:str=Field(default='',max_length=20)
    categorie:str=Field(default='',max_length=5)
    unite:str=Field(default='',max_length=3)
    site:str=Field(default='',max_length=5)
    fournisseur:str=Field(default='',max_length=100)
    code_fournisseur:str=Field(default='',max_length=15)
    reference_article:str=Field(default='',max_length=20)
    code_comptable:str=Field(default='',max_length=10)
    gestion_stock:str=Field(default='',max_length=2)
    gestion_lots:str=Field(default='',max_length=2)
    @field_validator('*')
    @classmethod
    def clean(cls,value):
        if any(ord(c)<32 for c in value):raise ValueError('Caractère de contrôle interdit')
        return value

def migrate():
    body=(ROOT/'backend/migrations/006-article-agent.sql').read_text(encoding='utf-8');sha=hashlib.sha256(body.encode()).hexdigest()
    with db.connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('article-agent-migration',))
        row=conn.execute('SELECT sha256 FROM schema_migrations WHERE version=%s',('006-article-agent',)).fetchone()
        if row:
            if row['sha256']!=sha:raise ValueError('Migration checksum mismatch')
            return False
        conn.execute(body)
        conn.execute('INSERT INTO schema_migrations(version,sha256) VALUES (%s,%s)',('006-article-agent',sha))
    return True

def event(conn,identifier,kind,payload):
    conn.execute('INSERT INTO article_agent_events(draft_id,kind,payload) VALUES (%s,%s,%s)',(identifier,kind,Jsonb(payload)))

def sql_check(draft):
    try:
        process=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'scripts/article_agent_sql_reader.ps1')],
            input=json.dumps(draft.model_dump(),ensure_ascii=False),capture_output=True,text=True,encoding='utf-8',timeout=35)
        if process.returncode or len(process.stdout)>262144:raise ValueError()
        result=json.loads(process.stdout.lstrip('\ufeff'))
        if not result.get('ok') or result.get('folder')!='TEST':raise ValueError()
        return result
    except (OSError,ValueError,subprocess.SubprocessError):
        return {'ok':False,'code':'sql_reader_unavailable','folder':'TEST'}

def evaluate(draft,sql):
    errors=[];warnings=[]
    for key in ['designation','code_article','categorie','unite']:
        if not getattr(draft,key):errors.append('missing:'+key)
    for key in ['code_article','categorie','unite','site','code_fournisseur','reference_article']:
        if getattr(draft,key) and not re.fullmatch(r'[A-Za-z0-9_./ -]+',getattr(draft,key)):errors.append('invalid:'+key)
    if not sql.get('ok'):errors.append('sql_check_unavailable')
    else:
        if sql.get('article'):errors.append('duplicate_article_code')
        if sql.get('designation_matches'):warnings.append('similar_designation_review_required')
        for key,result in [('categorie','category'),('unite','unit'),('site','site'),('code_fournisseur','supplier'),('reference_article','reference')]:
            if getattr(draft,key) and not sql.get(result):errors.append('unknown:'+key)
    if draft.fournisseur and not draft.code_fournisseur:errors.append('supplier_code_required')
    if draft.code_fournisseur:errors.append('supplier_link_mapping_requires_review')
    warnings += ['conditional_business_rules_require_sage_review','site_is_not_an_article_site_creation']
    return {'valid':not errors,'errors':errors,'warnings':warnings,'sql':sql,'writes_sent':False}

def create(identifier,proposal):
    articles=proposal.get('articles',[])
    data=articles[0] if len(articles)==1 and proposal.get('intention')=='create_article' else {}
    fields={key:(data.get(key) or '') for key in Draft.model_fields}
    with db.connection() as conn:
        original=conn.execute('SELECT original_text FROM requests WHERE id=%s',(identifier,)).fetchone()['original_text']
    ungrounded=[]
    for key in ['categorie','unite']:
        if fields[key] and not re.search(r'(?<!\w)'+re.escape(fields[key])+r'(?!\w)',original,re.I):
            fields[key]='';ungrounded.append(key)
    generated=False
    if data and not fields['code_article']:
        fields['code_article']='AI'+uuid4().hex[:14].upper();generated=True
    with db.connection() as conn:
        conn.execute('INSERT INTO article_agent_drafts(id,draft) VALUES (%s,%s)',(identifier,Jsonb(fields)))
        event(conn,identifier,'draft_proposed',{'application_generated_code':generated,'code_reserved':False,
            'single_article_supported':bool(data),'questions':proposal.get('questions',[]),'ambiguous':proposal.get('ambigu',True),
            'ungrounded_fields_removed':ungrounded,'extraction_source':'local_ollama_no_sql_context'})
    return read(identifier)

def row(identifier,conn,lock=False):
    value=conn.execute('SELECT * FROM article_agent_drafts WHERE id=%s'+(' FOR UPDATE' if lock else ''),(identifier,)).fetchone()
    if not value:raise crud.CrudError('conversation_not_found',404)
    return value

def read(identifier):
    with db.connection() as conn:
        value=row(identifier,conn)
        original=conn.execute('SELECT original_text,provenance,initial_extraction FROM requests WHERE id=%s',(identifier,)).fetchone()
        history=conn.execute('SELECT kind,payload,created_at FROM article_agent_events WHERE draft_id=%s ORDER BY id',(identifier,)).fetchall()
    op=crud.read(value['operation_id']) if value['operation_id'] else None
    return {**value,'message':original['original_text'],'ai_provenance':original['provenance'],'initial_extraction':original['initial_extraction'],'history':history,'operation':op,'security':crud.security(),
        'creation_message':'Création confirmée par Sage et SQL' if value['outcome'].get('confirmed') else 'Création en attente de configuration Sage' if not crud.security()['ready'] else 'Brouillon à valider et approbation distincte requise',
        'folder':'TEST'}

def history():
    with db.connection() as conn:
        return conn.execute('SELECT d.id,d.revision,d.validated,d.draft,d.created_at,d.outcome,r.original_text AS message FROM article_agent_drafts d JOIN requests r ON r.id=d.id ORDER BY d.created_at DESC LIMIT 30').fetchall()

def check_revision(value,revision):
    if value['revision']!=revision:raise crud.CrudError('stale_draft_revision',409)

def editable(value):
    if value['operation_id']:
        op=crud.read(value['operation_id'])
        if op['status'] not in ['prepared','blocked']:raise crud.CrudError('approved_or_attempted_draft_is_immutable',409)

def update(identifier,revision,draft):
    with db.connection() as conn:
        value=row(identifier,conn,True);check_revision(value,revision);editable(value)
        conn.execute("UPDATE article_agent_drafts SET draft=%s,revision=revision+1,validated=false,validation='{}',operation_id=NULL,outcome='{}',updated_at=now() WHERE id=%s",(Jsonb(draft.model_dump()),identifier))
        event(conn,identifier,'human_correction',{'before':value['draft'],'after':draft.model_dump(),'revision':revision+1})
    return read(identifier)

def validate(identifier,revision,confirm=False):
    with db.connection() as conn:value=row(identifier,conn)
    check_revision(value,revision);editable(value)
    draft=Draft.model_validate(value['draft']);evaluation=evaluate(draft,sql_check(draft))
    with db.connection() as conn:
        current=row(identifier,conn,True);check_revision(current,revision);editable(current)
        conn.execute('UPDATE article_agent_drafts SET validation=%s,validated=%s,updated_at=now() WHERE id=%s',(Jsonb(evaluation),confirm and evaluation['valid'],identifier))
        event(conn,identifier,'draft_validated' if confirm else 'sql_checked',{'revision':revision,'validation':evaluation,'local_validation_only':True})
    return read(identifier)

def preparation(draft):
    fields=[{'group':'ITM0_1','name':'DES1AXX','value':draft.designation},{'group':'ITM0_1','name':'TCLCOD','value':draft.categorie}]
    # TEST publication menu 246: 1 = Actif. build_xml verifies the live menu.
    fields.append({'group':'ITM0_1','name':'ITMSTA','value':'1'})
    fields += [{'group':'ITM3_1','name':name,'value':draft.unite} for name in ['STU','PUU','SAU']]
    fields += [{'group':'ITM3_1','name':name,'value':'1'} for name in ['PUUSTUCOE','SAUSTUCOE']]
    for value,group,name in [(draft.code_comptable,'ITM5_1','ACCCOD'),(draft.gestion_stock,'ITM2_1','STOMGTCOD'),(draft.gestion_lots,'ITM2_3','LOTMGTCOD')]:
        if value:fields.append({'group':group,'name':name,'value':value})
    return Preparation(action='create',keys={'ITMREF':draft.code_article},fields=fields)

def prepare(identifier,revision):
    with db.connection() as conn:
        value=row(identifier,conn,True);check_revision(value,revision);editable(value)
        if not value['validated']:raise crud.CrudError('human_draft_validation_required',409)
        draft=Draft.model_validate(value['draft']);evaluation=evaluate(draft,sql_check(draft))
        if not evaluation['valid']:raise crud.CrudError('sql_business_checks_failed',409)
        op=crud.prepare('articles',preparation(draft))
        conn.execute('UPDATE article_agent_drafts SET operation_id=%s,updated_at=now() WHERE id=%s',(op['id'],identifier))
        event(conn,identifier,'soap_prepared_no_write',{'operation_id':str(op['id']),'digest':op['digest']})
    return read(identifier)

def approve(identifier,revision,approval):
    with db.connection() as conn:
        value=row(identifier,conn,True);check_revision(value,revision)
        if not value['validated'] or not value['operation_id']:raise crud.CrudError('prepared_validated_draft_required',409)
        op=crud.read(value['operation_id'])
        if op['digest']!=approval.digest:raise crud.CrudError('approval_digest_mismatch',409)
        result=crud.approve(value['operation_id'],approval)
        event(conn,identifier,'specific_write_approval',{'operation_id':str(value['operation_id']),'actor':approval.actor,'reason':approval.reason})
    return result

def execute(identifier,revision,execution):
    with db.connection() as conn:
        value=row(identifier,conn,True);check_revision(value,revision)
        if not value['validated'] or value['operation_id']!=execution.operation_id:raise crud.CrudError('execution_scope_mismatch',403)
        if not crud.security()['ready']:raise crud.CrudError('security_conditions_not_met',423)
        draft=Draft.model_validate(value['draft']);check=evaluate(draft,sql_check(draft))
        if not check['valid']:raise crud.CrudError('sql_business_checks_failed',409)
        event(conn,identifier,'execution_requested',{'operation_id':str(execution.operation_id),'revision':revision})
    op=crud.execute('articles','create',{'ITMREF':draft.code_article},execution)
    sql=sql_check(draft)
    rows=sql.get('article',[]);saved=rows[0] if rows else {}
    comparisons={key:str(saved.get(key,'')).strip()==expected for key,expected in {
        'ITMREF_0':draft.code_article,'ITMDES1_0':draft.designation,'TCLCOD_0':draft.categorie,
        'STU_0':draft.unite,'PUU_0':draft.unite,'SAU_0':draft.unite}.items()}
    outcome={'confirmed':op['status']=='succeeded' and sql.get('ok',False) and all(comparisons.values()),
        'soap_status':op['status'],'sql_readback':sql,'comparisons':comparisons,'retry_allowed':False,
        'site_creation_executed':False}
    with db.connection() as conn:
        conn.execute('UPDATE article_agent_drafts SET outcome=%s,updated_at=now() WHERE id=%s',(Jsonb(outcome),identifier))
        event(conn,identifier,'execution_result',outcome)
    return read(identifier)
