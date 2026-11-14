"""Fixed user-supplied supplier SQL; only the typed supplier parameters vary."""
import hashlib,json,os,re,subprocess
from time import monotonic
from datetime import date
from pathlib import Path
from uuid import uuid4
from app.core.config import settings
from app.services import sage_crud as crud

ROOT=Path(__file__).resolve().parents[3]
SQL=ROOT/'TEST/create_supplier.sql'
MAPPING={'Nom':'nom','NomCourt':'intitule_court','ICE':'ice','IF':'identifiant_fiscal','RC':'rc',
 'DateRegularite':'date_regularite','Adresse':'adresse','Ville':'ville','Telephone':'telephone',
 'Paiement':'conditions_paiement','Categorie':'categorie_fournisseur','CodeComptable':'code_comptable',
 'RegimeTaxe':'regime_taxe','Devise':'devise','TypeLibelle':'type_montant','Pays':'pays'}
LIMITS={'Nom':100,'NomCourt':30,'ICE':15,'IF':30,'RC':30,'Adresse':100,'Ville':50,
 'Telephone':30,'Fax':30,'Paiement':10,'Categorie':10,'CodeComptable':10,'RegimeTaxe':10,'Devise':10,'Pays':3}
READBACK={'Nom':'RAISON_SOCIALE','NomCourt':'NOM_COURT','ICE':'ICE','IF':'IF_FISCAL','RC':'RC',
 'Adresse':'ADRESSE','Ville':'VILLE','Telephone':'TELEPHONE','Fax':'FAX','Paiement':'CONDITION_PAIEMENT',
 'Categorie':'CATEGORIE','CodeComptable':'CODE_COMPTABLE','RegimeTaxe':'REGIME_TAXE','Devise':'DEVISE',
 'TypeMontant':'TYPE_MONTANT','Pays':'PAYS','DateRegularite':'DATE_REGULARITE'}

_PERMISSION_CACHE={}

def split_address(value):
    """Three verified TEST nvarchar(50) lines; never truncate address content."""
    text=re.sub(r'\s+',' ',value).strip()
    units=lambda v:len(v.encode('utf-16-le'))//2
    if units(text)>150:raise crud.CrudError('Adresse trop longue : les trois lignes Sage acceptent 150 caractères au total (50 par ligne). Précisez une adresse plus courte ; vos données sont conservées.',423)
    lines=[];remaining=text
    for slot in range(3):
        if not remaining:break
        cut=0
        for ch in remaining:
            if units(remaining[:cut+1])>50:break
            cut+=1
        if cut<len(remaining):
            # Prefer a word boundary, provided the rest still fits the remaining
            # lines. Keeping the separator preserves the complete normalized text.
            choices=[i+1 for i,ch in enumerate(remaining[:cut]) if ch==' ' and units(remaining[i+1:])<=(2-slot)*50]
            if choices:cut=choices[-1]
        lines.append(remaining[:cut]);remaining=remaining[cut:]
    if remaining:raise crud.CrudError('Adresse trop longue pour les trois lignes Sage. Aucune donnée supprimée.',423)
    return (lines+['']*3)[:3]

def configured():return bool(settings.sage_supplier_sql_connection_string.get_secret_value()) and SQL.is_file()

def target(folder):
    if folder not in ("TEST","OB"):raise crud.CrudError("invalid_supplier_folder",403)
    return folder

def connection_env(folder="TEST"):
    target(folder)
    env=os.environ.copy();env['SAGE_SUPPLIER_TARGET_FOLDER']=folder
    env['SAGE_SUPPLIER_OB_TRUST_SERVER_CERTIFICATE']='true' if settings.sage_supplier_ob_trust_server_certificate else 'false'
    env['SAGE_SUPPLIER_SQL_CONNECTION_STRING']=settings.sage_supplier_sql_connection_string.get_secret_value()
    env['SAGE_SUPPLIER_SQL_CREDENTIAL_FILE']=settings.sage_supplier_sql_credential_file
    return env

