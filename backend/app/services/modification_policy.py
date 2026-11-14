"""ERP restrictions independent of user approval and of the language model."""
import json
from app.services.sage_crud import CrudError

def block(message):raise CrudError(message,423)

class ArticleDependencyAnalyzer:
    CONFIG={'article':{'ITMMASTER','ITMFACILIT','ITMSALES','ITMBPS','ATEXTRA'},'supplier':{'BPARTNER','BPSUPPLIER','BPADDRESS','CONTACT','CONTACTCRM','ITMBPS','ITMMASTER'}}
    def analyze(self,snapshot):
        dep=snapshot.get('dependencies',{});resource=snapshot.get('resource','article')
        sources=dep.get('sources') or []
        missing=[r['tab'] for r in sources if r.get('readable') is not True]
        matches=[r for r in sources if r.get('has_matches') and r['tab'] not in self.CONFIG.get(resource,set())]
        # No assumption that an invoice/delivery is closed from its mere existence.
        active=[r for r in matches if r.get('active') is True]
        unknown=[r for r in matches if r.get('active') is None]
        quantities=[]
        for row in sources:
            if not row.get('evidence'):continue
            try:values=json.loads(row['evidence'],parse_float=str)
            except (ValueError,TypeError):continue
            quantities.extend({'table':row['tab'],'field':v['field'],'quantity':str(v.get('quantity','non vérifiée')),'absolute':str(v['absolute'])} for v in values)
        return {'complete':dep.get('complete') is True and bool(sources) and not missing,'coverage':dep.get('coverage'),'missing':missing,'used':bool(matches),'history':matches,'active':active,'unknown_activity':unknown,'quantities':quantities,'sources_checked':len(sources)}

class ArticleModificationPolicy:
    IMMUTABLE={'code','code_article','ITMREF_0','BPSNUM_0','BPRNUM_0'}
    ARTICLE={'designation','category','accounting','general_account','tax_level','tax_rate','stock_mode','stock_unit','purchase_unit','sale_unit','add_sites','remove_sites','add_suppliers','remove_suppliers','replace_supplier','principal_supplier','supplier_reference','deactivate','allow_negative_stock','supplier_flag','sale_enabled'}
    SUPPLIER={'name','short_name','address','city','phone','email','contact_name','ice','if','rc','payment','address_code','enabled'}
    SENSITIVE={'name','short_name','ice','if','rc','payment','enabled'}

    def check(self,resource,changes,analysis):
        if set(changes)&self.IMMUTABLE:block('Le code unique ne peut pas être modifié directement. Préparez une nouvelle fiche avec le nouveau code ; sa création et une éventuelle désactivation exigent des contrôles et confirmations distincts.')
        allowed=self.ARTICLE if resource=='article' else self.SUPPLIER
        if not changes or set(changes)-allowed:block('Modification non prise en charge : '+', '.join(sorted(set(changes)-allowed))+'. Les données sont conservées ; aucune écriture.')
        if not analysis['complete']:block('Analyse des dépendances incomplète : '+', '.join(analysis['missing'] or ['couverture du schéma non vérifiée'])+'. Aucune modification autorisée.')
        if resource=='supplier' and 'enabled' in changes:
            if type(changes['enabled']) is not bool:block('Le statut fournisseur doit être actif ou désactivé.')
            if analysis['active'] or analysis['unknown_activity']:
                block('Changement de statut bloqué : opérations actives ou clôture non démontrée dans '+', '.join(r['tab'] for r in (analysis['active']+analysis['unknown_activity'])[:8])+'. Aucun changement effectué.')
        if resource=='article':
            for flag in ('allow_negative_stock','supplier_flag','sale_enabled'):
                if flag in changes and type(changes[flag]) is not bool:block('Un indicateur article doit etre un booleen explicite.')
            if analysis['used'] and set(changes)&{'designation','category','stock_unit','stock_mode'}:
                block('Article déjà utilisé dans '+', '.join(r['tab'] for r in analysis['history'][:8])+'. Intitulé, catégorie, unité de stock et gestion de stock restent verrouillés, même avec confirmation. Un nouvel article peut être préparé.')
            if set(changes)&{'purchase_unit','sale_unit','sale_enabled','remove_sites','deactivate','remove_suppliers','replace_supplier','principal_supplier','supplier_reference'}:
                if analysis['active']:block('Des opérations actives empêchent cette modification : '+', '.join(r['tab'] for r in analysis['active'][:8])+'. Terminez-les avant une nouvelle préparation.')
                if analysis['unknown_activity']:block('La clôture des opérations de '+', '.join(r['tab'] for r in analysis['unknown_activity'][:8])+' n’est pas démontrée. Modification bloquée ; aucun historique ne sera supprimé.')
            if set(changes)&{'remove_sites','remove_suppliers'}:
                block('Le retrait physique n’est pas autorisé. Aucun indicateur de désactivation de cette association n’a encore été validé dans TEST. Un ajout séparé peut être préparé ; aucune suppression d’historique.')
        elif analysis['used'] and set(changes)&{'name','short_name','ice','if','rc'}:
            block('Ce fournisseur possède un historique. Le changement de ses données légales nécessite une procédure métier validée ; la confirmation seule ne suffit pas. Les coordonnées courantes peuvent être préparées séparément.')
        return {'sensitive':resource=='supplier' and bool(set(changes)&self.SENSITIVE) or resource=='article' and bool(set(changes)&{'accounting','tax_level'}),'future_only':True,'history_writes':False}
