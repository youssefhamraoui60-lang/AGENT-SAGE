"""Three pinned TEST publications; the normal transport remains read-only."""
import hashlib,json,re
from pathlib import Path
from uuid import UUID
from types import SimpleNamespace
from decimal import Decimal,InvalidOperation
from lxml import etree
from app.core.config import settings
from app.services.sage_soap import SageReader,ReadOnlyTransport,SageError,parse_xml,NS,SOAP_NS,SOAP_PATH,GATE

SOAP_RESPONSE_DIR=Path(__file__).resolve().parents[3]/'runtime'/'soap-write-responses'

def archive_write_response(identifier,content):
    """Keep the bounded response body only, before decoding; never request headers."""
    from app.services.sage_soap import MAX_BYTES
    identifier=str(UUID(str(identifier)))
    if not isinstance(content,bytes) or len(content)>MAX_BYTES:raise SageError('invalid_write_response_archive')
    SOAP_RESPONSE_DIR.mkdir(parents=True,exist_ok=True)
    file=SOAP_RESPONSE_DIR/(identifier+'.xml')
    with file.open('xb') as handle:handle.write(content)
    return {'soap_response_file':str(file),'soap_response_sha256':hashlib.sha256(content).hexdigest()}

RESOURCES={
 'articles':{'publication':'WS_ARTICLE','object':'ITM','keys':['ITMREF'],'key_group':'ITM0_1','menu':'Common data > Products > Products (GESITM)',
             'updates':{'ITM0_1.DES1AXX','ITM1_1.DES2AXX','ITM1_1.DES3AXX'}},
 'suppliers':{'publication':'WS_FOURNIS','object':'BPS','keys':['BPSNUM'],'key_group':'BPS0_1','menu':'Common data > BPs > Suppliers (GESBPS)',
              'updates':{'BPRS_1.BPRNAM','BPRS_1.BPRSHO'}},
 'article-sites':{'publication':'WS_AR_SITE','object':'ITF','keys':['ITMREF','STOFCY'],'key_group':'ITF0_1','menu':'Common data > Products > Products-sites (GESITF)',
                  'updates':{'ITF1_2.ABCCLS'}}}

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()
def path(group,name,row=None):return group+(f'[{row}]' if row else '')+'.'+name
def projection(root):
    result={}
    for group in root:
        tag=etree.QName(group).localname
        def add(parent,row=None):
            for field in parent:
                name=field.get('NAME') or field.get('NAM')
                if not name or re.search(r'PWD|PASSWORD|SECRET|TOKEN|CREUSR|UPDUSR|WW_MODUSER',name):continue
                key=path(group.get('ID',''),name,row)
                if etree.QName(field).localname=='FLD':result[key]=field.text or ''
                elif etree.QName(field).localname=='LST':result[key]=[n.text or '' for n in field]
        if tag=='GRP':add(group)
        elif tag=='TAB':
            for i,line in enumerate(group,1):add(line,int(line.get('NUM',str(i))))
    return result

