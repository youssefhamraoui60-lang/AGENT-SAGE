"""Build a reviewable WS_FOURNIS proposal, without approval or SOAP execution."""
import re
from app.schemas.sage_crud import Preparation
from app.services.sage_gateway import build_xml,RESOURCES
from app.services.sage_soap import SageError
from app.services.chat_turns import norm


def proposal(partner,description):
    if partner.get('dossier_cible','TEST')!='TEST':raise ValueError('OB_read_only_no_creation')
    if any(description.get(k)!=v for k,v in {'FOL':'TEST','SOL':'V12','PNA':'WS_FOURNIS','OBJ':'BPS'}.items()):raise ValueError('supplier_description_scope_mismatch')
    if not re.fullmatch(r'F[0-9]{1,14}',partner.get('code') or ''):raise ValueError('confirmed_numeric_supplier_code_required')
    name=partner.get('nom','').strip()
    if not name or norm(name)=='erreur':raise ValueError('valid_supplier_name_required')
    required=['categorie_fournisseur','pays','devise','intitule_court','statut']
    if any(not partner.get(k) for k in required):raise ValueError('supplier_required_fields_not_confirmed')
    state=norm(partner['statut'])
    if state not in ('oui','actif','active','2','non','inactif','inactive','1'):raise ValueError('supplier_activation_value_unknown')
    fields=[{'group':'BPRS_1','name':'BPRNAM','value':[name,'']},
            {'group':'BPS0_1','name':'ENAFLG','value':'2' if state in ('oui','actif','active','2') else '1'}]
    for key,group,field in [('intitule_court','BPRS_1','BPRSHO'),('categorie_fournisseur','BPS0_1','BSGCOD'),('pays','BPRS_1','CRY'),('devise','BPRS_1','CUR'),('ice','BPRS_1','XICE'),('identifiant_fiscal','BPRS_1','XIF'),('rc','BPRS_1','XRC'),('conditions_paiement','BPS2_2','PTE'),('regime_taxe','BPS2_3','VACBPR'),('code_comptable','BPS2_1','ACCCOD')]:
        if partner.get(key):fields.append({'group':group,'name':field,'value':partner[key]})
    # Never silently omit data that has not yet been mapped and read-back tested.
    if any(partner.get(k) for k in ('adresse','telephone','email')):raise ValueError('supplier_address_contact_mapping_review_required')
    request=Preparation(action='create',keys={'BPSNUM':partner['code']},fields=fields)
    xml=build_xml(description,RESOURCES['suppliers'],request)
    return {'request':request.model_dump(),'xml':xml,'folder':'TEST','save_sent':False,'creation_ready':False,
            'blockers':['numbering_assignment_review','conditional_required_fields_review','exact_human_approval','existing_security_checks']}
