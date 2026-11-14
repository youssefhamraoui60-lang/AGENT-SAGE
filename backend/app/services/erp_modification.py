"""Fixed TEST modification plans. Qwen never supplies SQL, columns, keys or policy."""
import hashlib,json,re,subprocess,copy
from pathlib import Path
from uuid import uuid4
from app.services import supplier_sql,article_sql,sage_crud as crud
from app.services.modification_policy import ArticleDependencyAnalyzer,ArticleModificationPolicy,block
from app.services.modification_resolvers import UnitResolver,CategoryResolver,clean,norm
from app.core.config import settings
ROOT=Path(__file__).resolve().parents[3]
TERMINAL={'executing','succeeded','ambiguous','cancelled'}

def _transport(action,resource='',code='',plan=None,execute=False,folder='TEST'):
    supplier_sql.target(folder)
    if plan is not None and plan.get('folder')!=folder:block('Dossier du plan incoherent.')
    if action not in ('catalog','snapshot','plan') or type(execute) is not bool:block('Action de modification non autorisée.')
    if execute and (not settings.sage_modification_enabled or settings.sage_mcp_enabled):block('Modifications désactivées dans ce service. MCP reste en lecture seule.')
    payload={'folder':folder,'action':action,'Resource':resource,'Code':code,'plan':plan,'execute':execute}
    try:
        p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'TEST/modification_worker.ps1')],input=json.dumps(payload,ensure_ascii=False),env=supplier_sql.connection_env(folder),capture_output=True,text=True,encoding='utf-8',timeout=65,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        result=json.loads(p.stdout.lstrip('\ufeff'),parse_float=str)
        if not isinstance(result,dict):raise ValueError()
        return result
    except (OSError,ValueError,subprocess.TimeoutExpired):
        if execute:return {'ok':False,'folder':folder,'retry_allowed':False,'outcome':'unknown'}
        block('Lecture SQL interrompue. Vos changements sont conservés ; aucune modification effectuée.')

def transport(action,resource='',code='',plan=None,execute=False,folder='TEST'):
    from app.services.sage_sql_queue import plan_slot,SagePlanBusy,not_started
    params=dict(resource=resource,code=code,plan=plan,execute=execute,folder=folder)
    if action!='plan':return _transport(action,**params)
    try:
        with plan_slot(folder):return _transport(action,**params)
    except SagePlanBusy:return not_started(folder)

def catalog(folder="TEST"):
    result=transport('catalog',folder=folder) if folder!='TEST' else transport('catalog')
    if result.get('ok') is not True or result.get('folder')!=folder:block('Schéma ou permissions de modification indisponibles. Aucun droit ne sera modifié.')
    return result

def snapshot(resource,code,folder="TEST"):
    if resource not in ('article','supplier','unit') or not re.fullmatch(r'[A-Za-z0-9_./-]{1,30}',code):block('Indiquez un code Sage exact pour retrouver la fiche.')
    result=transport('snapshot',resource,code,folder=folder) if folder!='TEST' else transport('snapshot',resource,code)
    if result.get('ok') is not True or result.get('folder')!=folder or result.get('code')!=code:block('Lecture de la fiche ou de ses dépendances indisponible. Aucune modification effectuée.')
    # SQL JSON may omit empty subqueries. Normalize only collection fields
    # after scope/success validation; never fabricate dependency clearance.
    for key in ('article_suppliers','sales','sites','translations','addresses'):
        if result.get(key) is None:result[key]=[]
        if not isinstance(result[key],list):block('Format de lecture SQL invalide ; aucune modification effectuée.')
    return result

def one(rows,message):
    if len(rows)!=1:block(message)
    return rows[0]

def fingerprint(d):return crud.digest({k:d.get(k) for k in ('id','resource','code','changes','folder')})
def query_digest():
    names=['backend/app/services/erp_modification.py','backend/app/services/modification_policy.py','backend/app/services/modification_resolvers.py','TEST/modification_worker.ps1','TEST/modification_transaction.sql','TEST/modification_dependency_scan.sql','TEST/modification_snapshot.sql','TEST/modification_catalog.sql','TEST/modification-approved-triggers.json']
    names.append('backend/app/services/sage_sql_queue.py')
    return hashlib.sha256(b''.join((ROOT/n).read_bytes() for n in names)).hexdigest()

def diff_rows(nodes):
    return [{'table':n['table'],'key':n['keys'],'field':key,'before':n.get('before',{}).get(key),'after':value,'action':n['kind']} for n in nodes for key,value in n['values'].items() if n.get('before',{}).get(key)!=value]

