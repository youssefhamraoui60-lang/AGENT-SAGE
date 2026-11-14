"""Audited preparations, expiring single-use approvals, and disabled-by-default execution."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from decimal import Decimal,InvalidOperation
import hashlib,hmac,json,secrets
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit
from lxml import etree
from psycopg.types.json import Jsonb
from app.core.config import settings
from app.services import business_store as db
from app.services.sage_gateway import Gateway,RESOURCES,build_xml,digest,path
from app.services.sage_soap import SageError
from app.schemas.sage_crud import Preparation
from app.services.sage_article_rules import check as check_article_rules
from app.services.sage_test_scope import temporary_admin_scope,scope_matches
from app.services.sage_tls import local_tls_readiness

class CrudError(Exception):
    def __init__(self,code,status=409):self.code=code;self.status=status;super().__init__(code)

def migrate():
    body=(Path(__file__).resolve().parents[2]/'migrations/005-soap-crud.sql').read_text(encoding='utf-8');sha=hashlib.sha256(body.encode()).hexdigest()
    with db.connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('sage-crud-migration',))
        row=conn.execute('SELECT sha256 FROM schema_migrations WHERE version=%s',('005-soap-crud',)).fetchone()
        if row:
            if row['sha256']!=sha:raise ValueError('Migration checksum mismatch')
            return False
        conn.execute(body);conn.execute('INSERT INTO schema_migrations(version,sha256) VALUES (%s,%s)',('005-soap-crud',sha))
    return True

def description_hash(desc):
    node=deepcopy(desc);node.attrib.pop('TIM',None)
    return hashlib.sha256(etree.tostring(node)).hexdigest()

def event(conn,identifier,kind,payload,actor='system'):
    conn.execute('INSERT INTO soap_operation_events(operation_id,event_type,actor,payload) VALUES (%s,%s,%s,%s)',(identifier,kind,actor,Jsonb(payload)))

def security(resource=None,action=None,description=None,record_keys=None):
    blockers=[]
    if not settings.sage_writes_enabled:blockers.append('WRITES_DISABLED')
    try:
        url=urlsplit(settings.sage_soap_base_url.rstrip('/'))
        # Match the connector's base-URL rules; malformed ports/IPv6 must fail
        # closed instead of crashing /security or giving a misleading green gate.
        valid_https=(url.scheme=='https' and bool(url.hostname) and
            not any([url.username,url.password,url.path,url.query,url.fragment]))
        if url.port is not None and not 1<=url.port<=65535:valid_https=False
    except ValueError:valid_https=False
    if not valid_https:blockers.append('VERIFIED_HTTPS_REQUIRED')
    tls=local_tls_readiness(settings) if valid_https else {'local_material_ready':False,'peer_verified':False,'code':'https_required'}
    if valid_https and not tls['local_material_ready']:blockers.append('CA_CRL_MATERIAL_REQUIRED')
    user=settings.sage_soap_username.get_secret_value()
    policy={};temporary=False
    try:
        policy=json.loads(Path(settings.sage_security_policy_file).read_text(encoding='utf-8'))
        temporary=temporary_admin_scope(policy,user)
        expiry=datetime.fromisoformat(policy['expires_at'])
        if expiry.tzinfo is None or expiry<=datetime.now(timezone.utc):raise ValueError()
        if policy['folder']!='TEST' or policy['solution']!='V12' or policy['pool']!=settings.sage_soap_pool or policy['base_url']!=settings.sage_soap_base_url:raise ValueError()
        if policy.get('credentials_rotated') is not True or (policy.get('dedicated_account_verified') is not True and not temporary):raise ValueError()
        if policy['http_login_sha256']!=hashlib.sha256(user.encode()).hexdigest():raise ValueError()
    except (OSError,ValueError,KeyError,TypeError):blockers.append('VALID_ADMIN_SECURITY_EVIDENCE_REQUIRED')
    if not user or (user.casefold() in ['admin','administrator'] and not temporary):blockers.append('DEDICATED_TECHNICAL_ACCOUNT_REQUIRED')
    if temporary and resource and action and not scope_matches(policy,resource,action,record_keys):
        blockers.append('OUTSIDE_SINGLE_ARTICLE_TEST_SCOPE')
    if resource and action and policy:
        try:
            permit=policy['permissions'][resource][action]
            if permit['rights_verified'] is not True or permit['business_rules_reviewed'] is not True:raise ValueError()
            if action=='create' and permit.get('manual_keys_preserved') is not True:raise ValueError()
            for name in ['rights_evidence','business_rules_evidence']:
                file=Path(permit[name]['path'])
                if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=permit[name]['sha256']:raise ValueError()
            if description is not None:
                if permit['description_sha256']!=description_hash(description):raise ValueError()
                x3_user=description.get('USER','')
                if not x3_user or (x3_user.casefold() in ['admin','administrator'] and not temporary) or hashlib.sha256(x3_user.encode()).hexdigest()!=policy['x3_login_sha256']:raise ValueError()
        except (OSError,ValueError,KeyError,TypeError):blockers.append('SCOPED_X3_RIGHTS_AND_RULES_EVIDENCE_REQUIRED')
    return {'ready':not blockers,'blockers':sorted(set(blockers)),'folder':'TEST','individual_approval_required':True,
        'tls':tls,
        'scope':policy['scope'] if temporary else None}

def schema(resource):
    gateway=Gateway(resource);desc=gateway.describe();fields=[]
    for group in desc.findall('./ADXDATA/GRP'):
        for f in group.findall('FLD'):
            if f.get('MOD')!='Input':continue
            if f.get('NAM') in gateway.spec['keys'] or f.get('NAM','').startswith('WW_'):continue
            fields.append({'group':group.get('NAM'),'name':f.get('NAM'),'label':f.get('C_FRA') or f.get('NAM'),
                'type':f.get('TYP'),'length':f.get('LEN'),'dimension':int(f.get('DIM','1')),'table':group.get('TYB')=='Table',
                'update_allowed':group.get('NAM')+'.'+f.get('NAM') in gateway.spec['updates'],
                'menu':[{'value':n.get('IND'),'label':n.get('C_FRA')} for n in desc.findall('./ADXMEN/MNU[@NO="'+f.get('MEN','')+'"]/VAL')]})
    return {'resource':resource,'publication':gateway.spec['publication'],'object':gateway.spec['object'],'keys':gateway.spec['keys'],
        'fields':fields,'folder':'TEST','description_hash':description_hash(desc),'security':security(resource,'create',desc),'sage_menu':gateway.spec['menu']}

def read(identifier):
    with db.connection() as conn:
        row=conn.execute('SELECT * FROM soap_operations WHERE id=%s',(identifier,)).fetchone()
        if not row:raise CrudError('operation_not_found',404)
        row['history']=conn.execute('SELECT event_type,actor,payload,created_at FROM soap_operation_events WHERE operation_id=%s ORDER BY id',(identifier,)).fetchall()
    return {**row,'security':security(row['resource'],row['action']),'requires_individual_approval':True}

def history(resource):
    with db.connection() as conn:rows=conn.execute('SELECT id,action,record_keys,status,created_at FROM soap_operations WHERE resource=%s ORDER BY created_at DESC LIMIT 100',(resource,)).fetchall()
    return {'operations':rows,'limit':100}

def validate_integrity(row):
    expected=digest({'resource':row['resource'],'payload':row['payload'],'xml':row['object_xml'],'before':row['before_record'],'description_hash':row['description_hash'],'folder':'TEST'})
    if expected!=row['digest'] or row['payload']['keys']!=row['record_keys'] or row['payload']['action']!=row['action']:raise CrudError('stored_operation_integrity_mismatch')

def prepare(resource,request):
    gateway=Gateway(resource);desc=gateway.describe();xml=build_xml(desc,gateway.spec,request)
    if ('CREATE' if request.action=='create' else 'MODIFY') not in {n.get('ID') for n in desc.iter('MET')}:raise CrudError('publication_method_unavailable',422)
    blockers=[]
    try:before=gateway.read(request.keys,describe=False)
    except SageError as exc:before={'exists':None,'error':exc.code};blockers.append('EXISTENCE_UNKNOWN')
    if request.action=='create' and before['exists'] is True:blockers.append('DUPLICATE_EXISTS')
    if request.action=='update' and before['exists'] is False:blockers.append('RECORD_NOT_FOUND')
    if resource=='article-sites' and request.action=='create':
        try:
            parent=Gateway('articles').read({'ITMREF':request.keys['ITMREF']})
            if not parent['exists']:blockers.append('PARENT_ARTICLE_NOT_FOUND')
        except SageError:blockers.append('PARENT_ARTICLE_UNKNOWN')
    if request.action=='update' and before.get('exists'):
        if all(before.get('fields',{}).get(path(f.group,f.name,f.row))==f.value for f in request.fields):blockers.append('NO_CHANGES')
    business_checks=None
    if resource=='articles' and request.action=='create':
        try:business_checks=check_article_rules(request,desc,description_hash(desc))
        except SageError as exc:blockers.append(exc.code)
    policy=security(resource,request.action,desc)
    payload=request.model_dump();schema_hash=description_hash(desc)
    checksum=digest({'resource':resource,'payload':payload,'xml':xml,'before':before,'description_hash':schema_hash,'folder':'TEST'})
    checks={'blockers':blockers,'security':policy,'business_checks':business_checks,'conditional_rules_verified':policy['ready'] and not blockers,'duplicate_checked':before['exists'] is not None,
        'after_proposed':{path(f.group,f.name,f.row):f.value for f in request.fields},'human_approval_required':True,'save_sent':False}
    identifier=uuid4()
    with db.connection() as conn:
        conn.execute('INSERT INTO soap_operations(id,resource,action,record_keys,payload,object_xml,digest,description_hash,before_record,status,checks) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (identifier,resource,request.action,Jsonb(request.keys),Jsonb(payload),xml,checksum,schema_hash,Jsonb(before),'blocked' if blockers else 'prepared',Jsonb(checks)))
        event(conn,identifier,'prepared',{'digest':checksum,'action':request.action,'blockers':blockers,'security_blockers':policy['blockers']})
    return read(identifier)

def approve(identifier,approval):
    row=read(identifier)
    validate_integrity(row)
    gateway=Gateway(row['resource']);desc=gateway.describe()
    if not security(row['resource'],row['action'],desc,row['record_keys'])['ready']:raise CrudError('security_conditions_not_met',423)
    token=secrets.token_urlsafe(32);expires=datetime.now(timezone.utc)+timedelta(minutes=15)
    with db.connection() as conn:
        current=conn.execute('SELECT * FROM soap_operations WHERE id=%s FOR UPDATE',(identifier,)).fetchone()
        if current['status']!='prepared' or current['digest']!=approval.digest:raise CrudError('approval_state_or_digest_mismatch')
        conn.execute('INSERT INTO soap_operation_approvals(operation_id,digest,token_sha256,actor,reason,expires_at) VALUES (%s,%s,%s,%s,%s,%s)',
            (identifier,current['digest'],hashlib.sha256(token.encode()).hexdigest(),approval.actor,approval.reason,expires))
        conn.execute("UPDATE soap_operations SET status='approved',updated_at=now() WHERE id=%s",(identifier,))
        event(conn,identifier,'human_approved',{'digest':current['digest'],'reason':approval.reason,'expires_at':expires.isoformat()},approval.actor)
    return {'operation_id':identifier,'approval_token':token,'expires_at':expires,'digest':row['digest'],'single_use':True}

def authorize_transport(identifier,resource,action,xml):
    # Defence in depth: direct use of Gateway.write_once also requires a consumed approval.
    if not security(resource,action,Gateway(resource).describe())['ready']:raise CrudError('security_conditions_not_met',423)
    with db.connection() as conn:
        row=conn.execute('SELECT o.status,o.resource,o.action,o.object_xml,o.record_keys,a.consumed_at FROM soap_operations o JOIN soap_operation_approvals a ON a.operation_id=o.id WHERE o.id=%s',(identifier,)).fetchone()
    if not row or row['status']!='executing' or row['consumed_at'] is None or row['resource']!=resource or row['action']!=action or row['object_xml']!=xml:raise CrudError('consumed_approval_required',403)
    if not security(resource,action,record_keys=row['record_keys'])['ready']:raise CrudError('security_conditions_not_met',423)

def matches(expected,actual):
    if expected==actual:return True
    if isinstance(expected,str) and isinstance(actual,str):
        try:return Decimal(expected).is_finite() and Decimal(expected)==Decimal(actual)
        except InvalidOperation:return False
    return False

def execute(resource,action,keys,execution):
    row=read(execution.operation_id)
    validate_integrity(row)
    if row['resource']!=resource or row['action']!=action or row['record_keys']!=keys:raise CrudError('execution_scope_mismatch',403)
    gateway=Gateway(resource);desc=gateway.describe()
    if not security(resource,action,desc,keys)['ready']:raise CrudError('security_conditions_not_met',423)
    if description_hash(desc)!=row['description_hash']:raise CrudError('publication_changed')
    if row['checks'].get('blockers'):raise CrudError('preparation_blocked')
    if resource=='articles' and action=='create':
        verified=check_article_rules(Preparation(**row['payload']),desc,description_hash(desc))
        if verified!=row['checks'].get('business_checks'):raise CrudError('business_rules_changed_since_preparation')
    current=gateway.read(keys,describe=False)
    if action=='create' and current['exists'] is not False:raise CrudError('duplicate_or_existence_unknown')
    if action=='update' and (not current['exists'] or current.get('fingerprint')!=row['before_record'].get('fingerprint')):raise CrudError('record_changed_since_approval')
    if resource=='article-sites' and action=='create' and not Gateway('articles').read({'ITMREF':keys['ITMREF']})['exists']:raise CrudError('parent_article_missing')
    # Consume exactly once and commit before any attempted SOAP write.
    with db.connection() as conn:
        operation=conn.execute('SELECT * FROM soap_operations WHERE id=%s FOR UPDATE',(row['id'],)).fetchone()
        approval=conn.execute('SELECT * FROM soap_operation_approvals WHERE operation_id=%s FOR UPDATE',(row['id'],)).fetchone()
        if operation['status']!='approved' or not approval or approval['consumed_at'] or approval['expires_at']<=datetime.now(timezone.utc) or approval['digest']!=operation['digest'] or not hmac.compare_digest(approval['token_sha256'],hashlib.sha256(execution.approval_token.get_secret_value().encode()).hexdigest()):raise CrudError('approval_missing_expired_or_consumed',403)
        conn.execute('UPDATE soap_operation_approvals SET consumed_at=now() WHERE operation_id=%s',(row['id'],))
        conn.execute("UPDATE soap_operations SET status='executing',updated_at=now() WHERE id=%s",(row['id'],))
        event(conn,row['id'],'write_attempt_claimed',{'action':action,'digest':row['digest']},approval['actor'])
    result={};status='ambiguous'
    try:
        result=gateway.write_once(action,keys,row['object_xml'],row['id'])
        result={k:v for k,v in result.items() if k!='xml'}
        status='failed' if result['status']!=1 else 'unverified'
    except Exception as exc:
        # Never print raw network/Zeep exceptions, which may contain headers or data.
        result={'error_type':type(exc).__name__,'code':'write_outcome_unknown','retry_allowed':False}
    try:after=gateway.read(keys)
    except Exception:after={'exists':None,'error':'readback_unavailable'}
    comparisons={path(f['group'],f['name'],f.get('row')):matches(f['value'],after.get('fields',{}).get(path(f['group'],f['name'],f.get('row')))) for f in row['payload']['fields']}
    if status=='unverified' and after.get('exists') and all(comparisons.values()):status='succeeded'
    if resource=='suppliers' and action=='create':
        from app.services.supplier_readback import verify,message
        try:verification=verify(keys,row['payload'],after,result)
        except Exception:
            # A verification failure after SAVE must still be journalled, never
            # leave the client believing a retry is safe or the write confirmed.
            verification={'confirmed':False,'created_and_active':False,'folder':'TEST','code':keys.get('BPSNUM'),
                          'errors':['supplier_verification_unavailable'],'retry_allowed':False}
        result['supplier_verification']=verification
        result['supplier_message']=message(verification)
        if status=='succeeded' and not verification['confirmed']:status='unverified'
    result.update(field_comparisons=comparisons,retry_allowed=False)
    with db.connection() as conn:
        conn.execute('UPDATE soap_operations SET status=%s,result=%s,after_record=%s,updated_at=now() WHERE id=%s',(status,Jsonb(result),Jsonb(after),row['id']))
        event(conn,row['id'],'write_result',{'status':status,'result':result,'readback':after})
    return read(row['id'])

def reconcile(identifier):
    row=read(identifier)
    after=Gateway(row['resource']).read(row['record_keys'])
    with db.connection() as conn:event(conn,identifier,'read_only_reconciliation',after)
    return {'operation_id':identifier,'read':after,'write_retried':False,'previous_status':row['status']}
