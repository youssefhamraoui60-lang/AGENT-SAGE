import asyncio,json
from PIL import Image
import pytest
import learning_memory
import prepare as module
import read_documents_layout as documents
from source_article_safety import missing_explicit_articles


def test_explicit_rab10_cannot_be_replaced_by_packaging_film():
    source='Contact : Wiam\nC10246\n1000 kg rab 10 sonasid\n50 transport'
    wrong=[{'article':'FL_ET','quantity':1000},{'article':'MANTD','quantity':1}]
    assert missing_explicit_articles(source,wrong,module.canonical_article)==['RAB10']
    assert missing_explicit_articles(source,[{'article':'RAB10_F050'},{'article':'MANTD'}],module.canonical_article)==[]
    assert missing_explicit_articles('Téléphone : 212612345678\nAdresse : 10 rab',wrong,module.canonical_article)==[]


def test_pdf_quantities_do_not_become_caption_article_claims():
    assert missing_explicit_articles('DOCUMENT JOINT :\n1000 kg rab 10',[],module.canonical_article)==[]


def test_printed_diameter_and_brick_labels_are_bounded():
    token=learning_memory.ACTIVE.set(())
    try:
        assert module.canonical_article('Acier HA diamètre 6 mm')=='RABT6'
        assert module.canonical_article('ACIER DIAM 12')=='RAB12'
        assert module.canonical_article('BRIQUE 07')=='BQ7'
        assert module.canonical_article('Acier')=='Acier'
        assert module.canonical_article('Brique rouge')=='Brique rouge'
        assert module.canonical_article('Brique rouge 7*20*25 cm')=='BQ7'
        assert module.canonical_article('Briques rouges 7*20')=='BQ7'
    finally:learning_memory.ACTIVE.reset(token)


def test_sideways_handwriting_gets_orientation_retry_without_mutating_file(monkeypatch):
    image=Image.new('RGB',(40,70),'white');original=image.tobytes();calls=[]
    def ocr(im):
        calls.append(im.size)
        return {'text':'ENIBAC SARL BON DE COMMANDE CIMENT CPJ45 28 TONNES' if im.size==(70,40) else '', 'uncertain':True,'method':'ocr_words_rows'}
    monkeypatch.setattr(documents,'ocr',ocr)
    result=documents.photo_ocr(image)
    assert result['method']=='ocr_rotation_90' and 'ENIBAC' in result['text']
    assert image.tobytes()==original


def test_one_explicit_diameter_repairs_generic_model_label_without_changing_amounts():
    from source_article_safety import ground_single_explicit_steel
    draft={'lines':[{'article':'rab','quantity':1000,'price':None,'unit':'KG'},{'article':'MANTD','quantity':1,'price':50}]}
    assert ground_single_explicit_steel(draft,'1000 kg rab 10 sonasid\n50 transport',module.canonical_article)
    assert draft['lines'][0]=={'article':'RAB10','quantity':1000,'price':None,'unit':'KG'}
    ambiguous={'lines':[{'article':'rab','quantity':1000}]}
    assert not ground_single_explicit_steel(ambiguous,'1000 kg rab 10\n500 kg rab 12',module.canonical_article)
    assert ambiguous['lines'][0]['article']=='rab'

def test_explicit_quantities_and_compact_diameters_override_model_conversion_errors():
    from source_article_safety import ground_explicit_caption_quantities
    draft={'lines':[{'article':'RABT6','quantity':4,'unit':'KG','price':9.3},
                    {'article':'RAB8','quantity':4000000,'unit':'KG','price':9.3}]}
    ground_explicit_caption_quantities(draft,'4T6\n4t8',module.canonical_article)
    assert [(r['quantity'],r['unit']) for r in draft['lines']]==[(4,'tonnes'),(4,'tonnes')]
    assert missing_explicit_articles('4T6\n4t8',[],module.canonical_article)==['RAB8','RABT6']

def test_generic_red_bricks_do_not_prove_a_diameter_from_price_or_date():
    from source_article_safety import brick_dimension_supported
    assert not brick_dimension_supported('Date 07/11/2026\nBriques rouges | 272000 | 2.30','BQ7')
    assert brick_dimension_supported('BRIQUE | ROUGE | 7 | 13400','BQ7')
    assert brick_dimension_supported('Briques rouges 7*20*25 cm','BQ7')
    assert brick_dimension_supported('2 palettes BR7','BQ7')


@pytest.mark.parametrize('model_article',['rab','FL_ET'])
def test_full_preparation_repairs_generic_steel_or_blocks_false_specific_sku(monkeypatch,model_article):
    from app.core.config import settings
    from app.services import ai_provider
    draft={'intent':'order','client':'C10246','representative':None,'delivery':'2026-11-12','delivery_note':None,'question':'','lines':[{'article':model_article,'quantity':1000,'price':9.5,'unit':'KG'}]}
    async def complete(*args,**kwargs):return {'message':{'content':json.dumps(draft)}}
    def lookup(kind,code,*args,**kwargs):
        if kind=='client':return [{'BPCNUM_0':'C10246','BPCNAM_0':'LAASSIRY TAIKA','CUR_0':'MAD','REP_0':'REP012','VACBPR_0':'MAR'}]
        if kind=='article':return [{'ITMREF_0':code,'ITMDES1_0':'FER D10' if code=='RAB10' else 'FILM ETIRABLE','SAU_0':'KG','STU_0':'KG','VACITM_0':'T20','SITE_OK':1}]
        return []
    monkeypatch.setattr(settings,'ai_provider','deepseek');monkeypatch.setattr(ai_provider,'complete',complete)
    monkeypatch.setattr(module,'lookup',lookup);monkeypatch.setattr(learning_memory,'approved_rules',lambda:[])
    details=asyncio.run(module.prepare([{'role':'user','content':'C10246\n1000 kg rab 10 sonasid'}],details=True))
    if model_article=='rab':assert details['lines'][0]['article']=='RAB10'
    else:assert 'article explicite source non repris : RAB10' in details['missing_fields']
