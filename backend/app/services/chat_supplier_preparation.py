"""Supplier extraction and read-only business preparation, never a write mapping."""
import re
from app.services.chat_turns import norm


def literal_extract(text,state):
    from app.services.chat_model import Delta
    n=norm(text)
    if '?' in n or re.search(r'\barticles?\b',n):return None
    header=re.search(r'\b(?:creer?|creation\s+de)\s+(?:(?:un|une|ce|le|la|les)\s+)?(?:nouveau\s+|nouvelle\s+)?fournisseur\b\s*[:=]?\s*',n)
    if not header:return None
    body=text[header.end():];lower=norm(body)
    scope=re.search(r'\bdossier\b(?:\s+cible)?\s*[:=]?\s*([a-z0-9_-]+)\b|\bdans\s+(ob|test|prod|production)\b',n)
    scope_value=(scope[1] or scope[2]).upper() if scope else None
    if scope_value and scope_value not in ('TEST','OB'):raise ValueError('supplier_folder_read_not_allowed')
    marker=r'\b(nom|raison\s+sociale|ice|if|rc|activation|actif|statut|categorie|pays|devise|intitule\s+court)\s*[:=]\s*|\b(ice|if|rc)\s+(?=\d)|\b(dossier(?:\s+cible)?)\s*(?:[:=]\s*)?(?=(?:ob|test)\b)'
    labels=list(re.finditer(marker,lower))
    if not labels or not any((m[1] or m[2]) in ('ice','if','rc') for m in labels):return None
    fields={'dossier_cible':scope_value} if scope else {}
    name=body[:labels[0].start()].strip(' ,;\n\r:')
    if name:fields['nom']=name
    for i,match in enumerate(labels):
        key={'nom':'nom','raison sociale':'nom','ice':'ice','if':'identifiant_fiscal','rc':'rc','dossier':'dossier_cible','dossier cible':'dossier_cible','activation':'statut','actif':'statut','statut':'statut','categorie':'categorie_fournisseur','pays':'pays','devise':'devise','intitule court':'intitule_court'}[match[1] or match[2] or match[3]]
        end=labels[i+1].start() if i+1<len(labels) else len(body)
        value=body[match.end():end].strip(' ,;\n\r.')
        if key=='dossier_cible':value=value.upper()
        if not value or (key in fields and fields[key]!=value):return None
        fields[key]=value
    if not fields.get('nom'):return None
    # This grammar only consumes explicitly labelled fiscal/name facts. Other
    # clauses remain with the existing parser/model instead of being discarded.
    if any(re.search(r'\b(?:adresse|pays|devise|capital|juridique|dossier|categorie)\b',norm(v)) for v in fields.values()):return None
    return Delta(intent='new',fournisseurs=[fields])