class ArticleUpdateService:
    def __init__(self,schema,view):self.schema=schema;self.view=view;self.nodes=[];self.reference_guards=[];self.code=view['code']
    def pin_conversion(self,source,target):
        for row in self.view['units']:
            if clean(row['UOM_0']) in (source,target):self.reference_guards.append({'table':'TABUNIT','keys':{'UOM_0':clean(row['UOM_0'])},'source_hash':row['source_hash']})
        for row in self.view['conversions']:
            if (clean(row['UOM1_0']),clean(row['UOM2_0'])) in ((source,target),(target,source)):
                self.reference_guards.append({'table':'TABCOEFF','keys':{'UOM1_0':clean(row['UOM1_0']),'UOM2_0':clean(row['UOM2_0'])},'source_hash':row['source_hash']})
    def update(self,table,row,keys,values):
        if not values:return
        for key,value in values.items():article_sql.length(self.schema,table,key,value)
        existing=next((n for n in self.nodes if n['table']==table and n['keys']==keys and n['kind']=='update'),None)
        if existing:existing['values'].update(values);existing['before'].update({k:row.get(k) for k in values});return
        self.nodes.append({'kind':'update','table':table,'keys':keys,'source_hash':row['source_hash'],'before':{k:row.get(k) for k in values},'values':values})

    def build(self,changes):
        changes=copy.deepcopy(changes)
        a=one(self.view['articles'],'Article introuvable ou non unique dans TEST.');key={'ITMREF_0':self.code};ov={}
        if 'sale_enabled' in changes:
            if type(changes['sale_enabled']) is not bool:block('Le choix utilisable à la vente doit être oui ou non.')
            category=one([c for c in self.view['categories'] if clean(c['TCLCOD_0'])==clean(a['TCLCOD_0'])],'Catégorie actuelle introuvable.')
            if changes['sale_enabled'] and int(category['SALFLG_0'])!=2:block('La catégorie actuelle ne permet pas l’activation à la vente. Choisissez une catégorie compatible avant ce changement.')
            if changes['sale_enabled'] and not self.view.get('sales'):block('Activation à la vente conservée : la fiche vente doit être préparée par une méthode validée avant ce changement.')
            ov['SALFLG_0']=2 if changes['sale_enabled'] else 1
        # Supplier principal is optional. The association itself is required
        # when a sale/supplier change makes the article usable for sales.
        linked={clean(r['BPSNUM_0']) for r in self.view['article_suppliers']}|{p['code'] for p in changes.get('add_suppliers',[])}
        sale=changes.get('sale_enabled',int(a.get('SALFLG_0') or 1)==2)
        effective_sites={clean(r['STOFCY_0']) for r in self.view['sites']}|set(changes.get('add_sites') or [])
        required=article_sql.supplier_required(effective_sites)
        if sale and set(changes)&{'sale_enabled','supplier_flag','add_suppliers','principal_supplier','add_sites'}:
            if required and not linked:block('Article utilisable à la vente : rattachez au moins un fournisseur. Le Flag fournisseur sera coché automatiquement ; le fournisseur principal est facultatif. Le site 202 seul est exempté.')
            if required and changes.get('supplier_flag') is False:block('Un article utilisable à la vente doit garder le Flag fournisseur coché et au moins un fournisseur lié.')
            if linked or required:changes['supplier_flag']=True
        if changes.get('supplier_flag') is False and changes.get('add_suppliers'):block('L’ajout de fournisseurs et la désactivation simultanée du Flag fournisseur sont contradictoires. Précisez le résultat souhaité.')
        for field,column in (('allow_negative_stock','NEGSTO_0'),('supplier_flag','XFLGBPS_0')):
            if field not in changes:continue
            if type(changes[field]) is not bool:block('Valeur booléenne requise pour cet indicateur article.')
            menu={int(r['LANNUM_0']):norm(r['LANMES_0']) for r in self.view.get('menus',[]) if r['CODFIC_0']=='ITMMASTER' and r['CODZONE_0']==column[:-2]}
            if menu.get(1)!='non' or menu.get(2)!='oui':block('Menu Sage de cet indicateur non vérifié : '+column+'.')
            if field=='allow_negative_stock' and changes[field] and int(changes.get('stock_mode',a.get('STOMGTCOD_0')) or 0)==1:block('Cet article est non géré en stock. Le passage en gestion de stock doit être vérifié séparément ; aucun changement implicite.')
            if field=='supplier_flag':
                linked={clean(r['BPSNUM_0']) for r in self.view['article_suppliers']}|{p['code'] for p in changes.get('add_suppliers',[])}
                principal=changes['principal_supplier'] if 'principal_supplier' in changes else clean(a.get('XBPS_0'))
                if changes[field] and not linked:block('Pour cocher Flag fournisseur, rattachez au moins un fournisseur ; le fournisseur principal est facultatif.')
                if principal and principal not in linked:block('Le fournisseur principal indiqué doit être lié à cet article.')
                ov['XBPS_0']=principal if changes[field] else ''
            ov[column]=2 if changes[field] else 1
        if 'replace_supplier' in changes:
            replacement=changes['replace_supplier']
            if not isinstance(replacement,dict) or set(replacement)!={'old','new'} or replacement['old']==replacement['new']:block('Précisez deux fournisseurs distincts pour le remplacement fonctionnel.')
            one([r for r in self.view['article_suppliers'] if clean(r['BPSNUM_0'])==replacement['old']],'L’ancien fournisseur n’est pas référencé sur cet article.')
            if not any(clean(r['BPSNUM_0'])==replacement['new'] for r in self.view['article_suppliers']):changes.setdefault('add_suppliers',[]).append({'code':replacement['new'],'reference':''})
            changes['principal_supplier']=replacement['new']
        if 'principal_supplier' in changes:
            if not isinstance(changes['principal_supplier'],str):block('Précisez le code du fournisseur principal ou une valeur vide pour le retirer.')
            linked={clean(r['BPSNUM_0']) for r in self.view['article_suppliers']}|{p['code'] for p in changes.get('add_suppliers',[])}
            if changes['principal_supplier'] and changes['principal_supplier'] not in linked:block('Le fournisseur principal doit être référencé sur cette fiche, ou ajouté dans le même plan confirmé.')
            ov['XBPS_0']=changes['principal_supplier']
            if changes['principal_supplier']:ov['XFLGBPS_0']=2
        if 'designation' in changes:
            value=changes['designation']
            if not isinstance(value,str) or not value.strip():block('Précisez le nouvel intitulé.')
            ov['ITMDES1_0']=value
            tr=one([r for r in self.view['translations'] if r.get('LANGUE_0')=='FRA' and not clean(r.get('IDENT2_0'))],'Traduction française absente ou ambiguë : préparation spécifique nécessaire avant changement d’intitulé.')
            self.update('ATEXTRA',tr,{'CODFIC_0':'ITMMASTER','ZONE_0':'DES1AXX','IDENT1_0':self.code,'IDENT2_0':'','LANGUE_0':'FRA'},{'TEXTE_0':value})
            for row in self.view['sales']:self.update('ITMSALES',row,key,{'ITMDES1_0':value})
        cat=one([c for c in self.view['categories'] if clean(c['TCLCOD_0'])==clean(a['TCLCOD_0'])],'Catégorie actuelle introuvable.')
        if 'category' in changes:
            target=one([c for c in self.view['categories'] if clean(c['TCLCOD_0'])==changes['category']],'Catégorie inconnue. Recherchez une catégorie compatible avant de confirmer.')
            for column in ('STOMGTCOD_0','PURFLG_0','SALFLG_0','MFGFLG_0','DLVFLG_0','SCPFLG_0','RCPFLG_0','STU_0','ACCCOD_0','VACITM_0'):
                if str(target[column]).strip()!=str(cat[column]).strip():block('Catégories incompatibles sur '+column+'. Un changement coordonné des paramètres doit être validé techniquement ; aucun écrasement automatique.')
            ignored={'TCLCOD_0','TCLDES_0','TCLSHO_0','UPDTICK_0','AUUID_0','ROWID','source_hash','CREUSR_0','UPDUSR_0','CREDAT_0','UPDDAT_0','CREDATTIM_0','UPDDATTIM_0'}
            differences=[k for k in set(cat)|set(target) if k not in ignored and cat.get(k)!=target.get(k)]
            if differences:block('Autres paramètres de catégorie différents : '+', '.join(sorted(differences)[:6])+'. Une migration coordonnée doit être validée avant changement.')
            ov['TCLCOD_0']=changes['category']
        if 'accounting' in changes:
            value=changes['accounting'];target=one([r for r in self.view['accounting'] if clean(r['ACCCOD_0'])==value and r.get('ENAFLG_0',2)==2],'Code comptable absent, inactif ou ambigu pour le type article.')
            previous=[r for r in self.view['accounting'] if clean(r['ACCCOD_0'])==clean(a['ACCCOD_0'])]
            matching=[r for r in previous if clean(r['COA_0'])==clean(target['COA_0'])]
            if not matching and previous:block('Le plan comptable diffère du paramétrage actuel. La compatibilité société/site doit être validée avant modification.')
            old=one(matching,'Paramètres comptables actuels ambigus pour le plan du code demandé.')
            self.reference_guards.append({'table':'GACCCODE','keys':{'TYP_0':1,'ACCCOD_0':clean(old['ACCCOD_0']),'COA_0':clean(old['COA_0'])},'source_hash':old['source_hash']})
            ov['ACCCOD_0']=value
        if 'tax_rate' in changes:block('Un taux seul ne détermine pas la TVA applicable. Précisez le niveau de taxe et son indice ; les trois niveaux actuels sont conservés.')
        if 'tax_level' in changes:
            tax=changes['tax_level']
            if not isinstance(tax,dict) or set(tax)!={'index','code'} or type(tax['index']) is not int or tax['index'] not in (0,1,2):block('Précisez un niveau de taxe et son indice 0, 1 ou 2.')
            one([r for r in self.view['tax_levels'] if clean(r['VACITM_0'])==tax['code'] and r.get('ENAFLG_0')==2],'Niveau de taxe inconnu ou inactif dans TEST.TABVACITM.')
            ov['VACITM_'+str(tax['index'])]=tax['code']
        if 'stock_mode' in changes and changes['stock_mode']!=int(a['STOMGTCOD_0']):
            if type(changes['stock_mode']) is not int or changes['stock_mode'] not in (1,2,3):block('Mode de gestion de stock invalide.')
            if changes['stock_mode']!=int(cat['STOMGTCOD_0']):block('Le mode demandé est incompatible avec la catégorie actuelle. Préparez une catégorie et un article compatibles.')
            ignored={'STOMGTCOD_0','UPDTICK_0','AUUID_0','ROWID','source_hash','CREUSR_0','UPDUSR_0','CREDAT_0','UPDDAT_0','CREDATTIM_0','UPDDATTIM_0'}
            different=[k for k in set(a)&set(cat) if k not in ignored and a[k]!=cat[k]]
            if different:block('Paramètres complémentaires de stock différents de la catégorie : '+', '.join(sorted(different)[:6])+'. Une migration métier coordonnée doit être validée ; aucun basculement partiel.')
            ov['STOMGTCOD_0']=changes['stock_mode']
            for row in self.view['sites']:self.update('ITMFACILIT',row,{**key,'STOFCY_0':clean(row['STOFCY_0'])},{'STOMGTCOD_0':changes['stock_mode']})
        resolver=UnitResolver();stock=changes.get('stock_unit') or clean(a['STU_0'])
        if 'stock_unit' in changes:
            resolver.find(stock,self.view)
            # Category STU is a creation default, not a list of allowed units.
            # Existing quantities and all conversion checks below still apply.
            if any(clean(a[k])!=stock for k in ('PUU_0','SAU_0','SSU_0','EEU_0')):block('L’unité '+stock+' existe. Le passage de '+clean(a['STU_0'])+' à '+stock+' en stock exige une conversion vérifiée et la migration coordonnée des unités d’achat, de vente, statistiques et des conditionnements. Aucun coefficient ne sera inventé ; les changements proposés sont conservés, aucune modification partielle appliquée.')
            if stock!=clean(a['STU_0']):
                from decimal import Decimal
                old=clean(a['STU_0'])
                if Decimal(resolver.coefficient(old,stock,self.view))!=1:block('Cette conversion de l’unité de stock modifierait les quantités ou valeurs. Une migration métier complète doit être validée ; seul un changement vérifié à 1 pour 1 est pris en charge ici.')
                self.pin_conversion(old,stock)
                for u,c in [('PUU_0','PUUSTUCOE_0'),('SAU_0','SAUSTUCOE_0'),('SSU_0','SSUSTUCOE_0'),('EEU_0','EEUSTUCOE_0')]+[('PCU_'+str(i),'PCUSTUCOE_'+str(i)) for i in range(6)]:
                    if u not in a or not clean(a[u]):continue
                    if c not in a or Decimal(resolver.coefficient(clean(a[u]),stock,self.view))!=Decimal(str(a[c])):block('Un coefficient de conditionnement doit être migré. Aucun changement partiel de l’unité de stock.')
                    self.pin_conversion(clean(a[u]),stock)
            ov['STU_0']=stock
        for field,col,coeff in (('purchase_unit','PUU_0','PUUSTUCOE_0'),('sale_unit','SAU_0','SAUSTUCOE_0')):
            if field not in changes:continue
            change=changes[field]
            if not isinstance(change,dict) or set(change)-{'code','coefficient'} or not change.get('code'):block('Précisez le code unité et, si connu, son coefficient.')
            value=change['code'];rate=resolver.coefficient(value,stock,self.view,change.get('coefficient'))
            self.pin_conversion(value,stock)
            ov.update({col:value,coeff:rate})
            if field=='purchase_unit':
                for row in self.view['article_suppliers']:
                    if clean(row['PUU_0'])!=value:block('Les unités de référencement fournisseur diffèrent. Une migration coordonnée des conditionnements doit être validée.')
        if changes.get('deactivate') is True:
            menus=[r for r in self.view['menus'] if r['CODFIC_0']=='ITMMASTER' and r['CODZONE_0']=='ITMSTA' and norm(r['LANMES_0'])=='non utilisable']
            ov['ITMSTA_0']=one(menus,'Statut de désactivation non vérifié dans le dictionnaire Sage.')['LANNUM_0']
        if 'supplier_reference' in changes:
            p=changes['supplier_reference']
            if not isinstance(p,dict) or set(p)!={'code','reference'} or not p['reference']:block('Précisez le fournisseur et sa référence exacte.')
            row=one([r for r in self.view['article_suppliers'] if clean(r['BPSNUM_0'])==p['code']],'Association fournisseur absente ou ambiguë.')
            self.update('ITMBPS',row,{**key,'BPSNUM_0':p['code']},{'ITMREFBPS_0':p['reference']})
        self.update('ITMMASTER',a,key,ov)
        if changes.get('add_sites') or changes.get('add_suppliers'):
            sites=changes.get('add_sites') or [clean(r['STOFCY_0']) for r in self.view['sites']][:1]
            if not isinstance(sites,list) or not sites or any(not isinstance(s,str) for s in sites) or len(set(sites))!=len(sites):block('Indiquez les codes de sites distincts à ajouter.')
            if changes.get('add_sites') and any(s in {clean(r['STOFCY_0']) for r in self.view['sites']} for s in sites):block('Un des sites demandés existe déjà ; aucune création en double.')
            providers=changes.get('add_suppliers') or []
            if not isinstance(providers,list) or any(not isinstance(p,dict) or set(p)-{'code','reference'} or not p.get('code') for p in providers):block('Liste de fournisseurs illisible.')
            if any(p['code'] in {clean(r['BPSNUM_0']) for r in self.view['article_suppliers']} for p in providers):block('Un fournisseur est déjà référencé sur cet article.')
            data={'dossier_cible':self.view.get('folder','TEST'),'code_article':self.code,'designation':clean(a['ITMDES1_0']),'categorie':clean(a['TCLCOD_0']),'unite':stock,'code_comptable':clean(a.get('ACCCOD_0')),'code_tva':clean(a.get('VACITM_0')),'requested_sites':sites,'fournisseurs':providers,**{f:str(a[c]) for f,c in article_sql.FLAGS.items() if c in a}}
            plan=article_sql.article_plan(data,existing_suppliers=[clean(r['BPSNUM_0']) for r in self.view['article_suppliers']])
            for n in plan['nodes']:
                if n['table']=='ITMFACILIT' and not changes.get('add_sites') or n['table']=='ITMBPS' and not providers:continue
                if n['table'] not in ('ITMFACILIT','ITMBPS'):continue
                keys={**key,**({'STOFCY_0':n['overrides']['STOFCY_0']} if n['table']=='ITMFACILIT' else {'BPSNUM_0':n['overrides']['BPSNUM_0']})}
                source_keys={'ITMREF_0':n['model'],**({'STOFCY_0':n['site']} if n['table']=='ITMFACILIT' else {'BPSNUM_0':n['supplier']})}
                self.nodes.append({'kind':'insert','table':n['table'],'keys':keys,'model_keys':source_keys,'source_hash':n['source_hash'],'before':{},'values':n['overrides']})
            if providers and int(a['XFLGBPS_0'])!=2 and not changes.get('principal_supplier'):
                linked={clean(r['BPSNUM_0']) for r in self.view['article_suppliers']}|{p['code'] for p in providers}
                principal=clean(a['XBPS_0'])
                if principal and principal not in linked:block('Le fournisseur principal actuel n’est pas référencé. Corrigez ce lien avant confirmation.')
                self.update('ITMMASTER',a,key,{'XFLGBPS_0':2,'XBPS_0':principal})
        return self.nodes

