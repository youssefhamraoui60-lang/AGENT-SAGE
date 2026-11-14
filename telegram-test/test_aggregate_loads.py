from prepare import apply_explicit_aggregate_load


def test_sea_sand_voyage_price_is_per_load_not_per_cubic_metre():
    draft={'lines':[{'article':'sable de mer souiria','quantity':30,'price':10500,'unit':'m'}]}
    apply_explicit_aggregate_load(draft,'V sable de mer souiria 30m = 10500 dh')
    assert draft['lines']==[{'article':'SABM_30M3','quantity':1,'unit':'voyage','price':10500}]


def test_washed_sand_keeps_other_goods_and_explicit_amount():
    cement={'article':'CPJ45','quantity':20,'price':81,'unit':'SAC'}
    draft={'lines':[cement,{'article':'sable lavé','quantity':30,'unit':'m3','price':6500}]}
    apply_explicit_aggregate_load(draft,'1 voyage sable lavé 30 m 6500 dh berrechid')
    assert draft['lines']==[cement,{'article':'SABL_30M3','quantity':1,'unit':'voyage','price':6500}]


def test_unstated_or_different_volume_is_not_assumed_thirty():
    for source in ['V sable de mer = 10500 dh','V sable de mer 17m = 7000 dh','2 voyages sable lavé 30m = 10000 dh']:
        draft={'lines':[]}
        apply_explicit_aggregate_load(draft,source)
        assert draft['lines']==[]


def test_multiple_loads_of_same_family_need_individual_resolution():
    draft={'lines':[]}
    apply_explicit_aggregate_load(draft,'V sable de mer 30m = 10000 dh\nV sable de mer 30m = 11000 dh')
    assert draft['lines']==[]
