from confirmed_groups import apply, fingerprint, reference_lines


def fixture():
    rows=[{'ITMREF_0':'RAB12','QTY_0':12000,'NETPRIATI_0':9.1,'BPCORD_0':'C09802'}]
    source={1:{'text':'6 fardou 12','date':'2026-11-02T08:43:30+01:00'},2:{'text':'client C09802','date':'2026-11-02T08:44:17+01:00'}}
    rule={'kind':'interpretation','rule_key':'confirmed_source_group_1_2','payload':{
        'message_ids':[1,2],'ob_number':'OB1','client':'C09802','contact':'Aicha',
        'source_sha256':fingerprint([source[i]['text'] for i in [1,2]]),
        'reference_sha256':fingerprint(reference_lines(rows))}}
    outcomes=[{'message_ids':[1],'status':'unresolved'},{'message_ids':[2],'status':'unresolved'}]
    return rule,{'OB1':rows},source,outcomes


def test_confirmed_group_covers_exact_sources_once():
    rule,orders,source,outcomes=fixture();links={}
    apply([rule],orders,source,links,outcomes)
    assert len(outcomes)==1 and outcomes[0]['message_ids']==[1,2]
    assert links['OB1']['message_ids']==[1,2]


def test_changed_source_or_reference_cannot_reuse_confirmation():
    for change_source in [True,False]:
        rule,orders,source,outcomes=fixture();links={}
        if change_source:source[1]['text']='3 fardou 12'
        else:orders['OB1'][0]['QTY_0']=6000
        apply([rule],orders,source,links,outcomes)
        assert not links and len(outcomes)==2