class SupplierUpdateService(ArticleUpdateService):
    def build(self,changes):
        p=one(self.view['partners'],'Tiers fournisseur introuvable.');s=one(self.view['suppliers'],'Fournisseur introuvable.')
        if 'contact_name' in changes:block('Les références de contacts CONTACT/CONTACTCRM doivent être validées avant leur modification. Aucun nom libre ne sera écrit à la place d’un contact existant.')
        if 'name' in changes and clean(p.get('BPRNAM_1')):block('La raison sociale actuelle comporte une deuxième ligne. Une modification légale coordonnée des deux lignes doit être validée ; aucune ligne ne sera effacée implicitement.')
        partner={};supplier={};address={}
        if 'enabled' in changes:
            if type(changes['enabled']) is not bool:block('Statut fournisseur invalide.')
            if p.get('ENAFLG_0') not in (1,2) or s.get('ENAFLG_0') not in (1,2):block('Statut actuel fournisseur non reconnu. Vérification nécessaire.')
            for table in ('BPARTNER','BPSUPPLIER'):
                menu={int(r['LANNUM_0']):norm(r['LANMES_0']) for r in self.view.get('menus',[]) if r['CODFIC_0']==table and r['CODZONE_0']=='ENAFLG'}
                if menu.get(1) not in ('non','inactif','desactive') or menu.get(2) not in ('oui','actif','active'):block('Menu actif/inactif Sage non vérifié pour '+table+'.')
            partner['ENAFLG_0']=supplier['ENAFLG_0']=2 if changes['enabled'] else 1
        for field,pcol,scol in (('name','BPRNAM_0','BPSNAM_0'),('short_name','BPRSHO_0','BPSSHO_0'),('contact_name','CNTNAM_0','CNTNAM_0')):
            if field in changes:
                if not isinstance(changes[field],str) or not changes[field].strip():block('Valeur vide interdite : '+field+'.')
                partner[pcol]=changes[field];supplier[scol]=changes[field]
        for field,col in (('ice','XICE_0'),('if','XIF_0'),('rc','XRC_0')):
            if field not in changes:continue
            value=changes[field]
            if not isinstance(value,str) or (value and not re.fullmatch(r'[0-9]{15}' if field=='ice' else r'[0-9]+',value)):block('Identifiant fiscal invalide ; les zéros initiaux doivent être conservés.')
            partner[col]=value
        if 'payment' in changes:
            value=changes['payment'];rows=[r for r in self.view['payments'] if clean(r['PTE_0'])==value]
            if not rows:
                matches=[r for r in supplier_sql.load_reference_labels(self.view.get('folder','TEST')) if r['kind']=='Paiement' and supplier_sql.reference_norm(r['label'])==supplier_sql.reference_norm(str(value))]
                codes={r['code'] for r in matches}
                if len(codes)!=1:block('Conditions de paiement inconnues ou ambiguës. Précisez un code Sage valide ; aucun code ne sera inventé.')
                value=codes.pop();rows=[r for r in self.view['payments'] if clean(r['PTE_0'])==value]
                self.payment_label=next(r['label'] for r in matches if r['code']==value)
            row=one(rows,'Conditions de paiement inconnues ; indiquez un code Sage valide.')
            self.reference_guards.append({'table':'TABPAYTERM','keys':{'PTE_0':value},'source_hash':row['source_hash']})
            supplier['PTE_0']=value
        for field,col in (('city','CTY_0'),('phone','TEL_0'),('email','WEB_0')):
            if field in changes:
                if not isinstance(changes[field],str):block('Coordonnée illisible : '+field+'.')
                if field=='email' and changes[field] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',changes[field]):block('Adresse email invalide.')
                address[col]=changes[field]
        if 'address' in changes:
            value=changes['address']
            if not isinstance(value,str):block('Adresse illisible.')
            lines=[];remaining=value.strip()
            while remaining and len(lines)<3:
                if len(remaining)<=50:lines.append(remaining);remaining='';break
                cut=remaining.rfind(' ',0,51)
                if cut<1:cut=50
                lines.append(remaining[:cut]);remaining=remaining[cut:].lstrip()
            if remaining:block('Adresse trop longue pour les trois lignes Sage. Votre texte est conservé sans troncature.')
            address.update({'BPAADDLIG_'+str(i):lines[i] if i<len(lines) else '' for i in range(3)})
        self.update('BPARTNER',p,{'BPRNUM_0':self.code},partner);self.update('BPSUPPLIER',s,{'BPSNUM_0':self.code},supplier)
        if address:
            address_code=changes.get('address_code') or clean(s['BPAADD_0'])
            row=one([r for r in self.view['addresses'] if clean(r['BPAADD_0'])==address_code],'Adresse fournisseur absente ou ambiguë ; indiquez le code adresse.')
            self.update('BPADDRESS',row,{'BPANUM_0':self.code,'BPATYP_0':1,'BPAADD_0':address_code},address)
        return self.nodes

