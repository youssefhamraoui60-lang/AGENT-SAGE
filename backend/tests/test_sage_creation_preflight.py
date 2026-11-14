from pathlib import Path
import pytest
from lxml import etree
from app.services.sage_soap import SageError
from app.services.sage_creation_preflight import build_object_xml,validate_target

@pytest.fixture
def description():
    # Actual publication shape, synthetic metadata fixture; no ERP calls during these tests.
    root=etree.Element('ADXDOC',FOL='TEST',SOL='V12',PNA='WS_ARTICLE',OBJ='ITM')
    data=etree.SubElement(root,'ADXDATA')
    definitions={'ITM0_1':[('TCLCOD','Char','5'),('ITMSTA','Integer','15'),('ITMREF','Char','20'),('DES1AXX','Char','70')],
                 'ITM1_5':[('TSICOD','Char','20')],'ITM2_1':[('STOMGTCOD','Integer','15')],
                 'ITM3_1':[('STU','Char','3'),('PUU','Char','3'),('PUUSTUCOE','Decimal','5.6'),('SAU','Char','3'),('SAUSTUCOE','Decimal','5.6')]}
    for name,fields in definitions.items():
        group=etree.SubElement(data,'GRP',NAM=name)
        for field,kind,length in fields:
            node=etree.SubElement(group,'FLD',NAM=field,TYP=kind,LEN=length,MOD='Input')
            if field=='TSICOD':node.set('DIM','3')
    services=etree.SubElement(root,'ADXSER');etree.SubElement(services,'MET',ID='CREATE')
    return root

@pytest.mark.parametrize('attribute,value',[('FOL','PRODUCTION'),('SOL','OTHER'),('PNA','OTHER'),('OBJ','BPC')])
def test_target_mismatch_blocks_preparation(description,attribute,value):
    description.set(attribute,value)
    with pytest.raises(SageError):validate_target(description)

def test_offline_payload_does_not_copy_existing_article(description):
    content,fields=build_object_xml(description,'TSTAI261017ABCDEF','TEST IA SOAP <EXEMPLE> & TEST')
    root=etree.fromstring(content.encode())
    assert root.tag=='PARAM'
    assert root.find('.//FLD[@NAME="ITMREF"]').text=='TSTAI261017ABCDEF'
    assert root.find('.//FLD[@NAME="DES1AXX"]').text=='TEST IA SOAP <EXEMPLE> & TEST'
    assert root.find('.//FLD[@NAME="XBPS"]') is None
    assert root.find('.//FLD[@NAME="WW_MODUSER"]') is None
    assert root.find('.//LST[@NAME="TSICOD"]').get('SIZE')=='3'

def test_display_only_or_missing_field_blocks(description):
    description.find('.//FLD[@NAM="ITMREF"]').set('MOD','Display')
    with pytest.raises(ValueError):build_object_xml(description,'TSTAI261017ABCDEF','TEST IA SOAP EXEMPLE')

def test_published_length_enforced(description):
    description.find('.//FLD[@NAM="ITMREF"]').set('LEN','10')
    with pytest.raises(ValueError):build_object_xml(description,'TSTAI261017ABCDEF','TEST IA SOAP EXEMPLE')

def test_non_test_reference_refused(description):
    with pytest.raises(ValueError):build_object_xml(description,'CPJ35','TEST IA SOAP EXEMPLE')

def test_unavailable_create_method_blocks(description):
    description.find('.//MET').set('ID','READ')
    with pytest.raises(SageError):validate_target(description)
