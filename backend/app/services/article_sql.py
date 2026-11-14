"""Typed plans over the supplied clone logic. No model-supplied SQL or production."""
import json,subprocess,hashlib,re
from pathlib import Path
from uuid import uuid4
from app.services import supplier_sql,sage_crud as crud
from app.core.config import settings

ROOT=Path(__file__).resolve().parents[3]
FLAGS={'gestion_stock':'STOMGTCOD_0','achete':'PURFLG_0','vendu':'SALFLG_0','fabrique':'MFGFLG_0','livrable':'DLVFLG_0','sous_traite':'SCPFLG_0','receptionne':'RCPFLG_0'}
TERMINAL={'executing','succeeded','ambiguous','unverified','failed','cancelled'}
def fail(message):raise crud.CrudError(message,423)
def text(value):return str(value).strip() if value is not None else ''
def supplier_required(sites):return {text(site) for site in sites if text(site)}!={'202'}
INPUT_FIELDS=('code_article','designation','categorie','categorie_libelle','unite','unite_achat','unite_vente','code_comptable','compte_general','accounting_category','code_tva','niveau_taxe','taux_tva','site','requested_sites','fournisseurs','code_fournisseur','reference_fournisseur','fournisseur_nom','supplier_intent','fournisseur_principal','flag_fournisseur','allow_negative_stock','statut_article','familles_statistiques','type_article','modele_article','modele_site','modele_fournisseur','modele_traduction','dossier_cible',*FLAGS)
INPUT_FIELDS=(*INPUT_FIELDS,'coefficient_vente_declare','conversion_vente_declaree')
def fingerprint(article):return crud.digest({k:article.get(k) for k in INPUT_FIELDS})
def digest():return hashlib.sha256(b''.join(p.read_bytes() for p in (Path(__file__),ROOT/'backend/app/services/sage_sql_queue.py',ROOT/'TEST/article_transaction.sql',ROOT/'TEST/article_sql_worker.ps1',ROOT/'TEST/article_catalog.sql'))).hexdigest()
def _transport(action,plan=None,execute=False,category='',stock=0,code='',folder='TEST'):
    supplier_sql.target(folder)
    if plan is not None and plan.get('folder')!=folder:fail('Dossier du plan article incoherent.')
    if action not in ('catalog','plan') or type(execute) is not bool:fail('Opération article non autorisée.')
    if execute and (not settings.sage_article_sql_enabled or settings.sage_mcp_enabled):fail('Création article désactivée dans cet environnement ; brouillon conservé.')
    payload={'folder':folder,'action':action,'plan':plan,'execute':execute,'Category':category,'Stock':stock,'Code':code}
    try:
        p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'TEST/article_sql_worker.ps1')],input=json.dumps(payload,ensure_ascii=False),env=supplier_sql.connection_env(folder),capture_output=True,text=True,encoding='utf-8',timeout=55,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        result=json.loads(p.stdout.lstrip('\ufeff'))
        if not isinstance(result,dict):raise ValueError()
        return result
    except (OSError,ValueError,subprocess.TimeoutExpired):
        if execute:return {'ok':False,'folder':folder,'code':'result_requires_readback','retry_allowed':False}
        fail('Lecture Sage indisponible. Les informations du brouillon sont conservées.')

def transport(action,plan=None,execute=False,category='',stock=0,code='',folder='TEST'):
    from app.services.sage_sql_queue import plan_slot,SagePlanBusy,not_started
    params=dict(plan=plan,execute=execute,category=category,stock=stock,code=code,folder=folder)
    if action!='plan':return _transport(action,**params)
    try:
        with plan_slot(folder):return _transport(action,**params)
    except SagePlanBusy:return not_started(folder)

def catalog(category='',stock=0,code='',folder='TEST',require_insert=True):
    result=transport('catalog',category=category,stock=stock,code=code,folder=folder) if folder!='TEST' else transport('catalog',category=category,stock=stock,code=code)
    if result.get('folder','TEST')!=folder:fail('Lecture article hors dossier de la conversation.')
    if result.get('ok') is False:fail('Impossible de lire les modèles ou contraintes articles TEST. Aucune permission ne sera modifiée.')
    if any(r.get('can_select')!=1 or require_insert and r.get('can_insert')!=1 for r in result.get('permissions',[])):fail('Les droits nécessaires ne sont pas disponibles sur les tables de la fiche. Aucun droit ne sera modifié.')
    return result

