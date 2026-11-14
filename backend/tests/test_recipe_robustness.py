"""Real recipe failure modes using actual validators, synthetic references only."""
from copy import deepcopy
import pytest
from app.services import conversation_chat as chat
from app.services.chat_model import Delta


def reference_case(stock):
    article={'id':'test','code_article':'TESTAGENT005','designation':'TEST IA RECETTE',
             'categorie':'NEG','unite':'UN','site':'201','gestion_stock':stock,
             'code_fournisseur':'F1025','fournisseur_nom':'Atlas','sources':{},'proposals':{}}
    refs={key:{'ok':True,'rows':[]} for key in ('duplicate','recent','article_site')}
    refs.update(category={'ok':True,'rows':[{'TCLCOD_0':'NEG'}]},
                units={'ok':True,'rows':[{'UOM_0':'UN'}]},
                site={'ok':True,'rows':[{'FCY_0':'201'}]},
                supplier={'ok':True,'rows':[{'BPSNUM_0':'F1025','BPRNAM_0':'Atlas'}]})
    return article,refs


@pytest.mark.parametrize('stock',['1','2'])
@pytest.mark.parametrize('failure,expected',[
 ('duplicate','duplicate_article_code'),('site','unknown:site'),
 ('category','unknown:categorie'),('unit','unknown:unite'),
 ('supplier','supplier_code_not_verified'),('communication','sql_checks_incomplete')])
def test_bad_recipe_never_becomes_ready(stock,failure,expected):
    article,refs=reference_case(stock)
    if failure=='duplicate':refs['duplicate']['rows']=[{'ITMREF_0':article['code_article']}]
    if failure=='site':refs['site']['rows']=[]
    if failure=='category':refs['category']['rows']=[]
    if failure=='unit':refs['units']['rows']=[]
    if failure=='supplier':refs['supplier']['rows']=[]
    if failure=='communication':refs['site']['ok']=False
    result=chat.validate_article_draft(article,refs)
    assert expected in result['errors'] and not result['valid_basic']
    assert not result['sage_created'] and not result['article_site_dependency']['creation_executed']


@pytest.mark.parametrize('stock',['1','2'])
def test_modification_invalidates_local_review_before_any_save(stock):
    article,_=reference_case(stock);article.update(reviewed=True,approved=True,operation={'status':'prepared'})
    before={'articles':[article]};chat.PERMITS[article['id']]={'synthetic':True}
    try:
        result=chat.merge(before,Delta(intent='update',shared={'site':'202'}),'Site déclaré 202')
        assert not result['articles'][0].get('reviewed') and not result['articles'][0].get('approved')
        assert 'operation' not in result['articles'][0] and article['id'] not in chat.PERMITS
        assert before['articles'][0]['site']=='201'
    finally:chat.PERMITS.pop(article['id'],None)
