import json
import asyncio
from document_grounding import apply,issues
from prepare import document_issuer_names,normalize_sale_price,corporate_identity
from understanding import normalize_quantity

def test_split_letterhead_and_legal_footer_keep_buyers_separate_from_receiver():
    text='DOCUMENT JOINT :\nHAJJI ISSKAN\nSHAMA BAY\nSTE OULD BOUAZZA\nBON DE COMMANDE 222/2026'
    assert 'HAJJI ISSKAN SHAMA BAY' in document_issuer_names(text)
    text='DOCUMENT JOINT :\nSociété Mobilifer\nBON DE COMMANDE 123\nFournisseur : OULD BOUAZZA'
    assert 'Mobilifer' in document_issuer_names(text)

def test_legal_forms_do_not_erase_project_or_company_name():
    assert corporate_identity('STE MOBILIFER SARL AU')==corporate_identity('Mobilifer')
    assert corporate_identity('HAJJI ISSKAN SHAMA BAY')!=corporate_identity('HAJJI ISSKAN')
    assert corporate_identity('STELLA')=='stella'

def test_separate_letterhead_columns_do_not_merge_buyer_with_receivers_city():
    text='DOCUMENT JOINT :\nTanger le 10/11/2026\nOULD BOUAZZA\nBON DE COMMANDE 10/11/M\nEN-TETE GAUCHE (LECTURE SEPAREE) :\nALPHA BATIMENT\nICE 003702736000051\nEN-TETE DROIT (LECTURE SEPAREE) :\nOULD BOUAZZA\nBerrchid'
    names=document_issuer_names(text)
    assert 'ALPHA BATIMENT' in names
    assert 'ALPHA BATIMENT Berrchid' not in names

def test_bc_heading_and_dotted_tax_labels_are_not_lost():
    from prepare import is_order_document,document_total_ttc,document_tax_rates
    from telegram_batch import document_references
    assert is_order_document('BC | NO: | BD002026 | BATINDAY')
    assert document_references('BC | NO: | BD002026 | BATINDAY')=={'BD002026'}
    assert not is_order_document('FACTURE N°F123\nRéférence BC NO: BD002026')
    assert is_order_document('BON DE COMMANDE 123\nPaiement : facture à réception')
    assert document_total_ttc('DOCUMENT JOINT :\nTOTAL T.T.C : 32 160,00')==32160
    assert document_tax_rates('DOCUMENT JOINT :\nT.V.A 7%')=={7}
    assert is_order_document('Numéro\nCommande\nCF00001369')
    assert document_references('Numéro\nCommande\nCF00001369')=={'CF00001369'}

def test_complete_source_reference_repairs_an_omitted_width_not_a_conflicting_finish():
    from document_grounding import restore_complete_product_labels
    source='DOCUMENT JOINT :\nAFRIFLEX | 30 | W | 60 | F/F | RLX | 604 | 300'
    canonical=lambda v:'AFR_30VV_60' if '60' in v else v
    d={'lines':[{'article':'AFRIFLEX 30 W F/F RLX','quantity':604,'price':300}]}
    restore_complete_product_labels(d,source,canonical)
    assert '60' in d['lines'][0]['article']
    assert d['lines'][0]['quantity']==604
    bad={'lines':[{'article':'AFRIFLEX 30 VV ARD GRIS','quantity':604}]}
    restore_complete_product_labels(bad,source,canonical)
    assert bad['lines'][0]['article']=='AFRIFLEX 30 VV ARD GRIS'

def test_brick_diameter_is_restored_only_when_written_in_a_source_row():
    from document_grounding import restore_complete_product_labels
    from prepare import canonical_article
    d={'lines':[{'article':'BRIQUE ROUGE','quantity':13400,'price':2.3}]}
    restore_complete_product_labels(d,'DOCUMENT JOINT :\n13.400 | UNITE | BRIQUE ROUGE 7 | 2.30',canonical_article)
    assert canonical_article(d['lines'][0]['article'])=='BQ7'
    unknown={'lines':[{'article':'BRIQUE ROUGE','quantity':272000}]}
    restore_complete_product_labels(unknown,'DOCUMENT JOINT :\nBriques rouges | 272000 | 2.30',canonical_article)
    assert unknown['lines'][0]['article']=='BRIQUE ROUGE'

