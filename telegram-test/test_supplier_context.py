import learning_memory as memory
from prepare import apply_confirmed_source, source_body_key, article_supplier, annotate_supplier_context


BODY = 'BH4C\n11t 35perfecto\n2t cpj 45\nLafarge\n2mars\n300DH'


def test_confirmed_source_removes_false_line_without_changing_new_requests():
    lines = [{'article': 'CPJ35P', 'quantity': 11, 'unit': 'tonne', 'price': None},
             {'article': 'CPJ45', 'quantity': 2, 'unit': 'tonne', 'price': None},
             {'article': 'MANTD', 'quantity': 1, 'unit': None, 'price': 300}]
    rule = {'kind': 'interpretation', 'rule_key': 'source_draft_test',
            'payload': {'source_body_key': source_body_key(BODY), 'lines': lines,
                        'delivery': None, 'delivery_note': '2 Mars'}}
    token = memory.ACTIVE.set((rule,))
    try:
        draft = {'lines': [{'article': None, 'quantity': None}]}
        apply_confirmed_source(draft, 'Contact : Othmane\nNumero : 123\n' + BODY)
        assert len(draft['lines']) == 3
        assert draft['delivery'] is None
        draft['lines'][0]['quantity'] = 220
        assert lines[0]['quantity'] == 11  # independent of later unit conversion
        other = {'lines': []}
        apply_confirmed_source(other, BODY.replace('11t', '12t'))
        assert other == {'lines': []}
        apply_confirmed_source(other, BODY + '\nمادة إضافية')
        assert other == {'lines': []}
    finally:
        memory.ACTIVE.reset(token)


def test_cement_supplier_never_applies_to_transport_or_steel():
    token = memory.ACTIVE.set(({'kind': 'policy', 'rule_key': 'cement_supplier_phrases',
                               'payload': {'value': {'Lafarge': 'F008'}}},))
    try:
        assert article_supplier(BODY, 'CPJ35P') == 'F008'
        assert article_supplier(BODY, 'CPJ45') == 'F008'
        assert article_supplier(BODY, 'MANTD') is None
        assert article_supplier(BODY, 'RAB12') is None
        assert article_supplier('Client Lafarge', 'CPJ45') is None
    finally:
        memory.ACTIVE.reset(token)


def test_supplier_annotation_preserves_product_and_bare_amount():
    token = memory.ACTIVE.set(({'kind': 'policy', 'rule_key': 'cement_supplier_phrases',
                               'payload': {'value': {'Novacim': 'F889'}}},))
    try:
        text = 'Londra immo\n210 sac Cpj 35\nNovacim\n200dh'
        annotated = annotate_supplier_context(text)
        assert annotated == 'Londra immo\n210 sac Cpj 35\nFournisseur (pas un article) : Novacim\n200dh'
        # An unknown bare amount is not automatically interpreted as transport.
        assert annotate_supplier_context('Autre client\n200dh') == 'Autre client\n200dh'
        assert article_supplier(text, 'CPJ35') == 'F889'
        assert article_supplier(text, 'MANTD') is None
    finally:
        memory.ACTIVE.reset(token)


def test_inline_brand_preserves_the_goods_line():
    token=memory.ACTIVE.set(({'kind':'policy','rule_key':'cement_supplier_phrases','payload':{'value':{'Lafarge':'F008'}}},))
    try:
        text='Travemac voyage cima 45 Lafarge casa'
        assert article_supplier(text,'CPJ45')=='F008'
        assert annotate_supplier_context(text).splitlines()[0]==text
        assert 'Fournisseur du ciment indiqué : Lafarge' in annotate_supplier_context(text)
        assert article_supplier('Travemac CPJ45 sans Lafarge','CPJ45') is None
    finally:memory.ACTIVE.reset(token)


def test_supplier_with_delivery_on_same_line_and_client_name_safety():
    rules = ({'kind': 'policy', 'rule_key': 'cement_supplier_phrases',
              'payload': {'value': {'Holcim': 'F008', 'Novacim': 'F889'}}},
             {'kind': 'policy', 'rule_key': 'supplier_delivery_qualifiers',
              'payload': {'value': ['benne']}})
    token = memory.ACTIVE.set(rules)
    try:
        text = 'Bouterfa Ahmed\n120 perfecto\n400 ciment 45\nHolcim benne Benslimane'
        assert article_supplier(text, 'CPJ35P') == 'F008'
        assert article_supplier(text, 'CPJ45') == 'F008'
        assert article_supplier(text, 'MANTD') is None
        assert article_supplier('Client Holcim\n400 CPJ45', 'CPJ45') is None
        assert article_supplier('Holcim promotion\n400 CPJ45', 'CPJ45') is None
        assert article_supplier('Holcimex benne Benslimane', 'CPJ45') is None
        assert 'Fournisseur (pas un article) : Holcim benne Benslimane' in annotate_supplier_context(text)
    finally:
        memory.ACTIVE.reset(token)
