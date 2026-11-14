from pydantic import BaseModel,ConfigDict,Field,model_validator
from typing import Annotated

Text=Annotated[str,Field(max_length=100,pattern=r'^[^\x00-\x1f]*$')]
Code=Annotated[str,Field(min_length=1,max_length=30,pattern=r'^[A-Za-z0-9_.\-/]+$')]
class Args(BaseModel):model_config=ConfigDict(extra='forbid',strict=True)
class Search(Args):
    name:Text=''
    code:Text=''
    @model_validator(mode='after')
    def criteria(self):
        if not (self.name.strip() or self.code.strip()):raise ValueError('Indiquez un nom ou un code.')
        return self
class ArticleSearch(Args):
    name:Text=Field(min_length=1)
    category:Text=''
class Record(Args):code:Code
class Duplicates(Args):
    ice:Annotated[str,Field(pattern=r'^(?:[0-9]{15})?$')]=''
    fiscal:Annotated[str,Field(pattern=r'^[0-9]{0,30}$')]=''
    rc:Annotated[str,Field(pattern=r'^[0-9]{0,30}$')]=''
    name:Text=''
    @model_validator(mode='after')
    def criteria(self):
        if not any((self.ice,self.fiscal,self.rc,self.name.strip())):raise ValueError('Indiquez un identifiant ou un nom.')
        return self
class Category(Args):
    code:Text=''
    name:Text=''
    site:Text=''
class Unit(Args):unit:Code
class Site(Args):site:Text=''
class Tax(Args):
    code:Text=''
    rate:Annotated[str,Field(pattern=r'^(?:[0-9]{1,2}(?:\.[0-9]{1,3})?)?$')]=''
    company:Text=''
class ArticleSite(Args):
    code:Code
    site:Code

# Name -> typed schema, existing SELECT tool, literal parameter mapping, description.
CATALOG={
 'sage_search_suppliers':(Search,'search_suppliers',{'name':'Label','code':'Supplier'},'Rechercher des fournisseurs dans TEST par nom ou code. Résultats de correspondance à vérifier.'),
 'sage_get_supplier':(Record,'get_supplier_record',{'code':'Supplier'},'Consulter la fiche exacte et les identifiants fiscaux d’un fournisseur TEST.'),
 'sage_check_supplier_duplicates':(Duplicates,'check_supplier_fiscal_duplicates',{'ice':'Ice','fiscal':'Fiscal','rc':'Rc','name':'Label'},'Vérifier les correspondances ICE, IF, RC ou nom dans TEST. Ne crée aucune fiche.'),
 'sage_search_customers':(Search,'search_customers',{'name':'Label','code':'Supplier'},'Rechercher les clients TEST par nom ou code.'),
 'sage_search_articles':(ArticleSearch,'search_articles',{'name':'Label','category':'Category'},'Rechercher des articles TEST par désignation et éventuellement catégorie.'),
 'sage_get_article':(Record,'get_article_record',{'code':'Code'},'Consulter un article TEST : catégorie, unités, niveaux fiscaux et gestion de stock. Ne retourne pas les quantités en stock.'),
 'sage_get_categories':(Category,'get_article_categories',{'code':'Category','name':'Label','site':'Site'},'Consulter les catégories article, unités et paramètres par site dans TEST.'),
 'sage_get_units':(Unit,'get_units',{'unit':'Unit'},'Vérifier une unité de mesure dans TEST.'),
 'sage_get_sites':(Site,'get_sites',{'site':'Site'},'Consulter les sites et sociétés de TEST ; aucun stock disponible n’est déduit.'),
 'sage_get_tax_rules':(Tax,'get_tax_rules',{'code':'Code','rate':'Rate','company':'Company'},'Consulter les taux de TVA et dates de validité dans TEST. L’applicabilité métier reste à confirmer.'),
 'sage_get_article_site':(ArticleSite,'get_article_site',{'code':'Code','site':'Site'},'Vérifier le lien article-site TEST. Ne retourne pas de quantité de stock.'),
 'sage_get_stock':(ArticleSite,'live_stock',{'code':'code','site':'site'},'Consulter les quantités actuelles de stock TEST pour un code article et un site explicites. Quantités par statut en unité de stock ; ne calcule pas le disponible après réservations.'),
}
UNAVAILABLE=['purchase_orders','receipts','deliveries','invoices','document_links','create','modify','execute_sql','customer_write_api']
