"""Offline-only preparation of one test article. This module cannot send save."""
from decimal import Decimal,InvalidOperation
import re
from lxml import etree
from app.services.sage_soap import SageError,parse_xml

def validate_target(description):
    expected={'FOL':'TEST','SOL':'V12','PNA':'WS_ARTICLE','OBJ':'ITM'}
    if any(description.get(key)!=value for key,value in expected.items()):
        raise SageError('creation_preparation_wrong_target')
    if 'CREATE' not in {node.get('ID') for node in description.iter('MET')}:
        raise SageError('creation_not_declared_by_publication')

def build_object_xml(description,reference,designation):
    validate_target(description)
    if not re.fullmatch(r'TSTAI[0-9A-F]{12}',reference): raise ValueError('Test reference pattern required')
    if not designation.startswith('TEST IA SOAP '): raise ValueError('Explicit test designation required')
    groups=[('ITM0_1',{'TCLCOD':'DIVE','ITMSTA':'2','ITMREF':reference,'DES1AXX':designation}),
            ('ITM1_5',{'TSICOD':['FG','','']}),('ITM2_1',{'STOMGTCOD':'1'}),
            ('ITM3_1',{'STU':'UN','PUU':'UN','PUUSTUCOE':'1','SAU':'UN','SAUSTUCOE':'1'})]
    result=etree.Element('PARAM');validated=[]
    for group_name,values in groups:
        metadata=description.find('./ADXDATA/GRP[@NAM="'+group_name+'"]')
        if metadata is None: raise ValueError('Unpublished group')
        group=etree.SubElement(result,'GRP',ID=group_name)
        for name,value in values.items():
            field=metadata.find('./FLD[@NAM="'+name+'"]')
            if field is None or field.get('MOD')!='Input': raise ValueError('Unpublished or non-input field')
            entries=value if isinstance(value,list) else [value]
            if isinstance(value,list) and len(value)!=int(field.get('DIM','1')): raise ValueError('Invalid array dimension')
            for entry in entries:
                if field.get('TYP')=='Char' and len(entry)>int(field.get('LEN','0')): raise ValueError('Field too long')
                if field.get('TYP')=='Integer' and not re.fullmatch(r'\d+',entry): raise ValueError('Invalid integer')
                if field.get('TYP')=='Decimal':
                    try:
                        if not Decimal(entry).is_finite(): raise ValueError('Invalid decimal')
                    except InvalidOperation: raise ValueError('Invalid decimal') from None
                if field.get('MEN'):
                    allowed={node.get('IND') for node in description.findall('./ADXMEN/MNU[@NO="'+field.get('MEN')+'"]/VAL')}
                    if entry not in allowed: raise ValueError('Unpublished menu value')
            if isinstance(value,list):
                node=etree.SubElement(group,'LST',NAME=name,SIZE=str(len(value)))
                for entry in value: etree.SubElement(node,'ITM').text=entry
            else: etree.SubElement(group,'FLD',NAME=name).text=value
            validated.append({'group':group_name,'field':name,'value':value,'published_type':field.get('TYP'),
                              'checks':['published_input','type_length_dimension','local_menu_if_applicable']})
    content=etree.tostring(result,encoding='unicode',pretty_print=True)
    parse_xml(content)
    return content,validated
