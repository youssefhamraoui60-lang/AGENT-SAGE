import learning_memory as memory
from prepare import apply_ordinary_steel_context, article_supplier


def test_ordinary_steel_category_and_balance_price_are_not_extra_item_or_supplier():
    token=memory.ACTIVE.set(({'kind':'policy','rule_key':'ordinary_steel_phrases',
                              'payload':{'value':['Hdid 3adi','Hdide 3adi','Hdude 3adi']}},
                             {'kind':'policy','rule_key':'steel_supplier_phrases','payload':{'value':{}}}))
    try:
        draft={'lines':[{'article':'14','quantity':1200,'unit':'KG','price':None},
                        {'article':'RAB10','quantity':1000,'unit':'KG','price':None},
                        {'article':'Hdid 3adi','quantity':None,'unit':None,'price':9.2}]}
        text='1200 kg 14\n1000 kg 10\nHdid 3adi balance 9.20'
        apply_ordinary_steel_context(draft,text)
        assert [(l['article'],l['quantity'],l['price']) for l in draft['lines']]==[('RAB14',1200,9.2),('RAB10',1000,9.2)]
        assert article_supplier(text,'RAB14') is None
    finally:
        memory.ACTIVE.reset(token)


def test_numeric_article_is_not_assumed_steel_without_category():
    token=memory.ACTIVE.set(())
    try:
        draft={'lines':[{'article':'14','quantity':1200,'price':None}]}
        apply_ordinary_steel_context(draft,'1200 kg 14')
        assert draft['lines'][0]['article']=='14'
    finally:
        memory.ACTIVE.reset(token)
