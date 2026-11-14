"""Historical successful WS_ARTICLE fields through HTTP + simulated Sage only."""
from pathlib import Path
from copy import deepcopy
from lxml import etree
from test_sage_crud import client,FakeGateway,approval,execute
from app.services.sage_gateway import projection

def test_manual_payload_create_readback_and_one_attempt(client,monkeypatch):
    import test_sage_crud as suite
    root=Path(__file__).resolve().parents[2]
    cached=etree.fromstring((root/'runtime/crud-WS_ARTICLE-description.xml').read_bytes())
    monkeypatch.setattr(suite,'metadata',lambda resource:deepcopy(cached))
    original=etree.fromstring((root/'examples/step4/manual-success-object.xml').read_bytes())
    fields=[{'group':g.get('ID'),'name':f.get('NAME'),'value':f.text or ''} for g in original for f in g if f.get('NAME')!='ITMREF']
    request={'action':'create','keys':{'ITMREF':'SYNTHSAVEONLY001'},'fields':fields}
    operation=client.post('/api/v1/sage/articles/prepare',json=request)
    assert operation.status_code==200
    operation=operation.json()
    token=approval(client,operation)
    result=execute(client,'articles',operation,token)
    assert result.status_code==200
    record=result.json();assert record['status']=='succeeded' and record['after_record']['exists']
    expected=projection(original);expected['ITM0_1.ITMREF']='SYNTHSAVEONLY001'
    assert record['after_record']['fields']==expected
    assert all(record['result']['field_comparisons'].values())
    assert len(FakeGateway.writes)==1
    assert execute(client,'articles',operation,token).status_code in (403,409)
    assert len(FakeGateway.writes)==1
