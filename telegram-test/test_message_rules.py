from prepare import apply_service_amounts, canonical_article,apply_shared_steel_price
from prepare import remove_standalone_brand_notes
from prepare import unassigned_currency_amounts


def test_two_explicit_prices_cannot_be_ignored_by_zero_price_fallback():
    import learning_memory
    token=learning_memory.ACTIVE.set(())
    try:
        draft={'lines':[{'article':'RABT6','quantity':1000,'price':None},
                        {'article':'RAB10','quantity':1000,'price':None}]}
        assert unassigned_currency_amounts(draft,'Prix = 940 dh + 960 dh')==['940 + 960']
    finally:learning_memory.ACTIVE.reset(token)


def test_explicit_separate_article_prices_are_not_a_bare_price_pair():
    draft={'lines':[{'article':'RABT6','quantity':1000,'price':9.6},
                    {'article':'RAB10','quantity':1000,'price':9.4}]}
    assert unassigned_currency_amounts(draft,'Prix RAB6 = 960 dh + RAB10 = 940 dh')==[]


def test_unallocated_currency_line_cannot_be_silently_omitted():
    draft={'lines':[{'article':'CPJ45','quantity':40,'price':79}]}
    assert unassigned_currency_amounts(draft,'40 sacs CPJ45\n300DH')==['300']
    draft['lines'].append({'article':'MANTD','quantity':1,'price':300})
    assert unassigned_currency_amounts(draft,'40 sacs CPJ45\n300DH')==[]


def test_quoted_original_order_in_modification_does_not_double_transport():
    draft={'lines':[{'article':'MANTD','quantity':1,'price':50},{'article':'MANTD','quantity':1,'price':50}]}
    text='20 sacs CPJ45\n50 transport\nModification au niveau de cette commande :\n(20 sacs CPJ45\n50 transport\nBerrechid)\nPlus 40 sacs CPJ45'
    apply_service_amounts(draft,text)
    assert draft['lines']==[{'article':'MANTD','quantity':1,'price':50,'unit':None}]


def test_two_explicit_services_of_same_price_are_preserved():
    draft={'lines':[]}
    apply_service_amounts(draft,'50 trs\n50 manutention')
    assert len(draft['lines'])==2


def test_explicit_unit_price_and_total_are_already_allocated():
    draft={'lines':[{'article':'CPJ45','quantity':20,'price':81}]}
    assert unassigned_currency_amounts(draft,'81 DH\n1 620 MAD')==[]


def test_standalone_brand_without_quantity_is_not_an_extra_article():
    goods={'article':'RAB12','quantity':2000,'price':None}
    draft={'lines':[goods,{'article':'Sounacid','quantity':None,'price':None}]}
    remove_standalone_brand_notes(draft,'2000 kg RAB12\n*Sounacid*')
    assert draft['lines']==[goods]


def test_explicit_quantity_or_price_is_not_discarded_as_brand_note():
    lines=[{'article':'Cimat','quantity':20,'price':None},{'article':'Sonasid','quantity':None,'price':9.2}]
    draft={'lines':list(lines)}
    remove_standalone_brand_notes(draft,'Cimat\nSonasid')
    assert draft['lines']==lines


def test_transport_and_manutention_are_amounts_with_quantity_one():
    draft = {'lines': [{'article': 'TRS', 'quantity': 50, 'price': None}]}
    apply_service_amounts(draft, '50 trs\n25,5 manutention')
    assert draft['lines'] == [
        {'article': 'MANTD', 'quantity': 1, 'price': 50, 'unit': None},
        {'article': 'MANTD', 'quantity': 1, 'price': 25.5, 'unit': None},
    ]


def test_no_unrequested_manutention_or_service_from_product_line():
    draft = {'lines': []}
    apply_service_amounts(draft, '80 sac cpj 45\n5 kg pointe 6')
    assert draft['lines'] == []


def test_trc_alias_and_zero_amount():
    draft = {'lines': []}
    apply_service_amounts(draft, '0 trc')
    assert draft['lines'][0] == {'article': 'MANTD', 'quantity': 1, 'price': 0, 'unit': None}


def test_transport_already_extracted_as_mantd_is_not_charged_twice():
    draft={'lines':[{'article':'MANTD','quantity':1,'price':100,'unit':'UN'}]}
    apply_service_amounts(draft,'Trs = 100 dh')
    assert draft['lines']==[{'article':'MANTD','quantity':1,'price':100,'unit':None}]


def test_isolated_steel_price_is_not_replaced_by_zero_or_history():
    draft={'lines':[{'article':'RAB16','price':None},{'article':'RABT6','price':None},{'article':'CPJ45','price':None},{'article':'RAB12','price':10}]}
    apply_shared_steel_price(draft,'600kg rab 16\n500kg rab 6\n9.20\nSonasid')
    assert [r['price'] for r in draft['lines']]==[9.2,9.2,None,10]


def test_user_confirmed_pointe_references():
    for name in ['pointe 6', 'pointes 06', 'pointe de paris 6']:
        assert canonical_article(name) == 'PF-TP16X20'
    for name in ['PP6', 'PP 6', 'PP06']:
        assert canonical_article(name) == 'PP06'
    assert canonical_article('pointe 8') == 'PF-TP08X20'
    for name in ['PP8', 'PP08']:
        assert canonical_article(name) == 'PP08'
    assert canonical_article('pointe 16') == 'pointe 16'
