from PIL import Image
import read_documents_layout as documents


def test_faint_photo_retries_without_changing_original(monkeypatch):
    original = Image.new('RGB', (40, 60), (150, 150, 150))
    before = original.tobytes()
    calls = []
    def fake_ocr(image):
        calls.append(image.size)
        return {'text': "tr'02E" if len(calls) == 1 else 'BECOMAR BON DE COMMANDE CPJ35 100 SAC TOTAL TTC 8000',
                'uncertain': True, 'method': 'ocr_words_rows'}
    monkeypatch.setattr(documents, 'ocr', fake_ocr)
    result = documents.photo_ocr(original)
    assert result['method'] == 'ocr_illumination_retry'
    assert '100 SAC' in result['text']
    assert original.tobytes() == before
    assert len(calls) == 2


def test_readable_photo_keeps_first_ocr(monkeypatch):
    calls = []
    def fake_ocr(image):
        calls.append(1)
        return {'text': 'BON DE COMMANDE BECOMAR 100 SACS CPJ35 TOTAL TTC 8000 DH',
                'uncertain': True, 'method': 'ocr_words_rows'}
    monkeypatch.setattr(documents, 'ocr', fake_ocr)
    assert documents.photo_ocr(Image.new('RGB', (40, 60)))['method'] == 'ocr_words_rows'
    assert len(calls) == 1

def test_enlarged_regions_follow_rotated_page_coordinates(monkeypatch):
    calls=[]
    def fake(image):
        calls.append(image.size)
        return {'text':'9.30','uncertain':True,'method':'ocr_words_rows'}
    monkeypatch.setattr(documents,'ocr',fake)
    image=Image.new('RGB',(40,80));original=image.tobytes()
    result=documents.identity_and_price_regions(image,{'text':'BON DE COMMANDE PRIX TTC/KG',
        'method':'ocr_rotation_90','uncertain':True,'image_size':(80,40),
        'words':[{'text':'PRIX','x':50,'y':15,'width':15,'height':4}]})
    assert calls[0]==(240,24)
    assert '9.30' in result['text']
    assert image.tobytes()==original
