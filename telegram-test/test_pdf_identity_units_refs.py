from decimal import Decimal
from telegram_batch import document_references
from understanding import normalize_quantity
from prepare import document_ices,document_issuer_names,document_tax_rates


def test_verified_document_resolution_never_applies_to_changed_quantities():
    import hashlib
    import learning_memory
    from prepare import apply_confirmed_source
    body='BON 403/2026 108 MADRILLE 3'
    token=learning_memory.ACTIVE.set([{'kind':'interpretation','rule_key':'source_draft_test',
        'payload':{'document_text_hash':hashlib.sha256(body.casefold().encode()).hexdigest(),'client':'C10614'}}])
    try:
        draft={'client':None}
        apply_confirmed_source(draft,'DOCUMENT JOINT :\n'+body)
        assert draft['client']=='C10614'
        draft={'client':None}
        apply_confirmed_source(draft,'DOCUMENT JOINT :\n'+body.replace('108','109'))
        assert draft['client'] is None
    finally:learning_memory.ACTIVE.reset(token)


def test_one_number_with_year_is_one_document():
    assert document_references('Bon de Commande N°: 403/2026')=={'403'}
    assert document_references('BON DE COMMANDE N° :1011-1/2026')=={'1011-1'}
    assert document_references('Bon de commande NO BC7792-26')=={'BC7792-26'}


def test_generic_units_take_sage_unit_but_tonnes_are_converted():
    article={'ITMREF_0':'CPJ45','SAU_0':'SAC'}
    line={'quantity':150,'unit':'Unités'}
    normalize_quantity(line,article)
    assert line['quantity']==150 and line['unit']=='SAC'
    line={'quantity':8,'unit':'T'}
    normalize_quantity(line,article)
    assert line['quantity']==160 and line['unit']=='SAC'


def test_corporate_suffix_and_ice_label_are_recognized():
    text='DOCUMENT JOINT :\nPROBATRA | SARL\nBON DE COMMANDE N°1011-1/2026\nIDENTIFIANT | COMMUN : | 000516399000007'
    assert document_ices(text)=={'000516399000007'}
    assert 'PROBATRA' in document_issuer_names(text)


def test_explicit_exempt_transport_is_never_silently_taxed():
    assert Decimal(0) in document_tax_rates('DOCUMENT JOINT :\ntransport Exonere de TVA ACHATS')