def security(force=False,folder="TEST"):
    target(folder)
    base={'ready':False,'folder':folder,'transport':'direct_sql','trust_server_certificate':folder=='TEST' or settings.sage_supplier_ob_trust_server_certificate}
    if settings.sage_mcp_enabled:return {**base,'blockers':['Pilote MCP en lecture seule : créations désactivées, brouillons conservés.']}
    if not configured():return {**base,'blockers':['Connexion SQL fournisseur TEST à configurer.']}
    env=connection_env(folder)
    key=hashlib.sha256((env['SAGE_SUPPLIER_SQL_CONNECTION_STRING']+'|'+env['SAGE_SUPPLIER_SQL_CREDENTIAL_FILE']+'|'+folder+'|'+env['SAGE_SUPPLIER_OB_TRUST_SERVER_CERTIFICATE']).encode()).hexdigest()
    cached=_PERMISSION_CACHE.get(key)
    if not force and cached and monotonic()-cached[0]<30:return cached[1]
    try:
        proc=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'TEST/Check-SupplierSql.ps1')],
            capture_output=True,text=True,encoding='utf-8-sig',timeout=20,env=env,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        body=json.loads(proc.stdout)
        if not isinstance(body,dict):raise ValueError()
        rows=body.get('permissions') or []
        missing=[r['object'] for r in rows if r.get('requires_insert')==1 and r.get('can_insert')!=1]
        missing_select=[r['object'] for r in rows if r.get('requires_select')==1 and r.get('can_select')!=1]
        missing_execute=[r['object'] for r in rows if r.get('requires_execute')==1 and r.get('can_execute')!=1]
        ready=body.get('ok') is True and body.get('ready') is True and body.get('folder')==folder and len(rows)==19 and not (missing or missing_select or missing_execute)
        blockers=(['Autorisation INSERT manquante : '+', '.join(missing)] if missing else [])
        if missing_select:blockers.append('Autorisation SELECT manquante : '+', '.join(missing_select))
        if missing_execute:blockers.append('Autorisation EXECUTE manquante : '+', '.join(missing_execute))
        if not ready and not blockers:blockers=['Le certificat SQL Server ne peut pas être validé pour Production OB.' if body.get('code')=='sql_tls_validation_failed' else 'Connexion ou droits SQL fournisseur '+folder+' indisponibles.']
        answer={**base,'ready':ready,'blockers':blockers,'permissions':rows}
    except (OSError,ValueError,TypeError,KeyError,subprocess.TimeoutExpired):
        answer={**base,'blockers':['Vérification des droits SQL fournisseur TEST indisponible.']}
    _PERMISSION_CACHE.clear();_PERMISSION_CACHE[key]=(monotonic(),answer)
    return answer

def load_defaults(folder="TEST"):
    try:
        proc=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'TEST/Read-SupplierDefaults.ps1')],
            capture_output=True,text=True,encoding='utf-8-sig',timeout=20,env=connection_env(folder),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        body=json.loads(proc.stdout)
        if body.get('ok') is not True or len(body.get('rows',[]))!=1:raise ValueError()
        return {k:str(v).strip() if v is not None else '' for k,v in body['rows'][0].items()}
    except (OSError,ValueError,subprocess.TimeoutExpired):raise crud.CrudError('Paramètres du modèle OB.F103 indisponibles. Données conservées.',423) from None

def load_reference_labels(folder="TEST"):
    try:
        p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'TEST/Read-SupplierReferenceLabels.ps1')],capture_output=True,text=True,encoding='utf-8-sig',timeout=20,env=connection_env(folder),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        body=json.loads(p.stdout)
        if body.get('ok') is not True:raise ValueError()
        return body['rows']
    except (OSError,ValueError,subprocess.TimeoutExpired):raise crud.CrudError('Références de pays et de paiement indisponibles. Vos choix sont conservés.',423) from None

def needs_reference_labels(partner):
    return len(partner.get('pays') or '')>3 or len(partner.get('conditions_paiement') or '')>10

def reference_norm(value):
    from app.services.chat_turns import norm
    value=re.sub(r'\b(?:jour|nhar|nharat|jrs?|jr)\b','jours',norm(value))
    value=re.sub(r'\b(?:apres|ba3d|b3d)\s+(?=\d+)','',value)
    value=re.sub(r'\b(virement|cheque|effet)\s+a\s+(?=\d+\s+jours\b)',r'\1 ',norm(value)).strip()
    return re.sub(r'\b(virement|cheque|effet)\s+au\s+comptant\b',r'\1 comptant',value)

