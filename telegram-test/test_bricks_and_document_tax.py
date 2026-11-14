from decimal import Decimal
import learning_memory
from prepare import canonical_article, document_tax_rates
from understanding import normalize_quantity


def test_plural_brique_zero_seven_and_unit_preserve_quantity():
    token=learning_memory.ACTIVE.set(())
    try:
        assert canonical_article('briques rouge 07')=='BQ7'
        line={'article':'BQ7','quantity':13400,'unit':'unités'}
        normalize_quantity(line,{'ITMREF_0':'BQ7','SAU_0':'UN'})
        assert line['quantity']==13400 and line['unit']=='UN'
    finally:learning_memory.ACTIVE.reset(token)


def test_mixed_vat_table_is_not_silently_forced_to_twenty_percent():
    text='DOCUMENT JOINT :\nTaux | Base HT | Montant TVA | Total HT\n20,00 | 34650,00 | 6930,00\n12,00 | 625,00 | 75,00'
    assert document_tax_rates(text)=={Decimal(20),Decimal(12)}
    assert document_tax_rates(text+'\nNet à payer\n42 | 280,00 | MAD')=={Decimal(20),Decimal(12)}
    assert document_tax_rates('DOCUMENT JOINT :\nRemise 5%\nTVA 20%')=={Decimal(20)}
    assert document_tax_rates('Remise 5%')==set()
