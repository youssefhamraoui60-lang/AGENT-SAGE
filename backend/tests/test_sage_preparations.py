from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4
import pytest
from lxml import etree
from fastapi.testclient import TestClient
from pydantic import SecretStr,ValidationError
from app.main import app
from app.core.config import settings
from app.schemas.sage_preparation import ArticlePreparation
from app.services import sage_preparations as service,business_store as store
from app.services.sage_soap import SageError,SOAP_NS,NS

def payload():
    return dict(reference='TST_DRAFT_ONLY',designation='Brouillon synthétique sans envoi',categorie='NEG',unite_stock='SAC',unite_achat='SAC',unite_vente='SAC',coefficient_achat='1',coefficient_vente='1')

def metadata():
    root=etree.Element('ADXDOC',FOL='TEST',SOL='V12',PNA='WS_ARTICLE',OBJ='ITM')
    data=etree.SubElement(root,'ADXDATA')
    for group,fields in [('ITM0_1',[('TCLCOD',5),('ITMREF',20),('DES1AXX',70)]),('ITM3_1',[('STU',3),('PUU',3),('SAU',3),('PUUSTUCOE',20),('SAUSTUCOE',20)])]:
        node=etree.SubElement(data,'GRP',NAM=group)
        for name,length in fields:etree.SubElement(node,'FLD',NAM=name,TYP='Decimal' if 'COE' in name else 'Char',MOD='Input',LEN=str(length))
    etree.SubElement(etree.SubElement(root,'ADXSER'),'MET',ID='CREATE')
    return root

@pytest.mark.parametrize('coefficient',['0','-1','NaN','Infinity','1,5','100000','0.0000001'])
def test_bad_coefficients_rejected(coefficient):
    value=payload();value['coefficient_achat']=coefficient
    with pytest.raises(ValidationError):ArticlePreparation(**value)

@pytest.mark.parametrize('extra',[{'approved':True},{'folder':'PRODUCTION'},{'operation':'save'}])
def test_caller_cannot_inject_approval_target_or_operation(extra):
    with pytest.raises(ValidationError):ArticlePreparation(**(payload()|extra))

def test_xml_escaping_and_no_old_defaults():
    value=payload();value['designation']='Test <XML> & brouillon'
    xml=service.build_draft(metadata(),ArticlePreparation(**value));root=etree.fromstring(xml.encode())
    assert root.find('.//FLD[@NAME="DES1AXX"]').text==value['designation']
    assert root.find('.//FLD[@NAME="TCLCOD"]').text=='NEG'
    assert root.find('.//FLD[@NAME="STU"]').text=='SAC'
    assert root.find('.//FLD[@NAME="ITMSTA"]') is None
    assert root.find('.//LST[@NAME="TSICOD"]') is None

def test_optional_fields_follow_published_menus_and_manual_order():
    desc=metadata();data=desc.find('ADXDATA');menus=etree.SubElement(desc,'ADXMEN')
    for group,name,length,menu,value in [('ITM0_1','ITMSTA','15','246','1'),('ITM2_1','STOMGTCOD','15','215','2'),('ITM2_3','LOTMGTCOD','20','2711','3'),('ITM5_1','ACCCOD','10',None,'CPJ35')]:
        node=data.find('./GRP[@NAM="'+group+'"]')
        if node is None:node=etree.SubElement(data,'GRP',NAM=group)
        field=etree.SubElement(node,'FLD',NAM=name,TYP='Integer' if menu else 'Char',MOD='Input',LEN=length)
        if menu:
            field.set('MEN',menu);etree.SubElement(etree.SubElement(menus,'MNU',NO=menu),'VAL',IND=value)
    value=payload()|dict(statut='1',gestion_stock='2',gestion_lots='3',code_comptable='CPJ35')
    root=etree.fromstring(service.build_draft(desc,ArticlePreparation(**value)).encode())
    assert len(root.findall('.//FLD'))==12
    assert [node.get('NAME') for node in root.find('GRP')]==['TCLCOD','ITMSTA','ITMREF','DES1AXX']
    assert root.find('.//FLD[@NAME="ACCCOD"]').text=='CPJ35'
    with pytest.raises(SageError,match='sage_invalid_local_menu_value'):
        service.build_draft(desc,ArticlePreparation(**(value|{'gestion_lots':'9'})))

@pytest.mark.parametrize('status,message,xml,expected',[
    ('0','Fiche inexistante','',False),('0','Accès refusé','',None),
    ('1','', '<RESULT><GRP><FLD NAME="ITMREF">TST_DRAFT_ONLY</FLD></GRP></RESULT>',True),
    ('1','','<RESULT><GRP><FLD NAME="ITMREF">WRONG</FLD></GRP></RESULT>',None)])
def test_absence_requires_explicit_not_found(status,message,xml,expected):
    env=etree.Element('{'+SOAP_NS+'}Envelope');body=etree.SubElement(env,'{'+SOAP_NS+'}Body');reply=etree.SubElement(body,'{'+NS+'}readResponse');returned=etree.SubElement(reply,'readReturn')
    etree.SubElement(returned,'status').text=status;etree.SubElement(returned,'resultXml').text=xml
    etree.SubElement(etree.SubElement(returned,'messages'),'message').text=message
    @contextmanager
    def raw_settings(**kwargs):yield
    svc=SimpleNamespace(_client=SimpleNamespace(settings=raw_settings),read=lambda **kwargs:SimpleNamespace(status_code=200,content=etree.tostring(env)))
    reader=SimpleNamespace(config=SimpleNamespace(sage_soap_language='FRA',sage_soap_pool='POOL_AI_TEST',sage_soap_publication='WS_ARTICLE'),_client=lambda:(SimpleNamespace(close=lambda:None),svc))
    if expected is None:
        with pytest.raises(SageError):service.probe_reference(reader,'TST_DRAFT_ONLY')
    else:assert service.probe_reference(reader,'TST_DRAFT_ONLY')['exists'] is expected

@pytest.fixture
def db(monkeypatch):
    import os
    if os.environ.get('RUN_STEP2_INTEGRATION')!='1':pytest.skip('Real local PostgreSQL integration disabled')
    monkeypatch.setattr(settings,'business_schema','sage_draft_test_'+uuid4().hex[:12])
    monkeypatch.setattr(settings,'approval_token',SecretStr('synthetic-draft-token'))
    store.migrate();assert service.migrate() is True;assert service.migrate() is False
    monkeypatch.setattr(service.SageReader,'_invoke',lambda *a,**k:metadata())
    return TestClient(app)

@pytest.mark.parametrize('exists,expected',[(True,'blocked_existing'),(False,'awaiting_human_review'),(None,'blocked_unknown')])
def test_draft_persisted_without_approval_or_sage_write(db,monkeypatch,exists,expected):
    monkeypatch.setattr(service,'probe_reference',lambda *a:{'exists':exists,'source':'synthetic-test'})
    headers={'X-Approval-Token':'synthetic-draft-token'}
    response=db.post('/api/v1/sage/article-preparations',headers=headers,json=payload())
    assert response.status_code==200,response.text
    result=response.json();assert result['status']==expected
    assert result['sage_write_enabled'] is False and result['requires_human_approval'] is True
    assert result['checks']['human_approved'] is False
    response=db.get('/api/v1/sage/article-preparations/'+result['id'],headers=headers)
    assert response.json()==result
    assert db.post('/api/v1/sage/article-preparations',json=payload()).status_code==403
    assert db.post('/api/v1/sage/articles',headers=headers,json=payload()).status_code==423
