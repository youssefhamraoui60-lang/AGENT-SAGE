"""Verified 3x50 TEST address mapping; never execute a Sage insertion."""
import pytest,re
from app.services import supplier_sql as sql,supplier_snapshots
from app.services.sage_crud import CrudError
from test_chat_supplier_sql import supplier,result

ADDRESS='BD AOULIKHA NACRI FLORIDA CENTRE PARK1 LOT N3 BUREAU N 6 SIDI MAAROUF'

@pytest.mark.parametrize('address',[ADDRESS,'A'*50,'A'*51,'A'*100,'A'*101,'A'*149,'A'*150,'ZONE INDUSTRIELLE '*7,'Rue\n du\t fournisseur','😀'*75,'É'*150,''])
def test_address_preserved_and_each_line_fits_real_nvarchar(address):
 lines=sql.split_address(address)
 assert len(lines)==3 and ''.join(lines)==re.sub(r'\s+',' ',address).strip()
 assert all(len(line.encode('utf-16-le'))//2<=50 for line in lines)

@pytest.mark.parametrize('address',['A'*151,'😀'*76,'Adresse '*40])
def test_overflow_never_truncated(address):
 with pytest.raises(CrudError):sql.split_address(address)

def test_supplied_address_prepares_two_lines_and_snapshot_shows_both():
 p=supplier();p.update(nom='AUTOR AUTO SARL AU',adresse=ADDRESS)
 values=sql.parameters(p,{})
 assert values['Adresse2'] and not values['Adresse3']
 assert ''.join(values[k] for k in ('Adresse','Adresse2','Adresse3'))==ADDRESS
 assert p['adresse']==ADDRESS
 p['operation']={'status':'prepared','parameters':values}
 rows=supplier_snapshots.capture({'partners':[p]})[0]['rows']
 assert [r['value'] for r in rows if r['key'] in ('Adresse','Adresse2')]==[values['Adresse'],values['Adresse2']]

def test_readback_requires_all_address_lines_and_does_not_claim_success_on_partial_result():
 p=supplier();p['adresse']=ADDRESS;values=sql.parameters(p,{})
 body=result(values);assert sql.verify(values,body)['comparisons']['Adresse2'] is True
 body['rows'][0]['ADRESSE2']='incorrect';assert sql.verify(values,body) is None
 body=result(values);body['rows'][0].pop('ADRESSE3');assert sql.verify(values,body) is None

def test_new_short_address_clears_model_complements_in_each_explicit_folder():
 p=supplier();p['adresse']='Rue 1';values=sql.parameters(p,{})
 assert values['Adresse2']==values['Adresse3']==''
 p['dossier_cible']='OB';other=sql.parameters(p,{})
 assert other['Adresse2']==other['Adresse3']=='' and other['Adresse']=='Rue 1'
