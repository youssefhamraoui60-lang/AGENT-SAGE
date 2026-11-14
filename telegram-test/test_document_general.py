from decimal import Decimal
import json
from PIL import Image
import pymupdf
import learning_memory
import read_documents_layout as documents
from prepare import document_issuer_names, document_total_ttc


def test_ice_with_pdf_word_separators_keeps_exact_fifteen_digits():
    from prepare import document_ices
    assert document_ices('ICE : 00 | 33 | 77 | 33 | 00000 | 44\nMARRAKECH')=={'003377330000044'}
    assert document_ices('ICE 00337733000004499')==set()
    assert document_ices('ICE | NO | 002282315000043')=={'002282315000043'}
    assert document_ices('I.C.E N°: 002282315000043')=={'002282315000043'}
    assert document_ices('ICE N0001815204000003')==set()


def test_conventional_steel_labels_resolve_diameters_without_guessing_other_items():
    from prepare import canonical_article
    token=learning_memory.ACTIVE.set(())
    try:
        assert canonical_article('HA6')=='RABT6'
        assert canonical_article('Acier HA20')=='RAB20'
        assert canonical_article('Fer à béton HA Ø16 mm')=='RAB16'
        assert canonical_article('FER ROND 14')=='RAB14'
        assert canonical_article('Carre 14')=='Carre 14'
    finally:learning_memory.ACTIVE.reset(token)


def test_letterhead_name_is_separate_from_receiver_and_caption():
    text='Contact : Abdelmajid\nMediouna\nDOCUMENT JOINT :\nTA | BUILDING\nCasablanca le : 07-11-2026\nNOM : OULD BOUAZAA\nBON | DE | COMMANDE 0072'
    assert document_issuer_names(text)==['TA BUILDING']
    assert document_issuer_names(text.replace('BON | DE | COMMANDE','FACTURE'))==[]


def test_document_total_handles_ocr_table_separators():
    assert document_total_ttc('DOCUMENT JOINT :\nMontant | Total | TTC | 312 | 800.00')==Decimal('312800')
    assert document_total_ttc('DOCUMENT JOINT :\nTOTAL TTC : 8 000,00 DH')==Decimal('8000')
    assert document_total_ttc('DOCUMENT JOINT :\nTOTAL TTC 100\nTOTAL TTC 200') is None
    assert document_total_ttc('TOTAL TTC 200') is None
    assert document_total_ttc('DOCUMENT JOINT :\nTTC | : | 0,00 | Dh')==Decimal(0)


def test_explicit_caption_supplement_is_added_once_outside_pdf_total():
    from prepare import document_caption_supplements
    text='SVP : PLUS 1000 TRANSPORT\nDOCUMENT JOINT :\nTotal TTC 277920 DH'
    assert document_total_ttc(text)+document_caption_supplements(text)==Decimal('278920')
    assert document_caption_supplements('DOCUMENT JOINT :\nPLUS 1000 TRANSPORT\nTotal TTC 277920')==0
    assert document_caption_supplements('1000 dh\nDOCUMENT JOINT :\nTotal TTC 277920')==0


def test_verified_photo_transcription_cannot_leak_into_other_document_prompt():
    token=learning_memory.ACTIVE.set(({'kind':'interpretation','rule_key':'document_sha256_abc',
                                      'payload':{'transcription':'UNRELATED CUSTOMER 9999 KG'}},))
    try:
        assert json.loads(learning_memory.prompt_context('Different document'))==[]
    finally:
        learning_memory.ACTIVE.reset(token)

def test_exact_file_review_flag_cannot_be_cleared_by_a_plausible_ocr_result(tmp_path,monkeypatch):
    import document_memory
    path=tmp_path/'ambiguous.png';path.write_bytes(b'crossed-out-price')
    sha=document_memory.fingerprint(path)
    monkeypatch.setattr(learning_memory,'approved_rules',lambda:[{'kind':'interpretation','rule_key':'document_sha256_'+sha,'payload':{'requires_review':True,'review_reason':'Transport barré'}}])
    reader=lambda p:{'pages':[{'text':'BON DE COMMANDE CIMENT35 300 SAC 80','uncertain':False,'method':'pdf_words_rows'}]}
    result=document_memory.decode(path,reader)
    assert result['requires_review'] and result['uncertain']
    assert 'LECTURE INCERTAINE A CONFIRMER' in result['text']
    path.write_bytes(b'new-clear-document')
    assert not document_memory.decode(path,reader)['requires_review']


def test_native_pdf_reads_rows_without_ocr(tmp_path,monkeypatch):
    path=tmp_path/'native.pdf'
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((30,30),'TA BUILDING\nBON DE COMMANDE\nRAB14 6000 KG 9.20')
        doc.save(path)
    monkeypatch.setattr(documents,'photo_ocr',lambda image: (_ for _ in ()).throw(AssertionError('No OCR needed')))
    result=documents.read(path)
    assert '6000' in result['pages'][0]['text']
    assert result['pages'][0]['method']=='pdf_words_rows'


def test_scanned_pdf_uses_improved_photo_reader(tmp_path,monkeypatch):
    monkeypatch.setattr(learning_memory,'approved_rules',lambda:[])
    path=tmp_path/'scan.pdf'
    with Image.new('RGB',(50,70),'white') as image:
        image.save(path,'PDF')
    calls=[]
    def reader(image):
        calls.append(image.size)
        return {'text':'TA BUILDING BON DE COMMANDE','uncertain':True,'method':'ocr_illumination_retry'}
    monkeypatch.setattr(documents,'photo_ocr',reader)
    result=documents.read(path)
    assert len(calls)==1
    assert result['pages'][0]['method']=='ocr_illumination_retry'
