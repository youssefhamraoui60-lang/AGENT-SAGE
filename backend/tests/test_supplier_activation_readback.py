"""Controlled supplier post-SAVE checks; no Sage write or external SQL."""
from copy import deepcopy
from pathlib import Path
import pytest
from app.services import supplier_readback as readback,chat_supplier_preparation as prep,chat_fast_extract as fast,conversation_chat as chat
from app.services.supplier_xml import proposal
from app.services.sage_soap import parse_xml


def fixture_data():
    fields={'BPRS_1.BPRNAM':['SYNTH SUPPLIER',''],'BPRS_1.BPRSHO':'SYNTH','BPRS_1.XICE':'001850814000094','BPRS_1.XIF':'20734927','BPRS_1.XRC':'10909','BPRS_1.CRY':'MA','BPRS_1.CUR':'MAD','BPS0_1.BSGCOD':'FR','BPS0_1.ENAFLG':'2','BPS2_2.PTE':'CHQ00'}
    payload={'fields':[{'group':p.split('.')[0],'name':p.split('.')[1],'value':v} for p,v in fields.items()]}
    row={'folder':'TEST','BPSNUM_0':'F0012','BPRNUM_0':'F0012','BPRNAM_0':'SYNTH SUPPLIER','BPSNAM_0':'SYNTH SUPPLIER','BPRSHO_0':'SYNTH','BPSSHO_0':'SYNTH','XICE_0':'001850814000094','XIF_0':'20734927','XRC_0':'10909','CRY_0':'MA','CUR_0':'MAD','BSGCOD_0':'FR','supplier_active':2,'partner_active':2,'PTE_0':'CHQ00'}
    soap={'exists':True,'fields':{**fields,'BPS0_1.BPSNUM':'F0012'}}
    sql={'ok':True,'source':'SQL TEST','folder':'TEST','rows':[row]}
    return {'keys':{'BPSNUM':'F0012'},'payload':payload,'soap':soap,'save':{'status':1,'messages':[]},'sql':sql}


def test_created_and_active_requires_all_sources_and_uses_actual_code():
    result=readback.verify(**fixture_data())
    assert result['confirmed'] and result['created_and_active']
    message=readback.message(result)
    assert 'F0012' in message and 'F10022' not in message and 'TEST' in message
    assert 'créé et activé avec succès' in message


@pytest.mark.parametrize('case',['supplier_inactive','partner_inactive','name_wrong','code_wrong','ice_wrong','if_wrong','rc_wrong','sql_missing','sql_OB','soap_missing','soap_code_wrong','soap_name_wrong','save_refused','save_ambiguous','payment_wrong','country_wrong','currency_wrong','category_wrong','second_name_missing','sql_second_row'])
def test_incomplete_or_mismatched_creation_never_claims_success(case):
    args=fixture_data();row=args['sql']['rows'][0];soap=args['soap']
    values={'supplier_inactive':('supplier_active',1),'partner_inactive':('partner_active',1),'name_wrong':('BPSNAM_0','erreur'),'code_wrong':('BPSNUM_0','F0099'),'ice_wrong':('XICE_0','1850814000094'),'if_wrong':('XIF_0','0'),'rc_wrong':('XRC_0','0'),'payment_wrong':('PTE_0','OTHER'),'country_wrong':('CRY_0','FR'),'currency_wrong':('CUR_0','EUR'),'category_wrong':('BSGCOD_0','OTHER')}
    if case in values:row[values[case][0]]=values[case][1]
    elif case=='sql_missing':args['sql']['rows']=[]
    elif case=='sql_OB':args['sql']['folder']='OB';row['folder']='OB'
    elif case=='soap_missing':soap['exists']=False
    elif case=='soap_code_wrong':soap['fields']['BPS0_1.BPSNUM']='F0099'
    elif case=='soap_name_wrong':soap['fields']['BPRS_1.BPRNAM']=['erreur','']
    elif case=='save_refused':args['save']={'status':0,'messages':[{'message':'refus'}]}
    elif case=='save_ambiguous':args['save']={'code':'write_outcome_unknown'}
    elif case=='second_name_missing':soap['fields']['BPRS_1.BPRNAM']=['SYNTH SUPPLIER']
    elif case=='sql_second_row':args['sql']['rows'].append(deepcopy(row))
    result=readback.verify(**args)
    assert not result['confirmed'] and not result['created_and_active'] and not result['retry_allowed']
    assert 'créé et activé avec succès' not in readback.message(result)


def test_warning_requires_successful_readback_but_is_preserved():
    args=fixture_data();args['save']['messages']=[{'type':'warning','message':'synthetic warning'}]
    assert readback.verify(**args)['created_and_active']
    assert args['save']['messages'][0]['type']=='warning'


@pytest.mark.parametrize('field',['telephone','adresse'])
def test_unmapped_optional_data_cannot_be_silently_ignored(field):
    args=fixture_data();args['payload']['fields'].append({'group':'BPAS_1','name':field,'value':'synthetic'})
    result=readback.verify(**args)
    assert not result['confirmed'] and any('mapping_unverified' in e for e in result['errors'])