def length(schema,table,column,value):
    col=next((r for r in schema['columns'] if r['table']==table and r['column']==column),None)
    if not col:fail('Champ Sage absent : '+table+'.'+column+'.')
    if isinstance(value,str) and col['type'] in ('nvarchar','nchar','varchar','char') and col['max_length']!=-1:
        try:size=len(value.encode('utf-16-le')) if col['type'].startswith('n') else len(value.encode('cp1252'))
        except UnicodeEncodeError:fail('Caractères non représentables dans '+table+'.'+column+'. Valeur conservée sans remplacement.')
        if size>col['max_length']:fail('Champ trop long : '+table+'.'+column+' ('+str(len(value))+' caractères). Valeur conservée ; aucune troncature.')
    return col

def node(schema,table,source,overrides,site='',supplier=''):
    for key,value in overrides.items():length(schema,table,key,value)
    return {'table':table,'model':text(source.get('ITMREF_0') or source.get('IDENT1_0') or source.get('TCLCOD_0')),'site':site,'supplier':supplier,'source_hash':source['source_hash'],'overrides':overrides}

def unit_values(schema,table,unit):
    available={c['column'] for c in schema['columns'] if c['table']==table}
    result={k:unit for k in ('STU_0','PUU_0','SAU_0','SSU_0','EEU_0') if k in available}
    result.update({k:1 for k in ('PUUSTUCOE_0','SAUSTUCOE_0','SSUSTUCOE_0','EEUSTUCOE_0') if k in available})
    return result

def choose(rows,stock=None,preferred=()):
    values=[r for r in rows if stock is None or int(r.get('fields',{}).get('STOMGTCOD_0',stock))==stock]
    for code in preferred:
        exact=[r for r in values if text(r.get('ITMREF_0') or r.get('IDENT1_0'))==code]
        if len(exact)==1:return exact[0]
    if len(values)==1:return values[0]
    fail('Modèle compatible absent ou ambigu. Précisez un modèle validé ; aucun modèle ne sera choisi sur la seule ressemblance de son nom.')

def chosen(rows,stock=None,model=None,preferred=(),unit=None):
    original=rows
    if unit:rows=[r for r in rows if not r.get('fields',{}).get('STU_0') or text(r['fields']['STU_0'])==unit]
    if not rows and unit and not model:
        # Creating a new record can instantiate a neutral, approved template
        # in the declared unit. This never migrates any existing article.
        from decimal import Decimal,InvalidOperation
        def neutral(row):
            f=row.get('fields',{});old=text(f.get('STU_0'))
            if not old:return False
            if any(text(f.get(k)) not in ('',old) for k in ('PUU_0','SAU_0','SSU_0','EEU_0')):return False
            if any(text(v) for k,v in f.items() if re.fullmatch(r'PCU_\d+',k)):return False
            try:
                if any(Decimal(str(f[k]))!=1 for k in ('PUUSTUCOE_0','SAUSTUCOE_0','SSUSTUCOE_0','EEUSTUCOE_0') if k in f):return False
                if any(Decimal(str(v or 0))!=0 for k,v in f.items() if re.fullmatch(r'PCUSTUCOE_\d+',k) or k in ('ITMWEI_0','ITMVOU_0')):return False
            except InvalidOperation:return False
            return not any(text(f.get(k)) for k in ('WEU_0','VOU_0'))
        rows=[r for r in original if text(r.get('ITMREF_0') or r.get('IDENT1_0')) in preferred and neutral(r)]
    if model:
        rows=[r for r in rows if text(r.get('ITMREF_0') or r.get('IDENT1_0'))==model]
        return choose(rows,stock)
    return choose(rows,stock,preferred)

