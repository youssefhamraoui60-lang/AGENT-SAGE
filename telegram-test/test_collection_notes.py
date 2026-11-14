from prepare import apply_collection_note, unassigned_currency_amounts


TEXT='Baya salah\n4t cpj 45\n1t cpj 35\n11 rlx afriflex 40py ard\nLe chauffeur doit récupérer le règlement\n481 dh'


def test_collection_is_not_an_item_or_price():
    draft={'lines':[{'article':'CPJ45','quantity':80,'price':78.5},
                    {'article':None,'quantity':None,'price':481},
                    {'article':'AFR_40PY_G','quantity':11,'price':481}], 'delivery_note':None}
    apply_collection_note(draft,TEXT)
    assert len(draft['lines'])==2
    assert draft['lines'][1]['price'] is None
    assert '481 DH' in draft['delivery_note']
    assert unassigned_currency_amounts(draft,TEXT)==[]


def test_bare_amount_without_collection_instruction_still_needs_assignment():
    draft={'lines':[{'article':'CPJ45','quantity':80,'price':78.5}]}
    apply_collection_note(draft,'80 sacs CPJ45\n481 dh')
    assert unassigned_currency_amounts(draft,'80 sacs CPJ45\n481 dh')==['481']


def test_explicit_price_and_same_collection_amount_are_not_discarded():
    draft={'lines':[{'article':'AFR_40PY_G','quantity':11,'price':481}], 'delivery_note':None}
    apply_collection_note(draft,'11 rouleaux à 481 dh\nLe chauffeur doit récupérer le règlement\n481 dh')
    assert draft['lines'][0]['price']==481