def test_merged_steel_price_column_preserves_all_five_rows():
    text='DOCUMENT JOINT :\nBON DE COMMANDE 016/26\nFER 16 08 TONNE\nFER 14 06 TONNE\nFER 12 04 TONNE\nFER 10 10 TONNE\nFER 06 02 TONNE\nCOLONNE PRIX (LECTURE AGRANDIE) :\nPRIX | TTC/KG\n9.30'
    draft={'lines':[{'article':'Acier','quantity':30,'unit':'TONNE','price':None}]}
    apply(draft,text)
    assert len(draft['lines'])==5
    assert [r['quantity'] for r in draft['lines']]==[8,6,4,10,2]
    assert all(r['price']==9.3 and r['price_unit']=='KG' for r in draft['lines'])

def test_unreadable_diameter_cannot_be_silently_dropped():
    d={'lines':[{'article':'Original'}]}
    apply(d,'DOCUMENT JOINT :\nFER 12 04 TONNE\nFER IO 10 TONNE')
    assert d['lines']==[{'article':'Original'}]

def test_cement_prices_per_tonne_are_not_interpreted_as_prices_per_sack():
    d={'lines':[]};apply(d,'DOCUMENT JOINT :\nDESIGNATION QTE PRIX TTC/T TOTAL TTC\nCIMENT 45 LAFARGE 2 TONNE 1 610.00 3 220.00\nCIMENT 35 LAFARGE 13 TONNE 1 570.00 20 410.00')
    assert len(d['lines'])==2
    for r in d['lines']:
        article={'ITMREF_0':r['article'],'SAU_0':'SAC'}
        normalize_quantity(r,article);normalize_sale_price(r,article)
    assert [(r['quantity'],r['price']) for r in d['lines']]==[(40,80.5),(260,78.5)]

def test_arithmetic_contradiction_is_not_corrected_by_guessing():
    d={'lines':[]};apply(d,'DOCUMENT JOINT :\nPRIX TTC/T\nCIMENT 45 LAFARGE 2 TONNE 1 610.00 4 220.00')
    assert d['lines']==[]

def test_printed_cement_grade_does_not_replace_the_quantity():
    from prepare import document_total_ttc
    text='DOCUMENT JOINT :\nN° | Désignation | Quantité | Prix U TTC | Prix TOTAL TTC\n1 | Ciment | 45 | 120 | - | 82,00 | DH- | - | 9\u202f840,00 | DH-\nTOTAL | TTC | - | 10\u202f140,00 | DH-'
    d={'lines':[{'article':'CPJ45','quantity':45,'unit':'SAC','price':82}]};apply(d,text)
    assert d['lines'][0]['quantity']==120
    assert document_total_ttc(text)==10140

def test_weak_visual_reading_remains_a_blocker():
    assert issues('DOCUMENT JOINT :\nLECTURE INCERTAINE A CONFIRMER : ligne barrée')

def test_explicit_delivery_date_is_preserved_except_caption_correction():
    from document_grounding import explicit_delivery
    text='DOCUMENT JOINT :\nDATE | DE | LIVRAISON | : | 10/11/2026'
    assert explicit_delivery(text)=='2026-11-10'
    assert explicit_delivery('Livrer demain\n'+text) is None
    assert explicit_delivery('DOCUMENT JOINT :\nAcheteur | Projet | Date de livraison :\nSofia | Domaine Azur | 09/11/2026')=='2026-11-09'

def test_model_cannot_invent_a_white_cement_brand_from_a_generic_source(monkeypatch):
    import prepare as module
    import learning_memory
    from app.core.config import settings
    from app.services import ai_provider
    async def complete(*args,**kwargs):return {'message':{'content':json.dumps({'intent':'order','client':'C05751','lines':[{'article':'PW_CEM','quantity':4,'unit':'SAC','price':120}]})}}
    def lookup(kind,code,*args,**kwargs):
        if kind=='client':return [{'BPCNUM_0':'C05751','BPCNAM_0':'Client','CUR_0':'MAD','REP_0':'REP012','VACBPR_0':'MAR'}]
        if kind=='article':return [{'ITMREF_0':'PW_CEM','ITMDES1_0':'POWER CEM I CIMENT BLANC 40 KG','SAU_0':'SAC','VACITM_0':'T20','SITE_OK':1}]
        return []
    monkeypatch.setattr(settings,'ai_provider','deepseek');monkeypatch.setattr(ai_provider,'complete',complete)
    monkeypatch.setattr(module,'lookup',lookup);monkeypatch.setattr(learning_memory,'approved_rules',lambda:[])
    d=asyncio.run(module.prepare([{'role':'user','content':'C05751\n4 sacs Ciment Blanc 40 kg à 120 DH'}],details=True))
    assert 'référence exacte du ciment blanc 40 kg' in d['missing_fields']
    assert not d['lines']
