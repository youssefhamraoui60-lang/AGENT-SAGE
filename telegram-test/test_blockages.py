import asyncio
import pytest
import prepare
import creation
from blockages import explain


def test_col_conflict_keeps_line_and_proposes_validated_candidate(monkeypatch):
    test={'ITMREF_0':'COL','ITMDES1_0':'COL 250 ML ST','SAU_0':'UN','SITE_OK':0,'VACITM_0':'T20'}
    ob={**test,'ITMDES1_0':'Colle TRADICEM X 25 Kg','SAU_0':'SAC','SITE_OK':1}
    alternative={**ob,'ITMREF_0':'COL_F307'}
    def lookup(kind,code,**kwargs):
        return [alternative] if code=='TRADICEM' else [ob if kwargs.get('folder')=='OB' else test]
    monkeypatch.setattr(prepare,'lookup',lookup)
    details={'client':{'BPCNUM_0':'C01401'},'source_draft':{'lines':[{'article':'COL'}]},'lines':[{'article':'COL','quantity':40,'price':65}], 'missing':[],'missing_fields':[],'reply':'Brouillon'}
    result=asyncio.run(explain(details))
    assert result['lines'][0]['article']=='COL'
    assert result['alternatives_test'][0]['ITMREF_0']=='COL_F307'
    assert 'identité produit COL' in result['missing_fields']
    with pytest.raises(creation.CreationError):creation.build_payload(result)


def test_client_created_under_new_code_is_suggestion_not_substitution(monkeypatch):
    ob={'BPCNUM_0':'C10635','BPCNAM_0':'CLIENT EXISTANT','CUR_0':'MAD'}
    test={**ob,'BPCNUM_0':'C00999'}
    monkeypatch.setattr(prepare,'lookup',lambda kind,code,**kwargs:[ob if kwargs.get('folder')=='OB' else test])
    d={'client':None,'source_draft':{'client':'C10635','lines':[]},'lines':[],'reply':'Brouillon','missing':[],'missing_fields':[]}
    result=asyncio.run(explain(d))
    assert result['client'] is None
    assert result['alternative_clients_test']==[test]
    assert any('C00999' in p for p in result['proposals'])
