"""Literal comprehension regressions: no SQL transport, no Sage writes."""
import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services import article_sql_dialogue as dialogue

@pytest.mark.parametrize('opening',['Bonjour, je veux creer un article','cree un article','ajouter un article','bghit article','zid article'])
@pytest.mark.parametrize('marker',['','**','`','***','``'])
@pytest.mark.parametrize('separator',[', ','; '])
def test_fifty_literal_article_variants(opening,marker,separator):
    def marked(s):return marker+s+marker
    text=separator.join([opening+' '+marked('TESTIA001'),'designation '+marked('FOURNITURE BUREAU TEST'),'categorie '+marked('AVNS'),'non gere en stock','achete et vendu','unite '+marked('UN'),'site '+marked('202'),'sans fournisseur'])
    state={'articles':[{'id':'draft','designation':'incorrect model output'}]}
    dialogue.enrich(state,text)
    a=state['articles'][0]
    assert a['designation']=='FOURNITURE BUREAU TEST'
    assert a['categorie']=='AVNS' and a['unite']=='UN'
    assert a['requested_sites']==['202'] and a['site']=='202'
    assert a['gestion_stock']=='1' and a['achete']=='2' and a['vendu']=='2'
    assert a['fournisseurs']==[] and a['flag_fournisseur']=='1'
    assert '*' not in str(a) and '`' not in str(a)

def test_successive_corrections_preserve_facts():
    state={'articles':[{'id':'draft','designation':'**FOURNITURE BUREAU TEST**','code_article':'TESTIA001','categorie':'**AVNS**','site':'202','unite':'UN'}]}
    dialogue.enrich(state,"J'ai deja donne le code AVNS",copy.deepcopy(state))
    dialogue.enrich(state,'Supprime les etoiles dans les valeurs',copy.deepcopy(state))
    a=state['articles'][0]
    assert a['categorie']=='AVNS' and a['designation']=='FOURNITURE BUREAU TEST'
    assert a['site']=='202' and a['unite']=='UN' and a['code_article']=='TESTIA001'

def test_partial_model_does_not_erase_prior_values():
    before={'articles':[{'id':'draft','designation':'FOURNITURE BUREAU TEST','categorie':'AVNS','unite':'UN','site':'202','code_article':'TESTIA001'}]}
    changed=copy.deepcopy(before)
    changed['articles'][0].update(designation='TESTIA001',categorie=None,unite=None,site=None)
    dialogue.enrich(changed,'Supprime les etoiles dans les valeurs',before)
    assert all(changed['articles'][0][k]==v for k,v in before['articles'][0].items())
