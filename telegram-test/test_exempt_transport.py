import pytest
from prepare import normalize_sale_price,exempt_transport_document
import creation


def test_generic_price_unit_uses_sage_unit_without_changing_price():
    line={'price':82,'price_unit':'Unités'}
    normalize_sale_price(line,{'ITMREF_0':'CPJ45','SAU_0':'SAC'})
    assert line['price']==82 and line['price_unit']=='SAC'
    assert not line.get('price_unit_unresolved')


def test_exemption_requires_explicit_transport_line():
    assert exempt_transport_document('DOCUMENT JOINT :\nfrais de transport | 500 | Exonere de TVA')
    assert not exempt_transport_document('DOCUMENT JOINT :\nciment exonéré de TVA\ntransport 500')
    assert not exempt_transport_document('transport exonéré de TVA')


def test_payload_rejects_unverified_exemption_or_exempt_goods():
    from datetime import date
    details={'client':{'BPCNUM_0':'C07230','CUR_0':'MAD'},'missing':[],
        'delivery':'2026-11-10','lines':[{'article':'CPJ45','quantity':150,'price':82,'tax_code':'T00','tax_source':'document_transport_exempt'}]}
    with pytest.raises(creation.CreationError,match='Exonération'):
        creation.build_payload(details,reference_date=date(2026,11,10))
    details['lines'][0].update(article='MANTD',quantity=1,price=500,tax_source='unknown')
    with pytest.raises(creation.CreationError,match='Exonération'):
        creation.build_payload(details,reference_date=date(2026,11,10))
    details['lines'][0]['tax_source']='document_transport_exempt'
    assert creation.build_payload(details,reference_date=date(2026,11,10))['lines'][0]['tax_code']=='T00'
