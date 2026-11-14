import asyncio

from prepare import apply_steel_accessory_context, apply_service_location_note, canonical_article
from telegram_batch import OrderBatches, named_customer


def test_trip_customer_and_same_customer_new_delivery_are_separate():
    async def run():
        got=[]
        async def process(key,messages):got.append([i for i,_ in messages])
        b=OrderBatches(process,delay=.01)
        for i,text in [(759,'Contact : Rachida\nMourid mohamed\nV cpj45'),
                       (760,'Contact : Rachida\nBenlmaachi yassine\n4t cpj45\n100 trs'),
                       (772,'Contact : Youssef\n4000 kg rab12\nREVE MAT\nAdoz TRS100'),
                       (775,'Contact : Youssef\n1600 kg rab6\nBarre droit\nREVE MAT\nOmnia TRS300')]:
            b.add(1,1,i,text)
        await asyncio.gather(*list(b.tasks),return_exceptions=True)
        assert sorted(got)==[[759],[760],[772],[775]]
        await b.close()
    asyncio.run(run())
    assert named_customer('Mounzih el haj mohamed\nUn Voyage Cpj35\nPour le jeudi')=='mounzihelhajmohamed'


def test_steel_accessories_do_not_resolve_to_unrelated_catalog_items():
    d={'lines':[{'article':'rab12','quantity':1000,'unit':'KG'},
                {'article':'Fils','quantity':50,'unit':'KG'},
                {'article':'Barre droit','quantity':None,'unit':None}], 'delivery_note':None}
    apply_steel_accessory_context(d,'1000 kg rab12\n50 kg Fils\nBarre droit')
    assert [l['article'] for l in d['lines']]==['rab12','PF-FR130']
    assert d['delivery_note']=='Barre droite'
    assert canonical_article('Point 06')=='PF-TP16X20'
    unrelated={'lines':[{'article':'FILS','quantity':50,'unit':'UN'}]}
    apply_steel_accessory_context(unrelated,'50 FILS')
    assert unrelated['lines'][0]['article']=='FILS'


def test_location_preceding_transport_is_preserved_in_comment():
    d={'delivery_note':'Barre droite'}
    apply_service_location_note(d,'Omnia TRS 300.00')
    assert d['delivery_note']=='Barre droite ; Omnia'
    apply_service_location_note(d,'Omnia TRS 300.00')
    assert d['delivery_note']=='Barre droite ; Omnia'
