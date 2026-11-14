from prepare import normalize_sale_price

def test_board_piece_to_linear_metre_conversion_keeps_independent_price_basis():
    import learning_memory as memory
    from understanding import normalize_quantity
    from prepare import apply_madrier_caption_quantities
    token=memory.ACTIVE.set(({'kind':'policy','rule_key':'verified_unit_equivalences',
                              'payload':{'value':[{'article':'P_MD3','from':'piece','to':'ML','factor':3}]}},))
    try:
        draft={'lines':[{'article':'P_MD3','quantity':120,'unit':'ML','price':35,'price_unit':'PIECE'}]}
        apply_madrier_caption_quantities(draft,'40 madrier 3m 35dh')
        line=draft['lines'][0];article={'ITMREF_0':'P_MD3','SAU_0':'ML'}
        normalize_quantity(line,article);normalize_sale_price(line,article)
        assert line['quantity']==120 and line['unit']=='ML' and line['price']==35
        explicit={'price':105,'price_unit':'PIECE'};normalize_sale_price(explicit,article)
        assert explicit['price']==35
    finally:memory.ACTIVE.reset(token)

def test_verified_five_litre_containers_convert_both_explicit_quantity_and_price():
    import learning_memory as memory
    from understanding import normalize_quantity
    token=memory.ACTIVE.set(({'kind':'policy','rule_key':'verified_unit_equivalences','payload':{'value':[{'article':'SIK_5L','from':'bidon','to':'L','factor':5}]}},))
    try:
        r={'quantity':6,'unit':'bidon','price':290.004,'price_unit':'bidon'};article={'ITMREF_0':'SIK_5L','SAU_0':'L'}
        normalize_quantity(r,article);normalize_sale_price(r,article)
        assert r['quantity']==30 and r['unit']=='L' and r['price']==58.0008
        other={'quantity':6,'unit':'bidon'};normalize_quantity(other,{'ITMREF_0':'OTHER','SAU_0':'L'})
        assert other['unit']=='bidon'
    finally:memory.ACTIVE.reset(token)


def test_explicit_tonne_price_converts_to_bag_price_independently_of_qty():
    line={'quantity':240,'price':1640.004,'price_unit':'tonne'}
    normalize_sale_price(line,{'ITMREF_0':'CPJ45','SAU_0':'SAC'})
    assert line['price']==82.0002 and line['quantity']==240


def test_steel_price_per_tonne_is_not_left_as_price_per_kg():
    line={'price':9200,'price_unit':'t'}
    normalize_sale_price(line,{'ITMREF_0':'RAB14','SAU_0':'KG'})
    assert line['price']==9.2


def test_unspecified_price_basis_keeps_requested_cement_price():
    line={'price':78}
    normalize_sale_price(line,{'ITMREF_0':'CPJ45','SAU_0':'SAC'})
    assert line=={'price':78}


def test_unsupported_price_conversion_requires_clarification():
    line={'price':50,'price_unit':'litre'}
    normalize_sale_price(line,{'ITMREF_0':'OTHER','SAU_0':'KG'})
    assert line['price']==50 and line['price_unit_unresolved']
