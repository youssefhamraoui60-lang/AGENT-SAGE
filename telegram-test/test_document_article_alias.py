import learning_memory
from prepare import document_article_alias


def test_fil_de_fer_confirmation_is_limited_to_majasi_bon402():
    token=learning_memory.ACTIVE.set(({'kind':'policy','rule_key':'document_article_aliases',
        'payload':{'value':[{'client':'C10614','reference':'402/2026','aliases':{'fildefer':'PF-FR130'}}]}},))
    try:
        assert document_article_alias('FIL DE FER','C10614','Bon de commande 402/2026')=='PF-FR130'
        assert document_article_alias('FIL DE FER','C10614','Bon de commande 402 / 2026')=='PF-FR130'
        assert document_article_alias('FIL DE FER','C99999','Bon de commande 402/2026') is None
        assert document_article_alias('FIL DE FER','C10614','Bon de commande 403/2026') is None
        assert document_article_alias('FIL DE FER','C10614','Bon de commande 1402/2026') is None
    finally:
        learning_memory.ACTIVE.reset(token)


def test_conflicting_document_alias_does_not_choose_silently():
    rules=[{'client':'C10614','reference':'402/2026','aliases':{'fildefer':code}} for code in ['PF-FR130','OTHER']]
    token=learning_memory.ACTIVE.set(({'kind':'policy','rule_key':'document_article_aliases','payload':{'value':rules}},))
    try:
        assert document_article_alias('FIL DE FER','C10614','402/2026') is None
    finally:
        learning_memory.ACTIVE.reset(token)


def test_confirmed_total_does_not_override_other_customer_or_other_printed_amount():
    from decimal import Decimal
    from prepare import confirmed_document_total
    rule={'client':'C10614','reference':'402/2026','printed_total':'0','confirmed_total':'41222.50'}
    token=learning_memory.ACTIVE.set(({'kind':'policy','rule_key':'confirmed_document_totals','payload':{'value':[rule]}},))
    try:
        assert confirmed_document_total('402/2026','C10614',Decimal(0))==Decimal('41222.50')
        assert confirmed_document_total('402/2026','C99999',Decimal(0))==0
        assert confirmed_document_total('403/2026','C10614',Decimal(0))==0
        assert confirmed_document_total('402/2026','C10614',Decimal('123'))==123
    finally:
        learning_memory.ACTIVE.reset(token)
