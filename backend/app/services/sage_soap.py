"""Bounded read-only Sage SOAP facade. No generic operation dispatcher is exposed."""
from urllib.parse import urlsplit
import threading
import re
from pathlib import Path
from lxml import etree
import requests
from requests.auth import HTTPBasicAuth
from zeep import Client, Settings as ZeepSettings
from zeep.transports import Transport
from zeep.exceptions import Error as ZeepError, TransportError
from app.core.config import settings

WSDL_PATH='/soap-wsdl/syracuse/collaboration/syracuse/CAdxWebServiceXmlCC?wsdl'
SOAP_PATH='/soap-generic/syracuse/collaboration/syracuse/CAdxWebServiceXmlCC'
NS='http://www.adonix.com/WSS'
SOAP_NS='http://schemas.xmlsoap.org/soap/envelope/'
ALLOWED=frozenset({'getDescription','query','read'})
MAX_BYTES=4_000_000
GATE=threading.BoundedSemaphore(2)

class SageError(Exception):
    def __init__(self,code,status=502): self.code=code;self.status=status;super().__init__(code)

def parse_xml(content):
    if isinstance(content,str): content=content.encode('utf-8')
    if len(content)>MAX_BYTES: raise SageError('sage_response_too_large')
    if b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper(): raise SageError('sage_unsafe_xml')
    try: return etree.fromstring(content,parser=etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False))
    except etree.XMLSyntaxError: raise SageError('sage_invalid_xml') from None

class ReadOnlyTransport(Transport):
    """Pin network destinations and block unsafe SOAP methods even if called via Zeep."""
    def __init__(self,base,**kwargs): self.base=base;super().__init__(**kwargs)
    def load(self,url):
        bundled={'http://schemas.xmlsoap.org/soap/encoding/':'soap-encoding.xsd',
                 'https://schemas.xmlsoap.org/soap/encoding/':'soap-encoding.xsd',
                 'http://www.w3.org/2001/xml.xsd':'xml.xsd','https://www.w3.org/2001/xml.xsd':'xml.xsd'}
        if url in bundled:
            return (Path(__file__).resolve().parents[1]/'schemas'/'soap'/bundled[url]).read_bytes()
        if url!=self.base+WSDL_PATH: raise SageError('sage_unapproved_wsdl_import')
        return self._bounded('GET',url).content
    def _bounded(self,method,url,**kwargs):
        with self.session.request(method,url,timeout=self.operation_timeout,allow_redirects=False,stream=True,**kwargs) as response:
            if response.is_redirect: raise SageError('sage_redirect_blocked')
            if response.status_code in (401,403): raise SageError('sage_authentication_required',502)
            data=bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data)>MAX_BYTES: raise SageError('sage_response_too_large')
            response._content=bytes(data);response._content_consumed=True
            return response
    def post_xml(self,address,envelope,headers):
        if address!=self.base+SOAP_PATH: raise SageError('sage_endpoint_not_allowed')
        body=envelope.find('{'+SOAP_NS+'}Body')
        if body is None or len(body)!=1: raise SageError('sage_operation_not_allowed')
        operation=etree.QName(body[0])
        if operation.namespace!=NS or operation.localname not in ALLOWED: raise SageError('sage_operation_not_allowed')
        response=self._bounded('POST',address,data=etree.tostring(envelope,xml_declaration=True,encoding='utf-8'),headers=headers)
        return response

