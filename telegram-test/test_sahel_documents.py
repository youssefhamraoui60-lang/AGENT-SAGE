import asyncio
import prepare
from telegram_batch import OrderBatches,document_references,client_scoped_history


def test_three_purchase_bons_remain_separate_and_note_attaches_to_last():
    async def run():
        received=[]
        async def process(key,messages):received.append(messages)
        batches=OrderBatches(process,delay=.01)
        docs=["Contact : Siham\nDOCUMENT JOINT :\nBON | DE | COMMANDE | D'ACHAT\nN• | : | BC"+n for n in ['2026004785','2026004763','2026004744']]
        for i,text in enumerate(docs):batches.add(1,1,100+i,text)
        batches.add(1,1,103,'Contact : Siham\nPour le fer prix modifié')
        await asyncio.gather(*list(batches.tasks),return_exceptions=True)
        assert [[i for i,_ in group] for group in received]==[[100],[101],[102,103]]
        assert client_scoped_history([{'role':'user','content':docs[0]}],docs[1])==[]
        assert document_references(docs[0])=={'BC2026004785'}
        await batches.close()
    asyncio.run(run())


def test_unknown_document_reference_does_not_merge_attachments():
    history=[{'role':'user','content':'DOCUMENT JOINT :\nimage illisible'}]
    assert client_scoped_history(history,'DOCUMENT JOINT :\nautre image')==[]


def test_steel_diameter_after_ha_t_is_preserved():
    for diameter in [6,8,10,12]:
        assert prepare.canonical_article('ACIER HA T'+str(diameter))==('RABT6' if diameter==6 else 'RAB'+str(diameter))


def test_printed_ht_price_is_converted_once_even_with_modified_price_note():
    text='DOCUMENT JOINT :\nDésignation | Quantité | Unité | Prix net HT | Montant HT\nACIER HA T12 | 400,000 | KG | 8,17 | 3268,00\nTVA 20 %\nPour le fer prix modifié'
    draft={'lines':[{'article':'RAB12','quantity':400,'price':8.17}]}
    prepare.apply_explicit_ht_table(draft,text)
    assert draft['lines'][0]['price']==9.804


def test_cement_sac_description_corrects_model_thousand_decimal_error():
    text='DOCUMENT JOINT :\nDésignation | Quantité | Unité | Prix net HT | Montant HT\nCIMENT CPJ45 SAC | 2,000 | T | 1383,34 | 2766,68\nTVA 20 %'
    draft={'lines':[{'article':'CPJ45','quantity':2000,'price':1660.008,'unit':'T'}]}
    prepare.apply_explicit_ht_table(draft,text)
    assert draft['lines'][0]['quantity']==2
    assert draft['lines'][0]['price']==1660.008
    prepare.apply_explicit_ht_table(draft,text)
    assert draft['lines'][0]['price']==1660.008
