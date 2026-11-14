from PIL import Image
import httpx
import document_vision as vision

def test_visual_ocr_timeout_preserves_native_reading_and_marks_weak_input(monkeypatch):
    def failed(*args,**kwargs):raise httpx.ReadTimeout('local timeout')
    monkeypatch.setattr(vision,'transcribe',failed)
    r=vision.enrich(Image.new('RGB',(20,20)),{'text':'abc','method':'ocr','uncertain':True},{'enabled':True})
    assert r['text'].startswith('abc') and 'LECTURE INCERTAINE A CONFIRMER' in r['text']
    assert r['vision_error']=='ReadTimeout'

def test_visual_ocr_keeps_enlarged_price_column_as_source(monkeypatch):
    monkeypatch.setattr(vision,'transcribe',lambda *a,**k:'BON DE COMMANDE\nFER 12 04 TONNE')
    raw={'text':'BON DE COMMANDE FER12 QUANTITE4 TONNE PRIX TTC/KG','method':'ocr','uncertain':True,
         'identity_regions':['COLONNE PRIX (LECTURE AGRANDIE) :\nPRIX | TTC/KG\n9.30']}
    r=vision.enrich(Image.new('RGB',(20,20)),raw,{'enabled':True})
    assert '9.30' in r['text'] and r['raw_ocr']==raw['text']

def test_disabled_vision_makes_no_network_call(monkeypatch):
    monkeypatch.setattr(vision,'transcribe',lambda *a,**k:(_ for _ in ()).throw(AssertionError('No model call')))
    raw={'text':'existing','method':'ocr'}
    assert vision.enrich(Image.new('RGB',(20,20)),raw,{}) is raw