def test_optional_fiscal_fields_absent_are_not_invented():
    args=fixture_data();args['payload']['fields']=[f for f in args['payload']['fields'] if f['name'] not in ('XICE','XIF','XRC')]
    assert readback.verify(**args)['created_and_active']


def test_requested_activation_and_name_anomalies_are_distinct():
    text='Bonjour, merci de créer un fournisseur : DROGUERIE PALMERAIE ICE : 001850814000094 IF : 20734927 RC : 10909 Activation : OUI Catégorie : FR Pays : MA Devise : MAD'
    delta,trace=fast.extract(text,{'articles':[]});state=chat.merge({'articles':[]},delta,text)
    p=state['partners'][0]
    assert p['statut']=='OUI' and p['nom']=='DROGUERIE PALMERAIE' and p['categorie_fournisseur']=='FR'
    row={'folder':'TEST','BPRNUM_0':'DROGUERIEPALME','BPSNUM_0':'DROGUERIEPALME','BPRNAM_0':'erreur','BPSNAM_0':'erreur','XICE_0':p['ice'],'supplier_active':1,'partner_active':2}
    p=prep.prepare(p,{'fiscal':{'ok':True,'rows':[row]}})
    assert p['preparation']['activation_requested']
    duplicate=p['preparation']['duplicates'][0]
    assert duplicate['supplier_active']==1 and duplicate['partner_active']==2
    assert 'supplier_inactive' in duplicate['issues'] and 'supplier_name_differs_from_request' in duplicate['issues']
    assert p['preparation']['short_name_proposal']['value']=='DROGUERIE'
    assert not p['preparation']['short_name_proposal']['confirmed']


def test_real_description_builds_name_as_list_and_explicit_activation():
    desc=parse_xml((Path(__file__).resolve().parents[2]/'runtime/crud-WS_FOURNIS-description.xml').read_bytes())
    partner={'code':'F0012','nom':'SYNTH SUPPLIER','intitule_court':'SYNTH','categorie_fournisseur':'FR','pays':'MA','devise':'MAD','statut':'actif','ice':'001850814000094'}
    result=proposal(partner,desc)
    xml=parse_xml(result['xml'].encode())
    assert xml.find('./GRP[@ID="BPRS_1"]/LST[@NAME="BPRNAM"]/ITM').text=='SYNTH SUPPLIER'
    assert xml.find('./GRP[@ID="BPS0_1"]/FLD[@NAME="ENAFLG"]').text=='2'
    assert not result['save_sent'] and not result['creation_ready']
    partner['dossier_cible']='OB'
    with pytest.raises(ValueError,match='OB_read_only'):proposal(partner,desc)


def test_supplier_qwen_schema_is_narrow_and_requires_declared_fiscal_fields():
    from app.services.chat_model import supplier_request_schema
    schema=supplier_request_schema('Créer un fournisseur SYNTH ICE 001850814000094 IF 20734927 RC 10909')
    item=schema['properties']['fournisseurs']['items']
    assert set(item['required'])=={'nom','ice','identifiant_fiscal','rc'}
    assert item['additionalProperties'] is False and 'articles' not in schema['properties']
    assert supplier_request_schema('Créer un fournisseur et un article') is None
    assert supplier_request_schema('Créer un fournisseur SYNTH adresse : test') is None


@pytest.mark.parametrize('field,column',[('ice','XICE_0'),('identifiant_fiscal','XIF_0'),('rc','XRC_0'),('nom','BPRNAM_0')])
def test_each_duplicate_key_blocks_numeric_code_proposal(field,column):
    values={'ice':'001850814000094','identifiant_fiscal':'20734927','rc':'10909','nom':'SYNTH SUPPLIER'}
    partner={'nom':'SYNTH SUPPLIER',field:values[field]}
    row={'folder':'TEST','BPRNUM_0':'F0012','BPSNUM_0':'F0012',column:values[field]}
    result=prep.prepare(partner,{'fiscal':{'ok':True,'rows':[row]}})
    assert result['preparation']['duplicates'] and not result['preparation']['code_proposal']
    assert not result['preparation']['creation_ready']


def test_sql_connection_failure_cannot_mark_creation_confirmed(monkeypatch):
    def unavailable(*args):raise RuntimeError('synthetic_sql_offline')
    monkeypatch.setattr(readback.chat_tools,'run',unavailable)
    args=fixture_data();args.pop('sql')
    result=readback.verify(**args)
    assert not result['confirmed'] and not result['retry_allowed']


def test_error_placeholder_name_is_not_a_valid_preparation():
    result=prep.prepare({'nom':'erreur'},{'fiscal':{'ok':True,'rows':[]}})
    assert 'supplier_name_placeholder_not_allowed' in result['preparation']['errors']
