import pytest
from day_orders import validate_groups,refine_pending_plan


def test_day_plan_must_cover_every_message_once():
    source=[{'id':1,'text':'C01401'},{'id':2,'text':'20 sacs CPJ45'}]
    for proposed in [[{'ids':[1]}],[{'ids':[1,1,2]}],[{'ids':[1,2,99]}]]:
        with pytest.raises(ValueError):validate_groups(proposed,source)


def test_different_explicit_clients_are_not_automatically_combined():
    source=[{'id':1,'text':'C01401 : 20 sacs CPJ45'},{'id':2,'text':'C09802 : 1000 KG RAB12'}]
    result=validate_groups([{'ids':[1,2],'uncertain':False}],source)
    assert result[0]['uncertain'] is True


def test_customer_and_product_complement_can_stay_together():
    source=[{'id':1,'text':'1000 KG RAB12'},{'id':2,'text':'client C09802'}]
    result=validate_groups([{'ids':[1,2],'uncertain':False}],source)
    assert result[0]['uncertain'] is False


def test_transport_followup_survives_an_interleaved_other_contact():
    rows=[{'id':1,'text':'Contact : Aicha\n20 sacs CPJ45','date':'2026-11-09T09:00:00+01:00'},
          {'id':2,'text':'Contact : Omar\n10 KG RAB12','date':'2026-11-09T09:00:02+01:00'},
          {'id':3,'text':'Contact : Aicha\n50 trs','date':'2026-11-09T09:00:04+01:00'}]
    groups=[{'ids':[1],'contact':'aicha','uncertain':True},{'ids':[2],'contact':'omar'},{'ids':[3],'contact':'aicha'}]
    result,_=refine_pending_plan(groups,rows,[])
    assert result[0]['ids']==[1,3] and len(result)==2


def test_followup_to_created_order_is_flagged_without_creating_duplicate():
    rows=[{'id':1,'text':'20 sacs CPJ45','date':'2026-11-09T09:00:00+01:00'},
          {'id':3,'text':'50 trs','date':'2026-11-09T09:00:04+01:00'}]
    groups=[{'ids':[1],'contact':'aicha'},{'ids':[3],'contact':'aicha'}]
    receipts=[{'message_ids':[1],'status':'created','number':'TEST1'}]
    result,kept=refine_pending_plan(groups,rows,receipts)
    assert len(result)==2 and result[1]['uncertain']
    assert 'TEST1' in result[1]['reason'] and kept==receipts