def parameters(partner,defaults=None):
    target(partner.get('dossier_cible','TEST'))
    from app.services.conversation_guardrails import invalid_supplier_name
    if invalid_supplier_name(partner.get('nom')):
        raise crud.CrudError('Ce texte ressemble à un message de l’assistant, pas à un nom de fournisseur. Indiquez la raison sociale exacte avant de confirmer.',423)
    if partner.get('ice') and (not isinstance(partner['ice'],str) or not re.fullmatch(r'[0-9]{15}',partner['ice'])):
        raise crud.CrudError('ICE invalide : 15 chiffres requis.',423)
    missing=[field for field in ('nom',) if not partner.get(field)]
    if missing:raise crud.CrudError('Champs fournisseur manquants : '+', '.join(missing),423)
    # Legal form is retained as draft metadata, never mapped to an invented SQL
    # column. Approval must explicitly acknowledge this limited write scope.
    unsupported=[k for k in ('email','nom_commercial','capital','annee_creation','ville_rc','societe','site') if partner.get(k)]
    if unsupported:raise crud.CrudError('Champs absents de la requête fournie : '+', '.join(unsupported),423)
    result={key:partner.get(field) for key,field in MAPPING.items()}
    result['NomCourt']=partner.get('intitule_court') or partner['nom'][:10].upper()
    result['ICE']=partner.get('ice') or ''
    result['IF']=partner.get('identifiant_fiscal') or ''
    result['RC']=partner.get('rc') or ''
    fallback=defaults
    if any(result[k] is None for k in MAPPING if k not in ('Nom','ICE')):
        fallback=fallback if fallback is not None else load_defaults(partner.get('dossier_cible','TEST'))
    for key in result:
        if result[key] is None:result[key]=(fallback or {}).get(key,'')
    if partner.get('dossier_cible','TEST') in ('TEST','OB'):
        result['Adresse'],result['Adresse2'],result['Adresse3']=split_address(result['Adresse'])
    result.update(Fax=partner.get('fax') or (fallback or {}).get('Fax',''),CodeModele='F103',Statut='')
    if needs_reference_labels(partner):
        from app.services.chat_turns import norm
        labels=(defaults or {}).get('__reference_labels')
        if labels is None:labels=load_reference_labels(partner.get('dossier_cible','TEST'))
        for key in ('Pays','Paiement'):
            if len(result[key])<=LIMITS[key]:continue
            matches={r['code'] for r in labels if r['kind']==key and reference_norm(r['label'])==reference_norm(result[key])}
            if len(matches)!=1:raise crud.CrudError('Référence '+key+' introuvable ou ambiguë : '+result[key]+'. Précisez le code Sage.',423)
            result[key]=matches.pop()
    if partner.get('statut'):
        from app.services.chat_turns import norm
        status=norm(str(partner['statut'])).strip()
        if status not in ('oui','actif','active','2','non','inactif','inactive','desactive','desactivee','1'):
            raise crud.CrudError('Statut fournisseur invalide.',423)
        result['Statut']='2' if status in ('oui','actif','active','2') else '1'
    if result['ICE'] and not re.fullmatch(r'[0-9]{15}',result['ICE']):raise crud.CrudError('ICE invalide : 15 chiffres requis.',423)
    if result['TypeLibelle'] not in ('HT','TTC'):raise crud.CrudError('Type montant HT/TTC requis.',423)
    # The numeric menu value is checked against the Sage dictionary by SQL.
    result['TypeMontant']=partner.get('type_montant_valeur') or (int((fallback or {})['TypeMontant']) if not partner.get('type_montant') and (fallback or {}).get('TypeMontant') else (2 if result['TypeLibelle']=='TTC' else 1))
    try:date.fromisoformat(result['DateRegularite'])
    except ValueError:raise crud.CrudError('Date de régularité invalide.',423) from None
    for key,limit in LIMITS.items():
        if not isinstance(result[key],str) or len(result[key])>limit:raise crud.CrudError('Champ trop long : '+key,423)
    return result