def category_plan(draft,schema=None):
    folder=supplier_sql.target(draft.get('dossier_cible','TEST'))
    for field in ('code','designation','nom_court','modele'):
        if not draft.get(field):fail('Catégorie à compléter : '+field+'.')
    schema=schema or (catalog(draft['code'],folder=folder) if folder!='TEST' else catalog(draft['code']))
    if folder=='OB' and schema.get('folder')!='OB':fail('Modele de categorie hors dossier OB.')
    if any(text(r['TCLCOD_0'])==draft['code'] for r in schema['categories']):fail('Cette catégorie existe déjà. Consultez ses paramètres avant de créer une nouvelle fiche.')
    sources=[r for r in schema['categories'] if text(r['TCLCOD_0'])==draft['modele'] and not text(r['STOFCY_0'])]
    if len(sources)!=1:fail('Catégorie modèle absente ou non unique.')
    source=sources[0];ov={'TCLCOD_0':draft['code'],'STOFCY_0':'','TCLDES_0':draft['designation'],'TCLSHO_0':draft['nom_court']}
    for field,column in FLAGS.items():
        value=draft.get(field)
        if value is None:fail('Précisez le paramètre catégorie : '+field+'.')
        value=int(value)
        if value not in ((1,2,3) if field=='gestion_stock' else (1,2)):fail('Paramètre catégorie invalide : '+field+'.')
        ov[column]=value
    unit=draft.get('unite') or text(source['STU_0']);acct=draft.get('code_comptable') or text(source['ACCCOD_0']);tax=draft.get('taxe') or text(source['VACITM_0'])
    ov.update({key:unit for key in ('STU_0','PUU_0','SAU_0','SSU_0','EEU_0')});ov.update(ACCCOD_0=acct,VACITM_0=tax)
    return {'resource':'category','folder':folder,'code':draft['code'],'unit':unit,'accounting':acct,'tax':tax,'nodes':[node(schema,'ITMCATEG',source,ov)],'dependencies':[],'defaults_source':draft['modele']}