def prepare(partner,refs):
    target=partner.get('dossier_cible') or 'TEST'
    fiscal=refs.get('fiscal',{'ok':False,'rows':[]})
    profile=refs.get('profile',{'ok':False,'rows':[]})
    matches=[]
    for row in fiscal.get('rows',[]):
        reasons=[]
        for field,column in [('ice','XICE_0'),('identifiant_fiscal','XIF_0'),('rc','XRC_0')]:
            if partner.get(field) and str(row.get(column) or '').strip()==partner[field]:reasons.append(field)
        if norm((row.get('BPRNAM_0') or '').strip())==norm(partner.get('nom','')) or norm((row.get('BPSNAM_0') or '').strip())==norm(partner.get('nom','')):reasons.append('nom')
        issues=[]
        if row.get('BPSNUM_0') and norm(str(row.get('BPSNAM_0') or '').strip())!=norm(partner.get('nom','').strip()):issues.append('supplier_name_differs_from_request')
        if norm(str(row.get('BPRNAM_0') or '').strip())!=norm(partner.get('nom','').strip()):issues.append('partner_name_differs_from_request')
        if row.get('BPSNUM_0') and row.get('supplier_active')==1:issues.append('supplier_inactive')
        if row.get('partner_active')==1:issues.append('partner_inactive')
        if reasons:matches.append({'code':row['BPRNUM_0'],'name':row.get('BPRNAM_0'),'supplier_name':row.get('BPSNAM_0'),
            'supplier_exists':bool(row.get('BPSNUM_0')),'matched_fields':reasons,'folder':row.get('folder',target),
            'supplier_active':row.get('supplier_active'),'partner_active':row.get('partner_active'),'issues':issues})
    errors=[]
    if norm(partner.get('nom','').strip())=='erreur':errors.append('supplier_name_placeholder_not_allowed')
    if any(row.get('folder',target)!=target for row in fiscal.get('rows',[])):errors.append('fiscal_result_folder_mismatch')
    if not fiscal.get('ok'):errors.append('fiscal_duplicate_checks_unavailable')
    if any(set(m['matched_fields'])&{'ice','identifiant_fiscal'} and m['supplier_exists'] for m in matches):errors.append('supplier_fiscal_duplicate')
    if any(set(m['matched_fields'])&{'ice','identifiant_fiscal'} and not m['supplier_exists'] for m in matches):errors.append('existing_business_partner_requires_review')
    if any(m['matched_fields']==['rc'] for m in matches):errors.append('registration_match_requires_review')
    if any('nom' in m['matched_fields'] for m in matches):errors.append('existing_partner_name_requires_review')
    syntax={}
    for field,limit in [('ice',15),('identifiant_fiscal',30),('rc',30)]:
        value=partner.get(field)
        syntax[field]={'supplied':bool(value),'format_valid':bool(value and re.fullmatch(r'[0-9]+',value) and len(value)<=limit and (field!='ice' or len(value)==15)),
                       'authority_verified':False}
        if value and not syntax[field]['format_valid']:errors.append('invalid_fiscal_format:'+field)
    row=profile.get('rows',[{}])[0] if profile.get('rows') else {}
    if row and row.get('folder')!=target:
        row={};errors.append('target_profile_folder_mismatch')
    suggestions={}
    for field,column in [('categorie_fournisseur','BSGCOD_0'),('pays','CRY_0'),('devise','CUR_0'),('conditions_paiement','PTE_0'),('regime_taxe','VACBPR_0'),('code_comptable','ACCCOD_0')]:
        value=str(row.get(column) or '').strip()
        check={'pays':'country_verified','devise':'currency_verified','conditions_paiement':'payment_verified','regime_taxe':'tax_regime_verified','code_comptable':'accounting_verified'}.get(field)
        if value and not partner.get(field) and (not check or row.get(check)):
            suggestions[field]={'value':value,'source':target+'.BPSCATEG','confirmed':False,'business_applicability_verified':False}
    candidate=None
    if target=='TEST' and not matches and not errors and fiscal.get('ok') and row.get('candidate_available')==1 and re.fullmatch(r'F[0-9]{1,14}',str(row.get('candidate_code') or '')):
        candidate={'code':row['candidate_code'],'status':'observed_manual_convention_requires_confirmation','folder':'TEST',
            'available_at_check':True,'reserved':False,'official_next_number':False,'strict_convention_confirmed':False,'requires_fresh_check_before_write':True}
    if target=='OB':errors.append('OB_read_only_no_creation')
    if target=='TEST':errors=[e for e in errors if e not in ('supplier_fiscal_duplicate','existing_business_partner_requires_review','registration_match_requires_review','existing_partner_name_requires_review')]
    if not row:errors.append('target_supplier_rules_unavailable')
    # Unknown mandatory conditions of the published transaction still block SAVE.
    partner['preparation']={'target_folder':target,'reference_folder':'OB','reference_is_write_template':False,
        'fiscal_mapping':{'ice':target+'.BPARTNER.XICE_0','identifiant_fiscal':target+'.BPARTNER.XIF_0','rc':target+'.BPARTNER.XRC_0'},
        'fiscal_checks':syntax,'duplicates':matches,'duplicate_check_complete':bool(fiscal.get('ok') and 'fiscal_result_folder_mismatch' not in errors),'checks_complete':bool(fiscal.get('ok') and row),
        'record_preview':{'BPSUPPLIER':{'BPSNAM_0':partner.get('nom'),'BPSNUM_0':partner.get('code')},
            'BPARTNER':{'BPRNAM_0':partner.get('nom'),'BPRNUM_0':partner.get('code'),'XICE_0':partner.get('ice'),'XIF_0':partner.get('identifiant_fiscal'),'XRC_0':partner.get('rc')}},
        'suggested_defaults':suggestions,'code_proposal':candidate,'errors':errors,
        'activation_requested':norm(partner.get('statut') or '') in ('oui','actif','active','2'),
        'short_name_proposal':{'value':partner.get('intitule_court') or (partner.get('nom') or '')[:10].strip(),'confirmed':bool(partner.get('intitule_court')),'source':'user_declared' if partner.get('intitule_court') else 'name_truncation_proposal'},
        'required_before_creation':['target_category_confirmation','required_addresses_and_published_fields_validation','exact_human_approval','verified_write_mapping'],
        'server_managed':['CREUSR_0','CREDATTIM_0','UPDUSR_0','UPDDATTIM_0','AUUID_0','ROWID'],
        'creation_ready':False,'sage_writes':0}
    partner['preparation']['transport']='direct_sql'
    partner['preparation']['required_before_creation']=['nom','intitule_court','ice','identifiant_fiscal','rc',
        'adresse','ville','telephone','conditions_paiement','categorie_fournisseur','code_comptable',
        'regime_taxe','devise','pays','date_regularite','type_montant']
    partner['preparation']['missing_sql_fields']=[key for key in partner['preparation']['required_before_creation'] if not partner.get(key)]
    return partner