def build_xml(desc,spec,request):
    if set(request.keys)!=set(spec['keys']):raise SageError('wrong_object_keys',422)
    params=etree.Element('PARAM');groups={};lines={}
    all_fields=[(spec['key_group'],key,value,None) for key,value in request.keys.items()]
    for f in request.fields:
        if f.name.startswith('WW_') or f.name in {'CREUSR','UPDUSR','CREDAT','UPDDAT'}:raise SageError('technical_audit_field_forbidden',422)
        if f.name in spec['keys']:raise SageError('key_changes_forbidden',422)
        if request.action=='update' and (f.group+'.'+f.name not in spec['updates'] or f.row is not None):raise SageError('field_update_not_allowed',422)
        all_fields.append((f.group,f.name,f.value,f.row))
    for group,name,value,row in all_fields:
        gm=desc.find('./ADXDATA/GRP[@NAM="'+group+'"]');fm=gm.find('./FLD[@NAM="'+name+'"]') if gm is not None else None
        if fm is None or fm.get('MOD')!='Input':raise SageError('unpublished_input_field',422)
        table=gm.get('TYB')=='Table'
        if table!=(row is not None) or (row and row>int(gm.get('DIM','0'))):raise SageError('wrong_table_row',422)
        dim=int(fm.get('DIM','1'))
        if (dim>1)!=isinstance(value,list) or isinstance(value,list) and len(value)!=dim:raise SageError('wrong_field_dimension',422)
        for item in value if isinstance(value,list) else [value]:
            typ=fm.get('TYP')
            if typ not in ['Char','Integer','Decimal','Date']:raise SageError('unsupported_field_type',422)
            if typ=='Char' and len(item)>int(fm.get('LEN','0')):raise SageError('field_too_long',422)
            if typ=='Integer' and not re.fullmatch(r'-?\d+',item):raise SageError('invalid_integer',422)
            if typ=='Decimal':
                try:
                    num=Decimal(item)
                    precision=fm.get('LEN','').split('.')
                    if not num.is_finite() or len(precision)!=2 or num.as_tuple().exponent < -int(precision[1]) or abs(num)>=Decimal(10)**int(precision[0]):raise ValueError()
                except (InvalidOperation,ValueError):raise SageError('invalid_decimal',422) from None
            if typ=='Date':
                from datetime import date
                try:date.fromisoformat(item)
                except ValueError:raise SageError('invalid_date',422) from None
            if fm.get('MEN'):
                allowed={n.get('IND') for n in desc.findall('./ADXMEN/MNU[@NO="'+fm.get('MEN')+'"]/VAL')}
                if item not in allowed:raise SageError('invalid_local_menu',422)
        if group not in groups:groups[group]=etree.SubElement(params,'TAB' if table else 'GRP',ID=group)
        parent=groups[group]
        if table:
            if (group,row) not in lines:lines[group,row]=etree.SubElement(parent,'LIN',NUM=str(row))
            parent=lines[group,row]
        if isinstance(value,list):
            node=etree.SubElement(parent,'LST',NAME=name,SIZE=str(dim))
            for item in value:etree.SubElement(node,'ITM').text=item
        else:etree.SubElement(parent,'FLD',NAME=name).text=value
    return etree.tostring(params,encoding='unicode',pretty_print=True)

class OneShotTransport(ReadOnlyTransport):
    def __init__(self,base,expected,**kwargs):super().__init__(base,**kwargs);self.expected=expected;self.used=False
    def post_xml(self,address,envelope,headers):
        body=envelope.find('{'+SOAP_NS+'}Body')
        if self.used or address!=self.base+SOAP_PATH or body is None or len(body)!=1:raise SageError('one_shot_transport_denied')
        node=body[0];e=self.expected
        values={etree.QName(n).localname:n for n in node}
        context=values.get('callContext');pool=next((n.text for n in context if etree.QName(n).localname=='poolAlias'),None) if context is not None else None
        if node.tag!='{'+NS+'}'+e['method'] or values.get('publicName') is None or values['publicName'].text!=e['publication'] or pool!=e['pool'] or values.get('objectXml') is None or hashlib.sha256((values['objectXml'].text or '').encode()).hexdigest()!=e['xml_hash']:
            raise SageError('one_shot_payload_mismatch')
        if e['method']=='modify':
            object_keys=values.get('objectKeys');pairs=[]
            if object_keys is not None:
                for parent in object_keys.iter():
                    children={etree.QName(n).localname:n.text for n in parent}
                    if 'key' in children and 'value' in children:pairs.append((children['key'],children['value']))
            if len(pairs)!=len(e['keys']) or dict(pairs)!=e['keys']:raise SageError('one_shot_key_mismatch')
        self.used=True
        return self._bounded('POST',address,data=etree.tostring(envelope,encoding='utf-8',xml_declaration=True),headers=headers)

