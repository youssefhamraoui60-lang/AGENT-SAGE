import asyncio
from telegram_batch import OrderBatches, contact_name,client_scoped_history
from prepare import apply_service_amounts


def test_disabled_aggregation_dispatches_each_message_with_isolated_history_key():
    async def run():
        received = []
        async def process(key, messages):
            received.append((key, messages))
        batches = OrderBatches(process, delay=90, aggregate=False)
        batches.add(1, 2, 100, 'Contact : Aicha\n1 VYS CPJ35')
        batches.add(1, 2, 101, 'Contact : Aicha\nTransport 50')
        await batches.close()
        assert [messages for _, messages in received] == [
            [(100, 'Contact : Aicha\n1 VYS CPJ35')],
            [(101, 'Contact : Aicha\nTransport 50')]]
        assert received[0][0] != received[1][0]
        assert not batches.pending
    asyncio.run(run())

def test_cement_trip_abbreviations_keep_distinct_buyers_separate():
    from telegram_batch import named_customer,has_goods_request,separate_complete_requests
    first='Contact : Aicha\nClient Alpha\n1 VYS CPJ35'
    second='Contact : Aicha\nClient Beta\n2 VGS CPJ45'
    assert has_goods_request(first) and has_goods_request(second)
    assert named_customer(first)=='clientalpha'
    assert named_customer(second)=='clientbeta'
    assert separate_complete_requests(first,second)


def test_same_commercial_messages_form_one_order_and_do_not_mix_contacts():
    async def run():
        received = []

        async def process(key, messages):
            received.append((key, messages))

        batches = OrderBatches(process, delay=.02)
        batches.add(1, 1, 100, 'Contact : Aicha Khayr\n60 sacs ciment 45 Dior guisse')
        batches.add(1, 1, 101, 'Contact : Aicha Khayr\nTrs = 50 dh\nÀ côté kabaj Berrechid')
        batches.add(1, 1, 102, 'Contact : Rachida Mansali\nAutre commande')
        await asyncio.gather(*list(batches.tasks), return_exceptions=True)
        assert len(received) == 2
        aicha = next(messages for key, messages in received if key[2] == 'aichakhayr')
        assert [i for i, _ in aicha] == [100, 101]
        draft = {'lines': []}
        apply_service_amounts(draft, '\n\n'.join(text for _, text in aicha))
        assert draft['lines'] == [{'article': 'MANTD', 'quantity': 1, 'price': 50, 'unit': None}]
        await batches.close()

    asyncio.run(run())


def test_contact_name_normalization():
    assert contact_name('Contact : Aïcha Khayr\nNuméro : 123') == 'aichakhayr'


def test_separate_document_and_complete_text_order_both_directions():
    async def run():
        for reverse in [False,True]:
            received=[]
            async def process(key,messages):received.append([i for i,_ in messages])
            batches=OrderBatches(process,delay=.01)
            doc='Contact : Reda\nDOCUMENT JOINT :\nBON DE COMMANDE N°021795\nPRESTIGE ACIER'
            text='Contact : Reda\n8t rab25\n3t rab32\n50 treillis soudé 3.5*5\n1800 frais de transport\nSTC'
            items=[doc,text] if not reverse else [text,doc]
            for i,item in enumerate(items):batches.add(1,1,10+i,item)
            await asyncio.gather(*list(batches.tasks),return_exceptions=True)
            assert received==[[10],[11]]
            assert client_scoped_history([{'role':'user','content':items[0]}],items[1])==[]
            await batches.close()
    asyncio.run(run())


def test_wiam_two_clients_are_dispatched_as_two_orders():
    async def run():
        received=[]
        async def process(key,messages):received.append(messages)
        batches=OrderBatches(process,delay=.01)
        batches.add(1,1,328,'Contact : Wiam El Harti\nC10121\n20 sacs power fix blanc\n30 sacs ciment 35\n10 sacs ciment45\n50 transport')
        batches.add(1,1,329,'Contact : Wiam El Harti\nC09328\nSolo brique rouge7\n200 transport')
        await asyncio.gather(*list(batches.tasks),return_exceptions=True)
        assert [[mid for mid,_ in m] for m in received]==[[328],[329]]
        assert '200 transport' not in received[0][0][1]
        await batches.close()
    asyncio.run(run())


def test_next_client_does_not_inherit_an_unfinished_order():
    old=[{'role':'user','content':'C10121 : 20 sacs CPJ45'},{'role':'assistant','content':'Manque : prix.'}]
    assert client_scoped_history(old,'C09328 : solo brique rouge7')==[]
    assert client_scoped_history(old,'50 trs') is old
    assert client_scoped_history(old,'C10121 : livraison demain') is old


def test_missing_client_then_client_code_is_one_order():
    old=[{'role':'user','content':'6 fardou12\n4 fardou14'}]
    assert client_scoped_history(old,'New yo buildings C09802') is old


def test_two_pdf_bons_and_followup_are_three_independent_batches():
    async def run():
        received=[]
        async def process(key,messages):received.append([mid for mid,_ in messages])
        batches=OrderBatches(process,delay=.01)
        caption='Contact : Siham Elhafidi\nDOCUMENT JOINT :\nBON | DE | COMMANDE | N°'
        batches.add(1,1,385,caption+'3109- JR - 2026')
        batches.add(1,1,386,caption+'3108- JR - 2026')
        batches.add(1,1,389,'Contact : Siham Elhafidi\nRelance pour cpj Small palace..')
        await asyncio.gather(*list(batches.tasks),return_exceptions=True)
        assert received==[[385],[386],[389]]
        await batches.close()
    asyncio.run(run())


def test_distinct_pdf_and_followup_do_not_reuse_previous_history():
    old=[{'role':'user','content':'DOCUMENT JOINT :\nBON DE COMMANDE N°3109'}]
    assert client_scoped_history(old,'DOCUMENT JOINT :\nBON DE COMMANDE N°3108')==[]
    assert client_scoped_history(old,'Relance pour cpj Small palace')==[]


def test_named_second_customer_without_code_is_not_merged_into_first():
    async def run():
        received=[]
        async def process(key,messages):received.append([mid for mid,_ in messages])
        batches=OrderBatches(process,delay=.01)
        first='Contact : Aicha Khayr\nCharaia abdelmajid c10184\n30 sac cpj35 =79dh\n50 trs'
        second='Contact : Aicha Khayr\nIskane al mohute\n20 sac cpj35\n10 sac cpj45\n50 trs'
        batches.add(1,1,401,first)
        batches.add(1,1,403,second)
        await asyncio.gather(*list(batches.tasks),return_exceptions=True)
        assert received==[[401],[403]]
        assert client_scoped_history([{'role':'user','content':first}],second)==[]
        assert client_scoped_history([{'role':'user','content':first}],'Trs =50 dh')
        await batches.close()
    asyncio.run(run())


def test_phone_only_delivery_complement_is_not_a_new_customer():
    from telegram_batch import named_customer
    assert named_customer('Contact : Aicha\nBarre droite\n0661788236') is None
