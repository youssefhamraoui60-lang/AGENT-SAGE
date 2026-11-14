import copy
from app.services.article_fact_resolution import resolve
from app.services import article_sql_dialogue as dialogue

def category_state():
    return {'supplier_target':'TEST','category_search':{'ok':True,'folder':'TEST','choices':[{'code':'NEG','label':'Négoce','parameters':{'STU_0':'UN'}}]}}

def test_same_site_reference_is_unique_scoped_and_not_negated():
    s={'articles':[{'id':'one','site':'201'},{'id':'two'}]}
    assert resolve('site','201','le deuxième cest pour le même site, pas un troisième',s,s['articles'][1],None)['value']=='201'
    assert resolve('site','201','pas le même site',s,s['articles'][1],None) is None
    s['articles'].append({'id':'three','site':'202'})
    assert resolve('site','201','le même site',s,s['articles'][1],None) is None

def test_verified_negoce_label_is_kept_after_literal_enrichment():
    text='non jai dit catégorie négouse pas matériel informatique'
    state=category_state();article={'id':'one','designation':'PAPIER','categorie_libelle':'Consommables'}
    proof=resolve('categorie','NEG',text,state,article,lambda q:state['category_search'])
    assert proof['reference']=='NEG'
    article.update(categorie='NEG',field_provenance={'categorie':proof})
    dialogue.enrich({'articles':[article]},text)
    assert article['categorie']=='NEG' and article['categorie_libelle']=='Négoce'
    dialogue.enrich({'articles':[article]},'je change la catégorie pas la désignation')
    assert article['categorie']=='NEG'

def test_stock_unit_from_verified_category_requires_user_delegation():
    s=category_state();a={'categorie_libelle':'Négoce'}
    assert resolve('unite','UN','pour le stock regarde la catégorie',s,a,None)['source']=='explicit_category_stock_unit'
    assert resolve('unite','M2','pour le stock regarde la catégorie',s,a,None) is None
    assert resolve('unite','UN','bonjour',s,a,None) is None
    assert resolve('unite','UN','pour le stock regarde la catégorie',s,{**a,'unite':'M2'},None) is None

def test_unite_cest_is_not_an_invented_unit_code():
    a={'id':'one','designation':'PAPIER'}
    dialogue.enrich({'articles':[a]},'pour les ventes l’unité cest UN, pour l’achat aussi UN et le stock regarde la catégorie')
    assert a['unite']=='UN'

def test_explicit_category_code_does_not_trigger_a_long_query():
    def forbidden(q):raise AssertionError('No search needed for literal AVNS')
    text='Prépare un article, code CXDEMO, désignation test, catégorie AVNS, unité UN, site 201, non géré en stock, acheté et vendu, sans fournisseur.'
    assert resolve('categorie','AVNS',text,{},None,forbidden) is None