def approved_triggers(schema,tables,folder="TEST"):
    approved=json.loads((ROOT/'TEST/modification-approved-triggers.json').read_text(encoding='utf-8'))
    allowed={r['hash'] for r in approved if r.get('reviewed_by') and r.get('scope')==folder};result=[]
    for trigger in schema.get('triggers') or []:
        if trigger['table'] not in tables or trigger['is_disabled']:continue
        definition=next((r.get('definition') for r in schema.get('trigger_definitions',[]) if r['name']==trigger['name']),None)
        digest=hashlib.sha256(definition.encode('utf-16-le')).hexdigest().upper() if definition else None
        if digest not in allowed:block('Déclencheur '+trigger['name']+' non revu ou définition non lisible. Faites vérifier sa définition et son empreinte ; aucune permission ni règle ne sera contournée.')
        result.append({'table':trigger['table'],'name':trigger['name'],'hash':digest})
    return result

def resolve_tax_rate(value,view):
    from decimal import Decimal,InvalidOperation
    try:rate=Decimal(str(value).strip().rstrip('%').strip().replace(',','.'))
    except InvalidOperation:block('Précisez le taux de TVA souhaité en pourcentage.')
    if not rate.is_finite() or not 0<=rate<=100:block('Taux de TVA invalide.')
    taxes=[r for r in view.get('taxes',[]) if Decimal(str(r.get('VATRAT_0',-1)))==rate]
    if not taxes:block('Aucun code taxe ne correspond à ce taux dans TEST.')
    article=one(view.get('articles',[]),'Article introuvable dans TEST.')
    rules=view.get('tax_determinations',[]);candidates=[]
    def simple_rule(row):
        if any(clean(row.get(k)) for k in ('EXP1_0','EXP2_0')):return False
        expression=clean(row.get('EXPTST_0'))
        expected='[F:TLK]VACBPR="'+clean(row.get('VACBPR_0'))+'" & [F:TLK]VACITM="'+clean(row.get('VACITM_0'))+'"'
        return not expression or expression==expected
    ignored={'COD_0','LANDESSHO_0','VACDES_0','VACSHO_0','VACITM_0','VAT_0','UPDTICK_0','AUUID_0','ROWID','source_hash','CREUSR_0','UPDUSR_0','CREDAT_0','UPDDAT_0','CREDATTIM_0','UPDDATTIM_0'}
    for index in range(3):
        old=[r for r in rules if clean(r.get('VACITM_0'))==clean(article.get('VACITM_'+str(index))) and r.get('ENAFLG_0')==2]
        if not old:continue
        for tax in taxes:
            for rule in rules:
                if clean(rule.get('VAT_0'))!=clean(tax['VAT_0']) or rule.get('ENAFLG_0')!=2:continue
                if not simple_rule(rule) or not all(simple_rule(r) for r in old):continue
                if all(all(r.get(k)==rule.get(k) for k in set(r)|set(rule) if k not in ignored|{'EXPTST_0'}) for r in old):
                    candidates.append((index,rule,tax,old))
    choices={(i,clean(r['VACITM_0'])) for i,r,_,_ in candidates}
    if len(choices)!=1:block('Plusieurs contextes fiscaux sont possibles. Précisez le régime fiscal et le niveau de taxe ; les valeurs actuelles sont conservées.')
    index,rule,tax,old=candidates[0]
    guards=[{'table':'TABVAT','keys':{'VAT_0':tax['VAT_0']},'source_hash':tax['source_hash']}]
    guards.extend({'table':'TABVAC','keys':{'COD_0':r['COD_0']},'source_hash':r['source_hash']} for r in [rule,*old])
    return {'index':index,'code':clean(rule['VACITM_0'])},guards