class Gateway:
    def __init__(self,resource):
        if resource not in RESOURCES:raise SageError('unknown_resource',404)
        self.spec=RESOURCES[resource];self.resource=resource
        names=['sage_soap_base_url','sage_soap_username','sage_soap_password','sage_soap_pool','sage_soap_language','sage_soap_timeout','sage_soap_ca_bundle','sage_soap_crl_bundle']
        config=SimpleNamespace(**{n:getattr(settings,n) for n in names},sage_soap_publication=self.spec['publication'])
        self.reader=SageReader(config)
    def describe(self):
        desc=self.reader._invoke('getDescription')
        if any(desc.get(k)!=v for k,v in {'FOL':'TEST','SOL':'V12','PNA':self.spec['publication'],'OBJ':self.spec['object']}.items()):raise SageError('target_not_test',403)
        keys=[n.get('NAM') for n in desc.findall('./ADXREAD//FLD')]
        if keys!=self.spec['keys']:raise SageError('published_keys_changed')
        return desc
    def call(self,method,**kwargs):
        if method not in ['read','query']:raise SageError('operation_forbidden',403)
        session,service=self.reader._client()
        try:
            with service._client.settings(raw_response=True):
                response=getattr(service,method)(callContext={'codeLang':self.reader.config.sage_soap_language,'poolAlias':self.reader.config.sage_soap_pool,'poolId':'','requestConfig':'adxwss.optreturn=XML&adxwss.trace.on=off'},publicName=self.spec['publication'],**kwargs)
            return self.decode(response,method)
        finally:session.close()
    def decode(self,response,method):
        root=parse_xml(response.content);body=root.find('{'+SOAP_NS+'}Body')
        reply=body.find('{'+NS+'}'+method+'Response') if body is not None else None
        if response.status_code!=200 or reply is None:raise SageError('soap_response_invalid')
        nodes=[n for n in reply if etree.QName(n).localname==method+'Return']
        if len(nodes)!=1:raise SageError('soap_response_invalid')
        values={etree.QName(n).localname:n.text for n in nodes[0]}
        messages=[n.text or '' for n in nodes[0].iter() if etree.QName(n).localname=='message']
        for secret in [settings.sage_soap_username.get_secret_value(),settings.sage_soap_password.get_secret_value()]:
            if secret:messages=[text.replace(secret,'[REDACTED]') for text in messages]
        return {'status':int(values.get('status','-1')),'messages':messages,'xml':values.get('resultXml')}
    def read(self,keys,describe=True):
        if describe:
            desc=self.describe()
            for n in desc.findall('./ADXREAD//FLD'):
                value=keys.get(n.get('NAM'))
                if not isinstance(value,str) or not value or len(value)>int(n.get('LEN','20')) or not re.fullmatch(r'[A-Za-z0-9_./ -]+',value):raise SageError('invalid_record_key',422)
        if set(keys)!=set(self.spec['keys']):raise SageError('wrong_object_keys',422)
        result=self.call('read',objectKeys=[{'key':k,'value':v} for k,v in keys.items()])
        if result['status']==0 and not result['xml'] and 'Fiche inexistante' in result['messages']:return {'exists':False,'keys':keys,'status':0,'messages':result['messages']}
        if result['status']!=1 or not result['xml']:raise SageError('read_existence_unknown')
        fields=projection(parse_xml(result['xml']))
        for key,value in keys.items():
            if fields.get(self.spec['key_group']+'.'+key)!=value:raise SageError('read_key_mismatch')
        return {'exists':True,'keys':keys,'status':1,'messages':result['messages'],'fields':fields,'fingerprint':digest(fields)}
    def query(self,limit):
        self.describe()
        result=self.call('query',objectKeys=[{'key':k,'value':''} for k in self.spec['keys']],listSize=limit)
        if result['status']!=1 or not result['xml']:raise SageError('query_failed')
        root=parse_xml(result['xml']);records=[]
        if root.tag!='RESULT':raise SageError('query_format_unknown')
        for line in root.findall('LIN'):
            records.append({n.get('NAME'):n.text or '' for n in line.findall('FLD') if n.get('NAME')})
        if len(records)>limit:raise SageError('query_limit_violated')
        return {'records':records,'limit':limit,'possibly_truncated':len(records)==limit,'status':1,'messages':result['messages'],'resource':self.resource,'folder':'TEST'}
    def write_once(self,action,keys,xml,operation_id):
        # Called only after atomic approval consumption and all security/precondition checks.
        from app.services.sage_crud import authorize_transport
        authorize_transport(operation_id,self.resource,action,xml)
        method='save' if action=='create' else 'modify'
        session,service=self.reader._client()
        try:
            expected={'method':method,'publication':self.spec['publication'],'pool':self.reader.config.sage_soap_pool,'xml_hash':hashlib.sha256(xml.encode()).hexdigest(),'keys':keys}
            service._client.transport=OneShotTransport(self.reader.config.sage_soap_base_url.rstrip('/'),expected,session=session,timeout=settings.sage_soap_timeout,operation_timeout=settings.sage_soap_timeout)
            args={'objectXml':xml}
            if method=='modify':args['objectKeys']=[{'key':k,'value':v} for k,v in keys.items()]
            with service._client.settings(raw_response=True):
                response=getattr(service,method)(callContext={'codeLang':'FRA','poolAlias':self.reader.config.sage_soap_pool,'poolId':'','requestConfig':'adxwss.optreturn=XML&adxwss.trace.on=off'},publicName=self.spec['publication'],**args)
            proof=archive_write_response(operation_id,response.content)
            return {**self.decode(response,method),**proof}
        finally:session.close()
