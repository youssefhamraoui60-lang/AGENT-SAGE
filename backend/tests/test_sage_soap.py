from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from lxml import etree
from pydantic import SecretStr
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.services import sage_soap as soap

@pytest.mark.parametrize('operation',['save','delete','modify','run','actionObject','actionObjectKeys','insertLines','deleteLines','getDataXmlSchema'])
def test_write_and_unapproved_operations_never_reach_transport(operation):
    transport=soap.ReadOnlyTransport('http://192.168.9.200:8124')
    envelope=etree.Element('{'+soap.SOAP_NS+'}Envelope')
    body=etree.SubElement(envelope,'{'+soap.SOAP_NS+'}Body')
    etree.SubElement(body,'{'+soap.NS+'}'+operation)
    with pytest.raises(soap.SageError,match='sage_operation_not_allowed'):
        transport.post_xml(transport.base+soap.SOAP_PATH,envelope,{})

@pytest.mark.parametrize('url',['http://evil.invalid/schema','file:///C:/Windows/win.ini','http://127.0.0.1:5678/'])
def test_external_wsdl_imports_blocked(url):
    transport=soap.ReadOnlyTransport('http://192.168.9.200:8124')
    with pytest.raises(soap.SageError,match='sage_unapproved_wsdl_import'): transport.load(url)

def test_standard_schema_bundled_not_downloaded(monkeypatch):
    transport=soap.ReadOnlyTransport('http://192.168.9.200:8124')
    monkeypatch.setattr(transport.session,'request',lambda *a,**k:pytest.fail('network not allowed'))
    assert b'schema' in transport.load('http://schemas.xmlsoap.org/soap/encoding/')

@pytest.mark.parametrize('xml',[b'<!DOCTYPE x [<!ENTITY y SYSTEM "file:///C:/Windows/win.ini">]><x>&y;</x>',b'<broken',b'x'*4_000_001],ids=['entity','malformed','oversized'])
def test_unsafe_or_invalid_xml_rejected(xml):
    with pytest.raises(soap.SageError): soap.parse_xml(xml)

def test_missing_credentials_safe_failure():
    config=SimpleNamespace(sage_soap_base_url='http://192.168.9.200:8124',sage_soap_username=SecretStr(''),sage_soap_password=SecretStr(''))
    with pytest.raises(soap.SageError,match='sage_credentials_not_configured'): soap.SageReader(config)._client()

def test_query_uses_real_published_key_and_bounded_limit(monkeypatch):
    reader=soap.SageReader();calls=[]
    def invoke(operation,**kwargs):
        calls.append((operation,kwargs))
        return soap.parse_xml('<ADXDOC><FLD NAM="ITMREF"/></ADXDOC>' if operation=='getDescription' else '<RESULT><LIN><FLD NAME="ITMREF">CPJ35</FLD><FLD NAME="C2">Produit test</FLD></LIN></RESULT>')
    monkeypatch.setattr(reader,'_invoke',invoke)
    result=reader.articles(10)
    assert result['count']==1 and result['articles'][0]['ITMREF']=='CPJ35'
    assert calls[1]==('query',{'objectKeys':[{'key':'ITMREF','value':''}],'listSize':10})
    with pytest.raises(soap.SageError): reader.articles(51)

def test_unknown_published_key_blocks_read(monkeypatch):
    reader=soap.SageReader();monkeypatch.setattr(reader,'_invoke',lambda *a,**k:soap.parse_xml('<ADXDOC/>'))
    with pytest.raises(soap.SageError,match='sage_article_key_not_published'): reader.read_article('CPJ35')

def test_read_checks_reference_and_omits_author_identity(monkeypatch):
    reader=soap.SageReader()
    monkeypatch.setattr(reader,'_check_article_key',lambda:None)
    monkeypatch.setattr(reader,'_invoke',lambda *a,**k:soap.parse_xml('<RESULT><GRP><FLD NAME="ITMREF">CPJ35</FLD><FLD NAME="CREUSR">SECRET_AUTHOR</FLD></GRP></RESULT>'))
    assert reader.read_article('CPJ35')['article']=={'ITMREF':'CPJ35'}
    with pytest.raises(soap.SageError,match='sage_article_reference_mismatch'): reader.read_article('OTHER')
    with pytest.raises(soap.SageError,match='sage_invalid_reference'): reader.read_article('<bad>')

def test_protected_routes_and_no_write_route(monkeypatch):
    monkeypatch.setattr(settings,'approval_token',SecretStr('synthetic-test-token'))
    client=TestClient(app)
    for path in ['/status','/description','/articles','/articles/CPJ35']:
        assert client.get('/api/v1/sage'+path).status_code==403
    for method in ['post','put','patch','delete']:
        assert getattr(client,method)('/api/v1/sage/articles',headers={'X-Approval-Token':'synthetic-test-token'}).status_code==(423 if method=='post' else 405)

def test_rpc_reply_missing_messages_is_validated_explicitly(monkeypatch):
    @contextmanager
    def raw_settings(**kwargs): yield
    xml=f'<s:Envelope xmlns:s="{soap.SOAP_NS}"><s:Body><w:readResponse xmlns:w="{soap.NS}"><readReturn><status>1</status><resultXml>&lt;RESULT/&gt;</resultXml></readReturn></w:readResponse></s:Body></s:Envelope>'
    service=SimpleNamespace(_client=SimpleNamespace(settings=raw_settings),read=lambda **kwargs:SimpleNamespace(status_code=200,content=xml.encode()))
    reader=soap.SageReader()
    monkeypatch.setattr(reader,'_client',lambda:(SimpleNamespace(close=lambda:None),service))
    assert reader._invoke('read',objectKeys=[]).tag=='RESULT'

def test_fault_is_redacted(monkeypatch):
    @contextmanager
    def raw_settings(**kwargs): yield
    xml=f'<s:Envelope xmlns:s="{soap.SOAP_NS}"><s:Body><s:Fault><faultstring>SECRET</faultstring></s:Fault></s:Body></s:Envelope>'
    service=SimpleNamespace(_client=SimpleNamespace(settings=raw_settings),read=lambda **kwargs:SimpleNamespace(status_code=500,content=xml.encode()))
    reader=soap.SageReader();monkeypatch.setattr(reader,'_client',lambda:(SimpleNamespace(close=lambda:None),service))
    with pytest.raises(soap.SageError,match='sage_soap_fault') as exc: reader._invoke('read')
    assert 'SECRET' not in str(exc.value)
