from repair_history import validate


def reference():
    return {'2026ARC1':[{'BPCORD_0':'C01401','ITMREF_0':'CPJ45','ITMDES1_0':'Ciment CPJ45','QTY_0':20}]},{'C01401':{'BPCNAM_0':'CLIENT TEST'}}


def test_historical_reference_requires_original_client_and_goods_evidence():
    candidates,customers=reference()
    answer={'ob_number':'2026ARC1','client_evidence':'C01401','goods':[{'code':'CPJ45','source_quantity':20,'factor':1,'quote':'20 sacs CPJ45'}]}
    assert validate(answer,candidates,'C01401\n20 sacs CPJ45',customers)[0]
    assert not validate(answer,candidates,'C09999\n20 sacs CPJ45',customers)[0]
    answer['goods'][0]['quote']='20 kg RAB12'
    assert not validate(answer,candidates,'C01401\n20 kg RAB12',customers)[0]


def test_model_cannot_copy_an_ob_quantity_absent_from_source_quote():
    candidates,customers=reference()
    answer={'ob_number':'2026ARC1','client_evidence':'C01401','goods':[{'code':'CPJ45','source_quantity':20,'factor':1,'quote':'10 sacs CPJ45'}]}
    assert not validate(answer,candidates,'C01401\n10 sacs CPJ45',customers)[0]


def test_absent_customer_needs_three_source_goods_and_unique_ob_pattern():
    rows=[{'BPCORD_0':'C01401','ITMREF_0':code,'ITMDES1_0':code,'QTY_0':q} for code,q in [('RAB8',1000),('RAB10',2000),('RAB12',3000)]]
    candidates={'A':rows};customers={'C01401':{'BPCNAM_0':'CLIENT'}}
    answer={'ob_number':'A','client_evidence':'','goods':[{'code':r['ITMREF_0'],'source_quantity':r['QTY_0'],'factor':1,'quote':str(r['QTY_0'])+' kg '+r['ITMREF_0']} for r in rows]}
    source='\n'.join(g['quote'] for g in answer['goods'])
    assert validate(answer,candidates,source,customers)[0]
    assert not validate(answer,{'A':rows,'B':rows},source,customers)[0]


def test_document_layout_keeps_quantities_on_their_own_rows():
    from read_documents_layout import rows
    words=[{'text':'CPJ45','x':1,'y':1,'width':20,'height':10},
           {'text':'20','x':60,'y':2,'width':10,'height':10},
           {'text':'RAB12','x':1,'y':25,'width':20,'height':10},
           {'text':'1000','x':60,'y':25,'width':20,'height':10}]
    assert rows(words)=='CPJ45 | 20\nRAB12 | 1000'


def test_table_separators_do_not_break_a_verified_article_phrase():
    import learning_memory as memory
    token=memory.ACTIVE.set(({'kind':'article_alias','rule_key':memory.key('BITU FLEX 3MM ARD GRIS'),'payload':{'code':'BTF_3MM_AGR'}},))
    try:
        rows=[{'BPCORD_0':'C01401','ITMREF_0':'BTF_3MM_AGR','ITMDES1_0':'Membrane','QTY_0':35}]
        quote='BITU | FLEX | 3MM | ARD | GRIS | R | 35 | 428,00'
        answer={'ob_number':'A','client_evidence':'C01401','goods':[{'code':'BTF_3MM_AGR','source_quantity':35,'factor':1,'quote':quote}]}
        assert validate(answer,{'A':rows},'C01401\n'+quote,{'C01401':{'BPCNAM_0':'CLIENT'}})[0]
        answer['goods'][0]['source_quantity']=99
        assert not validate(answer,{'A':rows},'C01401\n'+quote,{'C01401':{'BPCNAM_0':'CLIENT'}})[0]
    finally:memory.ACTIVE.reset(token)


def test_unique_ice_can_prove_customer_without_reusing_candidate_name():
    candidates,customers=reference();customers['C01401']['XICE_0']='001234567890123'
    answer={'ob_number':'2026ARC1','client_evidence':'ICE 001234567890123','goods':[{'code':'CPJ45','source_quantity':20,'factor':1,'quote':'20 sacs CPJ45'}]}
    source='ICE 001234567890123\n20 sacs CPJ45'
    assert validate(answer,candidates,source,customers)[0]
    customers['C99999']={'BPCNAM_0':'AUTRE CLIENT','XICE_0':'001234567890123'}
    assert not validate(answer,candidates,source,customers)[0]


def test_arabic_source_quotes_preserve_letters_and_meaning():
    from repair_history import quote_in
    assert quote_in('سيمة 45','طلب: 20 كيس سيمة 45')
    assert not quote_in('حديد 2045','سيمة 2045')
    candidates,customers=reference()
    answer={'ob_number':'2026ARC1','client_evidence':'C01401','goods':[{'code':'CPJ45','source_quantity':20,'factor':1,'quote':'20 كيس سيمة 45'}]}
    assert validate(answer,candidates,'C01401\n20 كيس سيمة 45',customers)[0]