class SageReader:
    def __init__(self,config=settings): self.config=config
    def _client(self):
        config=self.config
        base=config.sage_soap_base_url.rstrip('/')
        parsed=urlsplit(base)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise SageError('sage_invalid_base_url',503)
        session=requests.Session();session.trust_env=False
        ca_bundle=getattr(config,'sage_soap_ca_bundle','')
        if ca_bundle:
            if not Path(ca_bundle).is_file():session.close();raise SageError('sage_ca_bundle_missing',503)
            session.verify=ca_bundle
        if parsed.scheme=='https':
            from app.services.sage_tls import verified_context,VerifiedSOAPAdapter,TLSConfigurationError
            try:session.mount('https://',VerifiedSOAPAdapter(verified_context(config)))
            except TLSConfigurationError as exc:
                session.close();raise SageError(str(exc),503) from None
        user=config.sage_soap_username.get_secret_value();password=config.sage_soap_password.get_secret_value()
        if not user or not password: session.close();raise SageError('sage_credentials_not_configured',503)
        session.auth=HTTPBasicAuth(user,password)
        transport=ReadOnlyTransport(base,session=session,timeout=config.sage_soap_timeout,operation_timeout=config.sage_soap_timeout)
        try:
            # Standard SOAP imports resolve to bundled files; transport rejects every other import.
            client=Client(base+WSDL_PATH,transport=transport,settings=ZeepSettings(strict=True,forbid_dtd=True,forbid_entities=True,forbid_external=False))
            service=client.create_service('{'+NS+'}CAdxWebServiceXmlCCSoapBinding',base+SOAP_PATH)
            return session,service
        except Exception: session.close();raise
    def _invoke(self,operation,**kwargs):
        if operation not in ALLOWED: raise SageError('sage_operation_not_allowed')
        if not GATE.acquire(blocking=False): raise SageError('sage_busy',503)
        session=None
        try:
            session,service=self._client()
            # The real Syracuse response omits the WSDL's mandatory messages member.
            # Keep strict WSDL/request validation and validate the bounded SOAP reply explicitly.
            with service._client.settings(raw_response=True):
                response=getattr(service,operation)(callContext={'codeLang':self.config.sage_soap_language,
                    'poolAlias':self.config.sage_soap_pool,'poolId':'','requestConfig':'adxwss.optreturn=XML&adxwss.trace.on=off'},
                    publicName=self.config.sage_soap_publication,**kwargs)
            root=parse_xml(response.content)
            body=root.find('{'+SOAP_NS+'}Body')
            if body is None: raise SageError('sage_invalid_response')
            if body.find('{'+SOAP_NS+'}Fault') is not None: raise SageError('sage_soap_fault')
            if response.status_code!=200: raise SageError('sage_http_error')
            replies=[node for node in body if etree.QName(node).localname==operation+'Response' and etree.QName(node).namespace==NS]
            if len(replies)!=1: raise SageError('sage_invalid_response')
            returns=[node for node in replies[0] if etree.QName(node).localname==operation+'Return']
            if len(returns)!=1: raise SageError('sage_invalid_response')
            values={etree.QName(node).localname:node.text for node in returns[0]}
            if values.get('status')!='1': raise SageError('sage_business_error')
            xml=values.get('resultXml') or ''
            if not xml: raise SageError('sage_missing_result')
            return parse_xml(xml)
        except SageError: raise
        except requests.exceptions.SSLError: raise SageError('sage_tls_validation_failed',503) from None
        except requests.Timeout: raise SageError('sage_timeout',504) from None
        except requests.RequestException: raise SageError('sage_network_error',503) from None
        except (ZeepError,ValueError,TypeError,AttributeError): raise SageError('sage_invalid_response') from None
        finally:
            if session is not None: session.close()
            GATE.release()
    def describe(self):
        root=self._invoke('getDescription')
        # Reflect published metadata without guessing the installation's article fields.
        fields=[]
        for item in root.iter():
            if etree.QName(item).localname in ('FLD','FIELD'):
                fields.append(dict(item.attrib))
        return {'publication':self.config.sage_soap_publication,'pool':self.config.sage_soap_pool,
                'fields':fields,'read_only':True}
    def _check_article_key(self):
        description=self._invoke('getDescription')
        if not any((node.get('NAM') or node.get('NAME'))=='ITMREF' for node in description.iter()):
            raise SageError('sage_article_key_not_published')
    def read_article(self,reference):
        if not re.fullmatch(r'[A-Za-z0-9_. -]{1,20}',reference): raise SageError('sage_invalid_reference',422)
        self._check_article_key()
        root=self._invoke('read',objectKeys=[{'key':'ITMREF','value':reference}])
        if etree.QName(root).localname!='RESULT': raise SageError('sage_unrecognized_article_result')
        fields={}
        # Only expose article fields, excluding technical traces and author/login identifiers.
        allowed={'ITMREF','DES1AXX','DES2AXX','DES3AXX','TCLCOD','ITMSTA','STU','SAU','PUU','XBPS','SEAKEY','EANCOD',
                 'PUUSTUCOE','SAUSTUCOE','LOTMGTCOD','ACCCOD','STOMGTCOD'}
        for node in root.iter():
            name=node.get('NAME') or node.get('NAM')
            if etree.QName(node).localname=='FLD' and name in allowed and name not in fields:
                fields[name]=''.join(node.itertext())
        if fields.get('ITMREF')!=reference: raise SageError('sage_article_reference_mismatch')
        return {'article':fields,'source':'sage_live','publication':self.config.sage_soap_publication,'read_only':True}
    def articles(self,limit=20):
        if type(limit) is not int or not 1<=limit<=50: raise SageError('sage_invalid_limit',422)
        self._check_article_key()
        # RPC encoded array cannot be empty in this WSDL. Start at the empty ITMREF key.
        root=self._invoke('query',objectKeys=[{'key':'ITMREF','value':''}],listSize=limit)
        if etree.QName(root).localname!='RESULT': raise SageError('sage_unrecognized_article_result')
        rows=[]
        for line in root:
            if etree.QName(line).localname!='LIN': continue
            row={}
            for field in line:
                if etree.QName(field).localname!='FLD': continue
                name=field.get('NAME') or field.get('NAM')
                if not name or name in row: raise SageError('sage_invalid_article_fields')
                row[name]=''.join(field.itertext())
            if not row: raise SageError('sage_empty_article_fields')
            rows.append(row)
        if len(rows)>limit: raise SageError('sage_list_limit_violated')
        return {'articles':rows,'count':len(rows),'limit':limit,'possibly_truncated':len(rows)==limit,
                'source':'sage_live','publication':self.config.sage_soap_publication,'read_only':True}
