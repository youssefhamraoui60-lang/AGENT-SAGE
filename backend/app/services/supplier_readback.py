"""Supplier verification after an already authorized write; never sends SAVE."""
from app.services import chat_tools

# SOAP inputs inspected in the local TEST WS_FOURNIS description.
MAPPING={
    'BPRS_1.BPRNAM':('BPRNAM_0','BPSNAM_0'),
    'BPRS_1.BPRSHO':('BPRSHO_0','BPSSHO_0'),
    'BPRS_1.XICE':('XICE_0',),'BPRS_1.XIF':('XIF_0',),'BPRS_1.XRC':('XRC_0',),
    'BPRS_1.CRY':('CRY_0',),'BPRS_1.CUR':('CUR_0',),
    'BPS0_1.BSGCOD':('BSGCOD_0',),'BPS0_1.ENAFLG':('supplier_active','partner_active'),
    'BPS2_1.ACCCOD':('ACCCOD_0',),'BPS2_2.PTE':('PTE_0',),'BPS2_3.VACBPR':('VACBPR_0',)}
REQUIRED={'BPRS_1.BPRNAM','BPRS_1.CRY','BPRS_1.CUR','BPS0_1.BSGCOD','BPS0_1.ENAFLG'}


def text(value):
    return str(value).strip() if value is not None else None


def verify(keys,payload,soap,save,sql=None):
    """Compare exact identity, requested fields, SOAP and fresh TEST SQL.

    Numeric coercion is deliberately forbidden for fiscal identifiers and codes.
    Additional unmapped fields (e.g. addresses) keep verification incomplete.
    """
    code=keys.get('BPSNUM');errors=[];comparisons={}
    if sql is None:
        try:sql=chat_tools.run([{'id':'supplier_readback','tool':'get_supplier_record','args':{'Folder':'TEST','Supplier':code or ''}}]).get('supplier_readback',{})
        except Exception:sql={}
    rows=sql.get('rows',[])
    valid_sql=sql.get('ok') is True and sql.get('source')=='SQL TEST' and sql.get('folder')=='TEST' and len(rows)==1 and rows[0].get('folder')=='TEST'
    row=rows[0] if valid_sql else {}
    if not valid_sql:errors.append('sql_readback_unavailable_or_wrong_scope')
    if soap.get('exists') is not True:errors.append('soap_readback_missing')
    fields=soap.get('fields',{})
    comparisons['soap_code']=isinstance(code,str) and text(fields.get('BPS0_1.BPSNUM'))==code
    comparisons['sql_supplier_code']=isinstance(code,str) and text(row.get('BPSNUM_0'))==code
    comparisons['sql_partner_code']=isinstance(code,str) and text(row.get('BPRNUM_0'))==code
    expected={}
    for field in payload.get('fields',[]):
        path=field['group']+'.'+field['name']
        value=field['value'];expected[path]=value
        actual=fields.get(path)
        comparisons['soap:'+path]=([text(x) for x in actual]==[text(x) for x in value] if isinstance(value,list) and isinstance(actual,list) else text(actual)==text(value) if not isinstance(value,list) else False)
        columns=MAPPING.get(path)
        if not columns or field.get('row') is not None:
            errors.append('sql_mapping_unverified:'+path);continue
        scalar=value[0] if isinstance(value,list) and value else value
        for column in columns:comparisons['sql:'+column]=text(row.get(column))==text(scalar)
    for missing in sorted(REQUIRED-set(expected)):errors.append('expected_field_missing:'+missing)
    name=expected.get('BPRS_1.BPRNAM')
    if not isinstance(name,list) or len(name)!=2 or not name[0].strip() or name[0].strip().casefold()=='erreur':errors.append('invalid_expected_supplier_name')
    if isinstance(name,list) and len(name)>1 and name[1].strip():errors.append('second_name_line_sql_mapping_unverified')
    active=text(row.get('supplier_active'))=='2' and text(row.get('partner_active'))=='2' and text(fields.get('BPS0_1.ENAFLG'))=='2'
    saved=save.get('status')==1 and not save.get('code') and not save.get('error_type')
    if not saved:errors.append('save_not_confirmed')
    conforms=not errors and bool(comparisons) and all(comparisons.values())
    requested_active=text(expected.get('BPS0_1.ENAFLG'))=='2'
    return {'confirmed':saved and conforms,'created_and_active':saved and conforms and requested_active and active,
        'folder':'TEST','code':text(row.get('BPSNUM_0')) if valid_sql else code,'active':active,
        'comparisons':comparisons,'errors':errors,'sql_readback':sql,'retry_allowed':False,
        'record':{k:row.get(k) for k in ('BPSNUM_0','BPSNAM_0','BSGCOD_0','XICE_0','XIF_0','XRC_0','CRY_0','CUR_0','supplier_active','partner_active')}}


def message(result):
    row=result.get('record',{})
    if result.get('created_and_active'):
        return ('Fournisseur créé et activé avec succès dans TEST.\n\n'+str(row.get('BPSNUM_0'))+' — '+str(row.get('BPSNAM_0'))+
            '\n\nCatégorie : '+str(row.get('BSGCOD_0'))+'\nICE : '+str(row.get('XICE_0') or '')+
            '\nIF : '+str(row.get('XIF_0') or '')+'\nRC : '+str(row.get('XRC_0') or '')+
            '\nPays : '+str(row.get('CRY_0'))+'\nDevise : '+str(row.get('CUR_0'))+
            '\nStatut : Actif\nLa fiche a été vérifiée par SOAP read et SQL. Consultation : TEST → GESBPS.')
    if result.get('sql_readback',{}).get('ok') and row.get('BPSNUM_0'):
        return 'Fiche fournisseur retrouvée, mais conformité complète non confirmée'+(' ; fournisseur inactif.' if not result.get('active') else '.')+' Consultez les différences. Ne relancez pas SAVE automatiquement.'
    return 'Résultat fournisseur non confirmé. Relecture SOAP et SQL nécessaire avant toute décision ; aucun nouvel envoi automatique.'