def query_digest(folder='TEST'):
    target(folder)
    if folder=='TEST':return hashlib.sha256(SQL.read_bytes()).hexdigest()
    text=SQL.read_text(encoding='utf-8-sig')
    return hashlib.sha256((text if folder=='TEST' else text.replace('TEST','OB')).encode('utf-8')).hexdigest()

def run(values,execute=False,approved_duplicate_codes=None,folder="TEST"):
    target(folder)
    if not configured():raise crud.CrudError('Connexion SQL fournisseur TEST à configurer.',423)
    env=connection_env(folder)
    try:
        proc=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'TEST/sql_worker.ps1')],
            input=json.dumps({'folder':folder,'parameters':values,'execute':execute,
                'allow_duplicates':bool(approved_duplicate_codes),'approved_duplicate_codes':approved_duplicate_codes or []},ensure_ascii=False),
            capture_output=True,text=True,encoding='utf-8',timeout=75,env=env,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        body=json.loads(proc.stdout.lstrip('\ufeff'))
        if not isinstance(body,dict):raise ValueError()
    except (OSError,ValueError,subprocess.TimeoutExpired):
        if execute:return {'ok':False,'code':'sql_result_requires_readback','folder':folder}
        raise crud.CrudError('Connexion SQL indisponible ; aucune création exécutée.',423) from None
    if not body.get('ok') and not execute and body.get('code')!='sql_validation_rejected':
        raise crud.CrudError('Préparation SQL refusée : '+str(body.get('code'))+' (SQL '+str(body.get('sql_error_number'))+'). Aucune insertion.',423)
    return body

def prepare_operation(partner):
    folder=target(partner.get("dossier_cible","TEST"))
    if partner.get('ice') and (not isinstance(partner['ice'],str) or not re.fullmatch(r'[0-9]{15}',partner['ice'])):
        raise crud.CrudError('ICE invalide : 15 chiffres requis.',423)
    defaults=(load_defaults(folder) if folder=="OB" else load_defaults()) if any(not partner.get(field) for key,field in MAPPING.items() if key not in ('Nom','ICE','IF','RC','NomCourt')) else {}
    if needs_reference_labels(partner):
        from app.services.chat_turns import norm
        requested={'Pays':partner.get('pays') or '', 'Paiement':partner.get('conditions_paiement') or ''}
        defaults['__reference_labels']=[r for r in load_reference_labels(folder) if reference_norm(r['label'])==reference_norm(requested.get(r['kind'],''))]
    values=parameters(partner,defaults);body=run(values,folder=folder) if folder=="OB" else run(values)
    if folder=='OB' and body.get('folder')!='OB':raise crud.CrudError('supplier_target_mismatch',403)
    rejected=body.get('ok') is False or bool(body.get('duplicate_warnings'))
    rows=body.get('rows') or []
    if not rejected and (len(rows)!=1 or rows[0].get('RESULTAT')!='VALIDATED_NO_INSERT'):raise crud.CrudError('supplier_sql_preview_invalid',409)
    sha=query_digest(folder);warnings=body.get('duplicate_warnings') or []
    digest=crud.digest({'parameters':values,'query':sha,'duplicates':warnings})
    op={'id':str(uuid4()),'resource':'suppliers','action':'create','transport':'direct_sql','folder':folder,
        'status':'blocked' if rejected else 'prepared','parameters':values,'model_defaults':defaults,
        'defaulted_fields':[key for key,field in MAPPING.items() if not partner.get(field)],
        'query_digest':sha,'digest':digest,'duplicate_warnings':warnings,'record_keys':{},
        'proposed_code':(body.get('diagnostics') or [{}])[0].get('proposed_code') if rejected else rows[0]['CODE_PROPOSE_NON_RESERVE']}
    op['reference_resolutions']=[{'field':key,'requested':partner[field],'code':values[key],'source':folder+'.ATEXTRA'}
        for key,field in [('Pays','pays'),('Paiement','conditions_paiement')]
        if partner.get(field) and partner[field]!=values[key]]
    if partner.get('forme_juridique'):
        op['draft_only_fields']=[{'field':'forme_juridique','label':'Forme juridique','value':partner['forme_juridique']}]
        op['digest']=operation_digest(op)
    if rejected:op['validation']={**body,'message':preparation_message(body)}
    return op