def build(draft,schema,view):
    folder=supplier_sql.target(draft.get('folder','TEST'))
    if folder=='OB' and (view.get('folder')!='OB' or schema.get('folder')!='OB'):block('Lectures de controle hors dossier OB.')
    resource=draft['resource'];changes=copy.deepcopy(draft['changes']);analysis=ArticleDependencyAnalyzer().analyze(view)
    tax_guards=[]
    if resource=='article' and 'general_account' in changes:
        account=changes['general_account']
        rows=[r for r in view.get('general_accounts',[]) if clean(r.get('ACC_0'))==account]
        if not rows:block('Le compte général '+account+' est introuvable dans TEST.GACCOUNT. Aucun code comptable ne sera remplacé.')
        mappings=[r for r in view.get('accounting',[]) if any(k.startswith('ACC_') and clean(v)==account for k,v in r.items())]
        codes=', '.join(sorted({clean(r['ACCCOD_0']) for r in mappings})) or 'aucun'
        block('Le compte général '+account+' existe. Codes comptables qui le référencent : '+codes+'. Précisez l’imputation concernée (achat, vente ou stock) et le plan comptable. Un compte général ne remplace pas directement le code comptable de l’article.')
    if resource=='article' and 'tax_rate' in changes:
        changes['tax_level'],tax_guards=resolve_tax_rate(changes.pop('tax_rate'),view)
    if resource=='unit':return unit_plan(draft,schema,view)
    policy=ArticleModificationPolicy().check(resource,changes,analysis)
    service=ArticleUpdateService(schema,view) if resource=='article' else SupplierUpdateService(schema,view)
    nodes=service.build(changes)
    nodes=[n for n in nodes if n['kind']=='insert' or any(n['before'].get(k)!=v for k,v in n['values'].items())]
    if not nodes:block('Les valeurs demandées sont déjà enregistrées. Aucune modification nécessaire.')
    for n in nodes:
        permission=next((r for r in schema['permissions'] if r['table']==n['table']),{})
        right='can_update' if n['kind']=='update' else 'can_insert'
        if permission.get('can_select')!=1 or permission.get(right)!=1:block('Autorisation '+right.removeprefix('can_').upper()+' manquante sur '+folder+'.'+n['table']+'. Une requête minimale est destinée à l’administrateur ; aucun droit ne sera accordé automatiquement.')
    triggers=approved_triggers(schema,{n['table'] for n in nodes},folder)
    base=view['articles'][0] if resource=='article' else view['suppliers'][0]
    base_keys={'ITMREF_0':draft['code']} if resource=='article' else {'BPSNUM_0':draft['code']}
    guards=[{'table':'ITMMASTER' if resource=='article' else 'BPSUPPLIER','keys':base_keys,'source_hash':base['source_hash']}]
    guards.extend(service.reference_guards);guards.extend(tax_guards)
    if resource=='article':
        for code in {clean(base['TCLCOD_0']),changes.get('category')} - {None,''}:
            row=one([r for r in view['categories'] if clean(r['TCLCOD_0'])==code],'Catégorie de contrôle introuvable.')
            guards.append({'table':'ITMCATEG','keys':{'TCLCOD_0':code,'STOFCY_0':''},'source_hash':row['source_hash']})
        if 'accounting' in changes:
            row=one([r for r in view['accounting'] if clean(r['ACCCOD_0'])==changes['accounting']],'Code comptable ambigu.')
            guards.append({'table':'GACCCODE','keys':{'TYP_0':1,'ACCCOD_0':changes['accounting'],'COA_0':row['COA_0']},'source_hash':row['source_hash']})
        if 'tax_level' in changes:
            row=one([r for r in view['tax_levels'] if clean(r['VACITM_0'])==changes['tax_level']['code']],'Niveau de taxe ambigu.')
            guards.append({'table':'TABVACITM','keys':{'VACITM_0':changes['tax_level']['code']},'source_hash':row['source_hash']})
        for field in ('purchase_unit','sale_unit'):
            if field not in changes:continue
            u=changes[field]['code'];stock=clean(base['STU_0'])
            for row in view['conversions'] if u!=stock else []:
                if (clean(row['UOM1_0']),clean(row['UOM2_0'])) in ((u,stock),(stock,u)):
                    guards.append({'table':'TABCOEFF','keys':{'UOM1_0':clean(row['UOM1_0']),'UOM2_0':clean(row['UOM2_0'])},'source_hash':row['source_hash']})
    impact='Paramétrage courant et futures opérations uniquement. Aucun document historique, règlement, écriture comptable ou compte bancaire ne sera modifié.'
    if 'replace_supplier' in changes:impact+=' Remplacement fonctionnel : le nouveau fournisseur devient principal ; l’ancienne association est conservée et n’est pas désactivée.'
    diffs=diff_rows(nodes)
    for row in diffs:
        if row['field']=='PTE_0' and getattr(service,'payment_label',None):row['display_after']=str(row['after'])+' — '+service.payment_label
        if row['field']=='ITMSTA_0':
            menus={r['LANNUM_0']:r['LANMES_0'] for r in view.get('menus',[]) if r['CODFIC_0']=='ITMMASTER' and r['CODZONE_0']=='ITMSTA'}
            row['display_before']=menus.get(row['before'],row['before']);row['display_after']=menus.get(row['after'],row['after'])
    return {'folder':folder,'resource':resource,'code':draft['code'],'nodes':nodes,'guards':guards,'dependencies':view['dependencies'],'analysis':analysis,'policy':policy,'triggers':triggers,'diff':diffs,'impact':impact}