def article_plan(article,schema=None,existing_suppliers=()):
    folder=supplier_sql.target(article.get('dossier_cible','TEST'))
    for key,label in (('designation','désignation'),('categorie','catégorie'),('code_article','code article'),('unite','unité de stock (code ou libellé, par exemple UN ou mètre carré)')):
        if not article.get(key):fail('Précisez '+label+'. Les autres informations sont conservées.')
    code=article['code_article'];stock=int(article.get('gestion_stock') or 0)
    if not re.fullmatch(r'[A-Za-z0-9_./-]{1,50}',code):fail('Le code article contient des caractères non autorisés.')
    schema=schema or (catalog(article['categorie'],stock,code,folder=folder) if folder!='TEST' else catalog(article['categorie'],stock,code))
    if folder=='OB' and schema.get('folder')!='OB':fail('Modele article hors dossier OB.')
    categories=[r for r in schema['categories'] if text(r['TCLCOD_0'])==article['categorie'] and not text(r['STOFCY_0'])]
    if len(categories)!=1:fail('Catégorie absente : '+article['categorie']+'. Préparez sa création puis confirmez-la avant de créer cet article.')
    cat=categories[0];flags={field:int(cat[column]) for field,column in FLAGS.items()}
    for field in FLAGS:
        if article.get(field) is not None and int(article[field])!=flags[field]:fail('La catégorie '+article['categorie']+' ne correspond pas au paramètre demandé : '+field+'. Choisissez une catégorie compatible ou préparez-en une nouvelle.')
    stock=flags['gestion_stock'];unit=article.get('unite') or text(cat['STU_0']);acct=article.get('code_comptable') or text(cat['ACCCOD_0']);tax=article.get('code_tva') or article.get('niveau_taxe') or text(cat['VACITM_0'])
    if article.get('compte_general') and not article.get('code_comptable'):
        query=text(article['compte_general'])
        matches=sorted({text(r['ACCCOD_0']) for r in schema['accounting'] if text(r.get('ACCCOD_0')).startswith(query) or any(re.fullmatch(r'ACC_\d+',key) and text(value).startswith(query) for key,value in r.items())})
        if matches:fail('Codes comptables article trouvés dans '+folder+' pour '+query+' : '+', '.join(matches[:12])+'. Indiquez « code comptable : … » avec le code à retenir après vérification de son applicabilité à la catégorie '+article['categorie']+'.')
        fail('Aucun code comptable article relié à '+query+' dans '+folder+'. La recherche porte sur les codes et comptes commençant par '+query+'. Indiquez un autre compte ou un code comptable article existant ; la fiche est conservée.')
    if article.get('accounting_category') and not article.get('code_comptable'):fail('Précisez le code comptable article validé. Un libellé comptable seul ne permet pas de le déduire.')
    if article.get('taux_tva') and not article.get('code_tva') and not article.get('niveau_taxe'):fail('Précisez le code taxe applicable ; un taux seul ne permet pas de déduire une règle de TVA.')
    if unit not in {text(r['UOM_0']) for r in schema['units']}:fail('Unité non retrouvée dans TEST.')
    if not acct:fail('La catégorie '+article['categorie']+' ne définit pas de code comptable par défaut. Quel code comptable ou compte souhaitez-vous utiliser pour cet article ? Il sera vérifié dans '+folder+'.')
    if acct not in {text(r['ACCCOD_0']) for r in schema['accounting']}:fail('Code comptable non retrouvé dans '+folder+'.')
    levels=schema.get('tax_levels')
    if tax not in ({text(r['VACITM_0']) for r in levels} if levels is not None else {text(r['VAT_0']) for r in schema['taxes']}):fail('Niveau de taxe article non retrouvé dans '+folder+'.')
    if any(article.get(k) and article[k]!=unit for k in ('unite_achat','unite_vente')):
        sale=article.get('unite_vente')
        declared=article.get('conversion_vente_declaree') or {}
        if declared and {declared.get('source_unit'),declared.get('target_unit')}=={unit,sale}:
            fail('Équivalence enregistrée : 1 '+declared['source_unit']+' = '+declared['coefficient']+' '+declared['target_unit']+'. Le sens est connu ; aucune nouvelle confirmation de cette égalité n’est nécessaire. La création avec ces unités distinctes reste bloquée par la validation technique de conversion, non prise en charge par ce parcours. Les valeurs sont conservées.')
        if sale and sale!=unit and article.get('coefficient_vente_declare'):
            coefficient=article['coefficient_vente_declare']
            if not re.fullmatch(r'\d+(?:[.,]\d+)?',str(coefficient)):fail('Le coefficient doit être un nombre. Donnez une égalité complète entre les unités ; aucune formule ne sera insérée dans un coefficient.')
            fail('Unité de stock '+unit+', unité de vente '+sale+' et coefficient '+coefficient+' conservés. Voulez-vous dire « 1 '+sale+' = '+coefficient+' '+unit+' » ou « 1 '+unit+' = '+coefficient+' '+sale+' » ? La création avec unités distinctes reste soumise à une conversion validée ; aucune unité ne sera remplacée automatiquement.')
        fail('Les conversions entre unités distinctes doivent être validées avant création. Les unités demandées sont conservées ; précisez leur équivalence et son sens.')
    sites=list(dict.fromkeys(article.get('requested_sites') or ([article['site']] if article.get('site') else [])))
    if not sites:fail('Pour quels sites souhaitez-vous préparer cet article ?')
    if len(sites)>10 or any(s not in {text(r['FCY_0']) for r in schema['sites']} for s in sites):fail('Un site demandé est absent de TEST ou la liste dépasse dix sites.')
    providers=list(article.get('fournisseurs') or [])
    if not providers and article.get('code_fournisseur'):providers=[{'code':article['code_fournisseur'],'reference':article.get('reference_fournisseur') or ''}]
    if article.get('supplier_intent')=='none' and providers:fail('Demande contradictoire : sans fournisseur et fournisseurs indiqués. Précisez votre choix.')
    if article.get('fournisseur_nom') and not providers:fail('Précisez le code du fournisseur ; son nom seul n’a pas été rapproché avec certitude.')
    if len(providers)>10 or len({p['code'] for p in providers})!=len(providers):fail('Fournisseurs répétés ou trop nombreux : corrigez la liste.')
    required=supplier_required(sites)
    if flags['vendu']==2 and required and not (providers or existing_suppliers):fail('Cet article est utilisable à la vente : rattachez au moins un fournisseur avant confirmation. Le Flag fournisseur sera coché automatiquement. Le site 202 seul est exempté.')
    principal=article.get('fournisseur_principal') or ''
    if principal and principal not in {p['code'] for p in providers}:fail('Le fournisseur principal doit appartenir à la liste confirmée.')
    flag=int(article.get('flag_fournisseur') or (2 if providers else 1))
    if flag not in (1,2):fail('Flag fournisseur invalide : précisez oui ou non.')
    if flags['vendu']==2 and (required or providers or existing_suppliers):flag=2
    if not (providers or existing_suppliers) and flag!=1:fail('Sans fournisseur, le flag fournisseur doit rester décoché.')
    master=chosen(schema['articles'],stock,article.get('modele_article'),('TESTART201' if stock==1 else 'A10/40',),unit)
    ov={'ITMREF_0':code,'TCLCOD_0':article['categorie'],'ITMDES1_0':article['designation'],'SEAKEY_0':code,'ITMSTA_0':int(article.get('statut_article') or 1),'ACCCOD_0':acct,'VACITM_0':tax,'XFLGBPS_0':flag,'XBPS_0':principal}
    ov.update({column:flags[field] for field,column in FLAGS.items() if any(c['table']=='ITMMASTER' and c['column']==column for c in schema['columns'])})
    ov.update(unit_values(schema,'ITMMASTER',unit))
    if article.get('allow_negative_stock') is not None:
        menu={int(row['LANNUM_0']):text(row['LANMES_0']).casefold() for row in schema.get('menus',[]) if row.get('CODFIC_0')=='ITMMASTER' and row.get('CODZONE_0')=='NEGSTO'}
        if menu.get(1)!='non' or menu.get(2)!='oui':fail('Choix de stock négatif conservé ; son menu Sage doit être vérifié avant préparation.')
        if article['allow_negative_stock'] and stock==1:fail('Le stock négatif ne peut pas être autorisé pour un article non géré en stock.')
        if not any(column['table']=='ITMMASTER' and column['column']=='NEGSTO_0' for column in schema['columns']):fail('Champ de stock négatif absent du dictionnaire article.')
        ov['NEGSTO_0']=2 if article['allow_negative_stock'] else 1
    if article.get('type_article') is not None:fail('Précisez le champ de type article et sa règle métier validée : aucune colonne ne sera supposée.')
    for i,value in enumerate(article.get('familles_statistiques') or []):ov['TSICOD_'+str(i)]=value
    nodes=[node(schema,'ITMMASTER',master,ov)];summary=[]
    if flags['vendu']==2:
        sales=chosen(schema['sales'],preferred=(master['ITMREF_0'],'TESTART201'),unit=unit)
        nodes.append(node(schema,'ITMSALES',sales,{'ITMREF_0':code,'ITMDES1_0':article['designation'],**unit_values(schema,'ITMSALES',unit)}))
    for site in sites:
        candidates=[r for r in schema['facilities'] if text(r['STOFCY_0'])==site]
        source=chosen(candidates,stock,article.get('modele_site'),(master['ITMREF_0'],'TESTART201','CONTRAT_MAINTENAN','A10/40'),unit)
        sitecat=[r for r in schema['categories'] if text(r['TCLCOD_0'])==article['categorie'] and text(r['STOFCY_0'])==site]
        if any(int(r['STOMGTCOD_0'])!=stock for r in sitecat):fail('Paramètres de catégorie incompatibles pour le site '+site+'.')
        nodes.append(node(schema,'ITMFACILIT',source,{'ITMREF_0':code,'STOFCY_0':site,'STOMGTCOD_0':stock,**unit_values(schema,'ITMFACILIT',unit)},site=site))
    for provider in providers:
        if provider['code'] not in {text(r['BPSNUM_0']) for r in schema['suppliers']}:fail('Fournisseur absent de TEST : '+provider['code']+'.')
        ref=provider.get('reference') or code+'_'+provider['code'];generated=not provider.get('reference')
        length(schema,'ITMBPS','BPSNUM_0',provider['code'])
        col=next(c for c in schema['columns'] if c['table']=='ITMBPS' and c['column']=='ITMREFBPS_0');limit=col['max_length']//2 if col['type'].startswith('n') else col['max_length']
        strategy='code_article_code_fournisseur'
        if generated and len(ref)>limit:ref='R'+hashlib.sha256((code+'|'+provider['code']).encode()).hexdigest().upper()[:limit-1];strategy='reference_technique_hachee_a_confirmer'
        source=chosen(schema['supplier_models'],model=article.get('modele_fournisseur'),preferred=('SCREW_F994',),unit=unit)
        nodes.append(node(schema,'ITMBPS',source,{'ITMREF_0':code,'BPSNUM_0':provider['code'],'ITMREFBPS_0':ref,**unit_values(schema,'ITMBPS',unit)},supplier=text(source['BPSNUM_0'])))
        summary.append({'code':provider['code'],'reference':ref,'generated':generated,'strategy':strategy})
    tr=chosen(schema['translations'],model=article.get('modele_traduction'),preferred=('TESTART201',))
    nodes.append(node(schema,'ATEXTRA',tr,{'CODFIC_0':'ITMMASTER','ZONE_0':'DES1AXX','IDENT1_0':code,'IDENT2_0':'','LANGUE_0':'FRA','TEXTE_0':article['designation']}))
    return {'resource':'article','folder':folder,'code':code,'unit':unit,'accounting':acct,'tax':tax,'nodes':nodes,'dependencies':[{'table':'ITMCATEG','model':article['categorie'],'site':'','source_hash':cat['source_hash']}],
      'summary':{'designation':article['designation'],'category':article['categorie'],'sites':sites,'suppliers':summary,'principal':principal,'flag_fournisseur':flag,**flags,'unit':unit,'accounting':acct,'tax':tax,'status':ov['ITMSTA_0'],'translation':'FRA','model':master['ITMREF_0'],'copied_defaults':{k:ov.get(k,v) for k,v in master['fields'].items() if k.startswith('TSICOD_') or k in ('ITMTYP_0','HDKITMTYP_0','ITMSFTTYP_0','INVPRODTYP_0')}}}