def operation_digest(op):
    content={'parameters':op.get('parameters'),'query':op.get('query_digest'),'duplicates':op.get('duplicate_warnings',[])}
    if op.get('draft_only_fields'):content['draft_only_fields']=op['draft_only_fields']
    return crud.digest(content)

def preparation_message(body):
    number=body.get('sql_error_number')
    if number==50105 and body.get('field_errors'):
        labels={'Nom':'Nom du fournisseur','NomCourt':'Nom court','Adresse':'Adresse','Ville':'Ville','Telephone':'Téléphone','Paiement':'Conditions de paiement'}
        errors=sorted({labels.get(r['field'],r['field'])+' : '+str(r['length'])+' caractères, maximum '+str(r['limit']) for r in body['field_errors']})
        return 'La fiche est comprise, mais certaines valeurs dépassent la taille autorisée dans Sage : '+ ' ; '.join(errors)+'. Corrigez-les dans le chat avant de confirmer. Vos informations sont conservées ; aucune fiche n’a été créée.'
    if number==50109 or body.get('duplicate_warnings'):
        rows=body.get('diagnostics') or body.get('duplicate_warnings') or []
        def cell(value):
            return str(value or 'Non renseigné').strip().replace('|','/').replace('\r',' ').replace('\n',' ')
        details=[]
        for row in rows:
            code=row.get('duplicate_code') or row.get('code')
            if not code:continue
            matched=', '.join(label for key,label in [('name_match','Nom'),('ice_match','ICE'),('fiscal_match','IF'),('rc_match','RC')] if row.get(key) in (1,True,'1')) or 'Informations communes'
            details.append('| '+' | '.join(cell(v) for v in [code,row.get('duplicate_name') or row.get('name'),row.get('existing_ice'),row.get('existing_if'),row.get('existing_rc'),matched])+' |')
        intro='Nous vous informons qu’une fiche correspondante existe déjà dans TEST. Ces informations sont déjà utilisées ; aucune nouvelle fiche n’a été créée.'
        if details:
            intro+='\n\n| Code existant | Nom du fournisseur | ICE | IF | RC | Correspondances |\n| --- | --- | --- | --- | --- | --- |\n'+'\n'.join(dict.fromkeys(details))
        return intro.replace('dans TEST','dans '+body.get('folder','TEST'))+'\n\nLa création est bloquée pour éviter un doublon. Vérifiez la fiche existante ou corrigez les informations de votre demande.'
    return 'La fiche ne peut pas encore être créée. Certaines informations doivent être vérifiées ; vos données sont conservées.'

def verify(values,body,folder="TEST"):
    target(folder)
    rows=body.get('rows') or []
    if not body.get('ok') or body.get('folder')!=folder or body.get('executed') is not True or len(rows)!=1:return None
    row=rows[0];code=str(row.get('CODE_FOURNISSEUR') or '')
    if not re.fullmatch(r'F[0-9]+',code):return None
    comparisons={key:str(row.get(column,'')).strip()==str(values[key]).strip() for key,column in READBACK.items() if key!='DateRegularite'}
    if 'Adresse2' in values:
        comparisons.update({key:column in row and str(row[column]).strip()==str(values[key]).strip() for key,column in [('Adresse2','ADRESSE2'),('Adresse3','ADRESSE3')]})
    comparisons['DateRegularite']=str(row.get('DATE_REGULARITE',''))[:10]==values['DateRegularite']
    if values.get('Statut'):
        comparisons['Statut']=all(str(row.get(k))==values['Statut'] for k in ('partner_active','supplier_active'))
    if not all(comparisons.values()):return None
    record={**row,'BPSNUM_0':code,'BPSNAM_0':row['RAISON_SOCIALE'],'XICE_0':row['ICE'],'XIF_0':row['IF_FISCAL'],
            'XRC_0':row['RC'],'BSGCOD_0':row['CATEGORIE'],'CUR_0':row['DEVISE'],'CRY_0':row['PAYS']}
    return {'confirmed':True,'folder':folder,'code':code,'record':record,'comparisons':comparisons,
            'sql_readback':{'ok':True,'source':'SQL '+folder,'folder':folder,'rows':[row]},'errors':[]}