def unit_plan(draft,schema,view):
    from decimal import Decimal,InvalidOperation
    code=draft['code'];c=draft['changes'];resolver=UnitResolver()
    if any(clean(r['UOM_0'])==code for r in view['units']):block('Cette unité existe déjà. Réutilisez-la ; aucune nouvelle unité ne sera créée.')
    if set(c)-{'model','symbol','stock_unit','coefficient','inverse','decimals','international_code'}:block('Paramètre unité non pris en charge.')
    if not re.fullmatch(r'[A-Za-z0-9]{1,3}',code):block('Code unité invalide.')
    missing=[label for key,label in (('model','modèle de conditionnement'),('stock_unit','unité de stock'),('coefficient','coefficient vers le stock'),('inverse','coefficient inverse')) if key not in c or c[key] in (None,'')]
    if missing:block('Unité à compléter : '+', '.join(missing)+'. Les paramètres déjà donnés sont conservés.')
    source=resolver.find(c.get('model',''),view);stock=resolver.find(c.get('stock_unit',''),view)
    if int(source['UOMTYP_0'])!=7 or int(stock['UOMTYP_0'])!=4:block('La création d’un conditionnement exige un modèle conditionnement et une unité de masse vérifiés.')
    if c.get('international_code','')!='':block('Un identifiant international doit être validé séparément ; il ne sera pas copié du modèle.')
    if type(c.get('coefficient')) is float or type(c.get('inverse')) is float:block('Fournissez les coefficients comme textes décimaux exacts ; aucun arrondi JSON implicite.')
    try:forward=Decimal(str(c['coefficient']));back=Decimal(str(c['inverse']))
    except (KeyError,InvalidOperation):block('Précisez les deux coefficients exacts, dans leurs sens respectifs.')
    if not forward.is_finite() or not back.is_finite() or max(forward.adjusted(),back.adjusted())>38 or min(forward.adjusted(),back.adjusted())<-38:block('Coefficient non fini ou hors précision SQL ; aucune valeur approchée ne sera utilisée.')
    if forward<=0 or back<=0 or abs(forward*back-1)>Decimal('.0000001'):block('Les coefficients ne sont pas positifs et inverses.')
    decimals=c.get('decimals',0)
    if type(decimals) is not int or not 0<=decimals<=7:block('Précision unité invalide.')
    nodes=[{'kind':'insert','table':'TABUNIT','keys':{'UOM_0':code},'model_keys':{'UOM_0':clean(source['UOM_0'])},'source_hash':source['source_hash'],'values':{'UOM_0':code,'UOMDEC_0':decimals,'UOMSYM_0':c.get('symbol',code),'UOMTYP_0':7,'INTSAU_0':''},'before':{}}]
    for u1,u2,coefficient in ((code,c['stock_unit'],forward),(c['stock_unit'],code,back)):
        templates=[r for r in view['conversions'] if clean(r['UOM2_0'])==c['stock_unit'] and int(r['REV_0'])==1]
        template=one(templates[:1],'Modèle de conversion absent ; la structure doit être validée.')
        if any(clean(r['UOM1_0'])==u1 and clean(r['UOM2_0'])==u2 for r in view['conversions']):block('Une conversion existe déjà.')
        column=next(r for r in schema['columns'] if r['table']=='TABCOEFF' and r['column']=='COEUOM_0')
        if max(0,-coefficient.as_tuple().exponent)>column['scale'] or coefficient.adjusted()+1>column['precision']-column['scale']:block('Coefficient hors précision SQL autorisée ; aucune valeur arrondie silencieusement.')
        nodes.append({'kind':'insert','table':'TABCOEFF','keys':{'UOM1_0':u1,'UOM2_0':u2},'model_keys':{'UOM1_0':clean(template['UOM1_0']),'UOM2_0':clean(template['UOM2_0'])},'source_hash':template['source_hash'],'values':{'UOM1_0':u1,'UOM2_0':u2,'REV_0':1,'COEUOM_0':format(coefficient,'f')},'before':{}})
    for n in nodes:
        for key,value in n['values'].items():article_sql.length(schema,n['table'],key,value)
        p=next((r for r in schema['permissions'] if r['table']==n['table']),{})
        if p.get('can_insert')!=1:block('INSERT manquant sur TEST.'+n['table']+'. Proposition conservée, création d’unité bloquée jusqu’à autorisation administrateur et confirmation spécifique.')
    return {'folder':'TEST','resource':'unit','code':code,'nodes':nodes,'guards':[],'dependencies':view['dependencies'],'policy':{'sensitive':True},'triggers':approved_triggers(schema,{'TABUNIT','TABCOEFF'}),'diff':diff_rows(nodes),'impact':'Nouvelle unité uniquement ; aucun article ni coefficient existant modifié. Validation fonctionnelle Sage distincte.'}

