"""Local drafts and observations only. No Sage write implementation or approval bypass."""
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4
from lxml import etree
from psycopg.types.json import Jsonb
from app.services import business_store as store
from app.services.sage_soap import SageReader,SageError,parse_xml,SOAP_NS,NS,GATE
from app.services.sage_creation_preflight import validate_target

def migrate():
    body=(Path(__file__).resolve().parents[2]/'migrations/004-soap-preparation.sql').read_text(encoding='utf-8')
    digest=hashlib.sha256(body.encode()).hexdigest()
    with store.connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('agent-sage-step4-migration',))
        row=conn.execute('SELECT sha256 FROM schema_migrations WHERE version=%s',('004-soap-preparation',)).fetchone()
        if row:
            if row['sha256']!=digest:raise ValueError('Applied migration checksum mismatch')
            return False
        conn.execute(body)
        conn.execute('INSERT INTO schema_migrations(version,sha256) VALUES (%s,%s)',('004-soap-preparation',digest))
    return True

def probe_reference(reader,reference):
    if not GATE.acquire(blocking=False):raise SageError('sage_busy',503)
    session=None
    try:
        session,service=reader._client()
        with service._client.settings(raw_response=True):
            response=service.read(callContext={'codeLang':reader.config.sage_soap_language,
                'poolAlias':reader.config.sage_soap_pool,'poolId':'','requestConfig':'adxwss.optreturn=XML&adxwss.trace.on=off'},
                publicName=reader.config.sage_soap_publication,objectKeys=[{'key':'ITMREF','value':reference}])
        root=parse_xml(response.content)
        reply=root.find('{'+SOAP_NS+'}Body/{'+NS+'}readResponse')
        if response.status_code!=200 or reply is None:raise SageError('sage_existence_unknown')
        returned=[n for n in reply if etree.QName(n).localname=='readReturn']
        if len(returned)!=1:raise SageError('sage_existence_unknown')
        values={etree.QName(n).localname:n.text for n in returned[0]}
        if values.get('status')=='1' and values.get('resultXml'):
            article=parse_xml(values['resultXml'])
            refs=[n.text for n in article.iter('FLD') if (n.get('NAME') or n.get('NAM'))=='ITMREF']
            if reference not in refs:raise SageError('sage_article_reference_mismatch')
            return {'exists':True,'soap_status':1,'source':'sage_live_read'}
        messages=[n.text or '' for n in returned[0].iter() if etree.QName(n).localname=='message']
        if values.get('status')=='0' and not values.get('resultXml') and any(m.strip()=='Fiche inexistante' for m in messages):
            return {'exists':False,'soap_status':0,'source':'sage_live_read','message':'Fiche inexistante'}
        raise SageError('sage_existence_unknown')
    finally:
        if session is not None:session.close()
        GATE.release()

def build_draft(description,request):
    validate_target(description)
    fields=[('ITM0_1','TCLCOD',request.categorie),('ITM0_1','ITMREF',request.reference),('ITM0_1','DES1AXX',request.designation),
            ('ITM3_1','STU',request.unite_stock),('ITM3_1','PUU',request.unite_achat),('ITM3_1','SAU',request.unite_vente),
            ('ITM3_1','PUUSTUCOE',request.coefficient_achat),('ITM3_1','SAUSTUCOE',request.coefficient_vente)]
    fields.extend((group,name,value) for group,name,value in [
        ('ITM0_1','ITMSTA',request.statut),('ITM2_1','STOMGTCOD',request.gestion_stock),
        ('ITM2_3','LOTMGTCOD',request.gestion_lots),('ITM5_1','ACCCOD',request.code_comptable)] if value is not None)
    order={name:index for index,name in enumerate(['TCLCOD','ITMSTA','ITMREF','DES1AXX','STOMGTCOD','LOTMGTCOD','STU','PUU','PUUSTUCOE','SAU','SAUSTUCOE','ACCCOD'])}
    fields.sort(key=lambda item:order[item[1]])
    root=etree.Element('PARAM');groups={}
    for group,name,value in fields:
        meta=description.find('./ADXDATA/GRP[@NAM="'+group+'"]/FLD[@NAM="'+name+'"]')
        if meta is None or meta.get('MOD')!='Input':raise SageError('sage_field_not_published')
        if meta.get('DIM','1')!='1':raise SageError('sage_field_dimension_changed')
        if meta.get('TYP')=='Char' and len(value)>int(meta.get('LEN','0')):raise SageError('sage_field_length_changed')
        if meta.get('TYP')=='Integer' and not re.fullmatch(r'\d+',value):raise SageError('sage_invalid_integer',422)
        if meta.get('MEN'):
            valid={n.get('IND') for n in description.findall('./ADXMEN/MNU[@NO="'+meta.get('MEN')+'"]/VAL')}
            if value not in valid:raise SageError('sage_invalid_local_menu_value',422)
        if group not in groups:groups[group]=etree.SubElement(root,'GRP',ID=group)
        etree.SubElement(groups[group],'FLD',NAME=name).text=value
    return etree.tostring(root,encoding='unicode',pretty_print=True)

def prepare(request):
    reader=SageReader()
    description=reader._invoke('getDescription')
    xml=build_draft(description,request)
    try:existence=probe_reference(reader,request.reference)
    except SageError as exc:existence={'exists':None,'error_code':exc.code}
    status='blocked_existing' if existence['exists'] is True else ('blocked_unknown' if existence['exists'] is None else 'awaiting_human_review')
    checks={'target':{'solution':'V12','folder':'TEST','publication':'WS_ARTICLE','object':'ITM'},'existence':existence,
        'structural_validation':True,'conditional_business_rules_verified':False,'effective_create_rights_verified':False,
        'reference_values_validated':False,'human_approval_required':True,'human_approved':False,'sage_write_enabled':False,
        'transport_https':reader.config.sage_soap_base_url.startswith('https://'),
        'warnings':['Brouillon uniquement; les valeurs par défaut et obligations conditionnelles restent à vérifier.',
            'La lecture ne réserve pas le code; une nouvelle vérification sera nécessaire avant toute écriture autorisée.']}
    identifier=uuid4();digest=hashlib.sha256(xml.encode()).hexdigest()
    with store.connection() as conn:
        conn.execute('INSERT INTO soap_article_preparations(id,reference,payload,object_xml,object_sha256,checks,status) VALUES (%s,%s,%s,%s,%s,%s,%s)',
            (identifier,request.reference,Jsonb(request.model_dump()),xml,digest,Jsonb(checks),status))
    return read(identifier)

def read(identifier):
    with store.connection() as conn:
        row=conn.execute('SELECT * FROM soap_article_preparations WHERE id=%s',(identifier,)).fetchone()
    if row is None:raise store.NotFound()
    return {**row,'requires_human_approval':True,'sage_write_enabled':False}

def record_observation(reference,result,source):
    identifier=uuid4()
    with store.connection() as conn:
        conn.execute('INSERT INTO soap_article_observations(id,reference,source,result) VALUES (%s,%s,%s,%s)',
            (identifier,reference,source,Jsonb(result)))
    return str(identifier)
