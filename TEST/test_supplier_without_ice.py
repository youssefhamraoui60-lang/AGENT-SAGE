import pytest
from test_chat_supplier_sql import supplier,workflow
from app.services import supplier_sql as sql
from app.services.sage_crud import CrudError

def test_ice_absent_stays_empty_and_is_not_taken_from_model():
    p=supplier();p.pop('ice')
    values=sql.parameters(p,{'ICE':'999999999999999'})
    assert values['ICE']==''

def test_invalid_nonempty_ice_is_rejected():
    p=supplier();p['ice']='123'
    with pytest.raises(CrudError):sql.parameters(p)

def test_named_supplier_without_ice_can_prepare_but_not_execute_without_approval(workflow):
    state,calls,call=workflow;p=state['partners'][0];p['nom']='ATLAS FOURNITURES';p.pop('ice')
    response=call('prepare');assert response.status_code==200,response.text
    op=response.json()['state']['partners'][0]['operation']
    assert op['status']=='prepared' and op['parameters']['ICE']==''
    assert call('execute',True).status_code==403 and calls==[False]