def prepare(draft,schema=None,view=None):
    folder=supplier_sql.target(draft.get('folder','TEST'))
    schema=schema or (catalog(folder) if folder!='TEST' else catalog());view=view or (snapshot(draft['resource'],draft['code'],folder) if folder!='TEST' else snapshot(draft['resource'],draft['code']))
    plan=build(draft,schema,view)
    result=transport('plan',draft['resource'],draft['code'],plan,False,folder=folder) if folder!='TEST' else transport('plan',draft['resource'],draft['code'],plan,False)
    if result.get('ok') is not True or result.get('transaction_state')!='VALIDATED_NO_WRITE' or result.get('executed'):block(result.get('message') or 'Préparation refusée. Aucun enregistrement modifié.')
    digest=query_digest()
    return {'id':str(uuid4()),'transport':'direct_sql_modification','status':'prepared','plan':plan,'input_hash':fingerprint(draft),'query_digest':digest,'digest':crud.digest({'plan':plan,'query':digest}),'preview':result}

def verify(plan,result):
    records=result.get('records') or []
    return (result.get('ok') is True and result.get('folder')==plan.get('folder','TEST') and result.get('code')==plan['code'] and result.get('resource')==plan['resource'] and result.get('executed') is True and result.get('transaction_state')=='COMMIT' and result.get('verified') is True and result.get('affected')==len(plan['nodes']) and len(records)==len(plan['nodes']) and all(r.get('tab')==n['table'] and r.get('kind')==n['kind'] and r.get('affected')==1 for r,n in zip(records,plan['nodes'])))
