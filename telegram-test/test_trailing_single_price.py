from prepare import apply_single_item_trailing_price


def test_isolated_price_belongs_to_single_item_not_phantom_article():
    draft={'lines':[{'article':'POWER ENDUIT P104','quantity':40,'price':None},
                    {'article':None,'quantity':None,'price':95}]}
    apply_single_item_trailing_price(draft,'B&b\n40 sac power enduit p104\n95')
    assert len(draft['lines'])==1 and draft['lines'][0]['price']==95
    other={'lines':[{'article':'CPJ45','quantity':40,'price':None},{'article':'CPJ35','quantity':20,'price':None}]}
    apply_single_item_trailing_price(other,'B&b\n40 sac cpj45\n20 sac cpj35\n95')
    assert all(x['price'] is None for x in other['lines'])
