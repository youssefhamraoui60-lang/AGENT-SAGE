from message_intent import administrative_reply

def test_activation_and_payment_notes_do_not_ask_for_new_order_lines():
    assert 'activation' in administrative_reply('Contact : Siham\nPrière activer fer delta matériaux')
    assert 'chèques' in administrative_reply('Contact : Aicha\nBchiker hassan\nيجيبوا شيكات بقيمة 110000 درهم وشكرا')

def test_goods_and_document_orders_are_not_hidden_by_administrative_words():
    assert administrative_reply('Merci de créer 40 sacs CPJ35') is None
    assert administrative_reply('DOCUMENT JOINT :\nMerci') is None
    assert administrative_reply('Merci de grouper avec la cmd Mondial acier') is None