def prepare(article,resource='article',schema=None):
    plan=category_plan(article,schema) if resource=='category' else article_plan(article,schema)
    folder=plan['folder']
    result=transport('plan',plan,False,folder=folder) if folder!='TEST' else transport('plan',plan,False)
    if result.get('folder')!=folder:fail('Preuve de preparation article hors dossier de la conversation.')
    if not result.get('ok'):fail(result.get('message') or 'Préparation refusée par les contraintes Sage. Vos données sont conservées.')
    if result.get('transaction_state')!='VALIDATED_NO_INSERT' or result.get('executed'):fail('La préparation n’a pas fourni de preuve de lecture seule.')
    op={'id':str(uuid4()),'resource':resource,'action':'create','folder':folder,'transport':'direct_sql_article','status':'prepared','plan':plan,'query_digest':digest(),'preview':result,'summary':plan.get('summary') or {'code':plan['code'],'parameters':plan['nodes'][0]['overrides']},'input_hash':fingerprint(article) if resource=='article' else crud.digest(article)}
    op['digest']=crud.digest({'plan':plan,'query':op['query_digest']});return op

def verify(plan,result):
    if result.get('ok') is not True or result.get('folder')!=plan.get('folder','TEST') or result.get('resource')!=plan['resource'] or result.get('code')!=plan['code'] or result.get('executed') is not True or result.get('transaction_state')!='COMMIT' or result.get('sql_verified') is not True:return False
    records=result.get('records') or []
    return len(records)==len(plan['nodes']) and all(r['tab']==n['table'] and r.get('inserted')==1 and text(r.get('site'))==text(n['overrides'].get('STOFCY_0')) and text(r.get('supplier'))==text(n['overrides'].get('BPSNUM_0')) for r,n in zip(records,plan['nodes']))
