"""Isolated bounded document decoding. Input is a private temporary path, not a command."""
import io,json,subprocess,sys,tempfile,warnings
from pathlib import Path
import pymupdf
from PIL import Image,ImageOps,ImageFilter,ImageStat
Image.MAX_IMAGE_PIXELS=20_000_000
warnings.simplefilter('error',Image.DecompressionBombWarning)
MAX_PAGES=8

def ocr(image):
    image=ImageOps.exif_transpose(image).convert('RGB')
    image.thumbnail((2200,2200))
    quality=[]
    if min(image.size)<300:quality.append('low_resolution')
    gray=image.convert('L')
    if ImageStat.Stat(gray).stddev[0]<25:quality.append('low_contrast')
    # No numeric correction, OCR replacement, execution or network calls.
    with tempfile.TemporaryDirectory(prefix='sage-ocr-') as directory:
        path=Path(directory)/'page.png';image.save(path)
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(Path(__file__).with_name('windows_document_ocr.ps1')),'-ImagePath',str(path)],capture_output=True,text=True,encoding='utf-8-sig',timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise ValueError('ocr_unavailable')
        body=json.loads(result.stdout)
    return {'text':str(body.get('text',''))[:8000],'method':'windows_ocr','uncertain':True,'warnings':quality,'language':body.get('language')}

def read(path,kind):
    pages=[]
    if kind=='pdf':
        with pymupdf.open(path) as document:
            if document.needs_pass:raise ValueError('encrypted_pdf')
            if not 1<=len(document)<=MAX_PAGES:raise ValueError('page_limit')
            for index,page in enumerate(document):
                text=page.get_text('text',sort=True).strip()
                if len(text)>=15:
                    pages.append({'text':text[:8000],'method':'pdf_text','uncertain':False,'warnings':['text_truncated'] if len(text)>8000 else []})
                else:
                    scale=min(2.5,2200/max(page.rect.width,page.rect.height))
                    pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False)
                    pages.append(ocr(Image.open(io.BytesIO(pix.tobytes('png')))))
    else:
        with Image.open(path) as image:
            if image.format not in ('PNG','JPEG','WEBP','TIFF','BMP'):raise ValueError('unsupported_image')
            frames=getattr(image,'n_frames',1)
            if not 1<=frames<=MAX_PAGES:raise ValueError('page_limit')
            for index in range(frames):image.seek(index);pages.append(ocr(image.copy()))
    for index,page in enumerate(pages,1):page['page']=index
    return {'pages':pages,'reader_version':1,'instructions_executed':False}

if __name__=='__main__':
    try:print(json.dumps({'ok':True,**read(Path(sys.argv[1]),sys.argv[2])},ensure_ascii=False))
    except Exception as exc:
        known=('encrypted_pdf','page_limit','unsupported_image','ocr_unavailable')
        print(json.dumps({'ok':False,'error':str(exc) if str(exc) in known else 'unreadable_document'}))
