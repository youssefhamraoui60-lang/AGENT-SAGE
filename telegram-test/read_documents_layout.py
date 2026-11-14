"""SOB-only document replay preserving table rows, without changing the other agent."""
import concurrent.futures
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import statistics
import pymupdf
from PIL import Image,ImageOps,ImageFilter
import re

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/sob-week-20261102'

def rows(words):
    if not words:return ''
    height=statistics.median(w['height'] for w in words if w['height']>0)
    clusters=[]
    for word in sorted(words,key=lambda w:w['y']+w['height']/2):
        center=word['y']+word['height']/2
        if clusters and abs(center-clusters[-1][0])<height*.6:
            clusters[-1][1].append(word)
        else:clusters.append([center,[word]])
    return '\n'.join(' | '.join(w['text'] for w in sorted(group,key=lambda w:w['x'])) for _,group in clusters)

def ocr(image):
    image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((2300,2300))
    with tempfile.TemporaryDirectory(prefix='sob-layout-') as folder:
        path=Path(folder)/'page.png';image.save(path)
        proc=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(Path(__file__).with_name('sob-ocr-layout.ps1')),'-ImagePath',str(path)],capture_output=True,encoding='utf-8-sig',timeout=35)
        if proc.returncode:raise ValueError('OCR indisponible')
        data=json.loads(proc.stdout)
    return {'text':rows(data['words']),'uncertain':True,'method':'ocr_words_rows','words':data['words'],'image_size':image.size}


def identity_and_price_regions(image,result):
    """Enlarge small logos/footers and narrow price columns, not the whole page."""
    if not re.search(r'(?i)commande|designation|ciment|\bfer\b',result['text']):return result
    im=ImageOps.exif_transpose(image).convert('RGB')
    rotation=re.fullmatch(r'ocr_rotation_(90|270)',result.get('method',''))
    if rotation:im=im.rotate(int(rotation[1]),expand=True)
    im.thumbnail((2300,2300))
    regions=[('EN-TETE', (0,0,im.width,im.height*.20)),
             ('EN-TETE GAUCHE',(0,0,im.width*.5,im.height*.25)),
             ('EN-TETE DROIT',(im.width*.5,0,im.width,im.height*.25)),
             ('PIED/CACHET',(0,im.height*.80,im.width,im.height))]
    size=result.get('image_size',im.size)
    sx,sy=im.width/max(size[0],1),im.height/max(size[1],1)
    words=[{**w,'x':w['x']*sx,'width':w['width']*sx,'y':w['y']*sy,'height':w['height']*sy} for w in result.get('words',[])]
    for word in words:
        if word['text'].casefold()=='prix':
            x,y=word['x'],word['y']
            next_y=[w['y'] for w in words if w['y']>y+3*word['height'] and re.match(r'(?i)^(?:NB|Veuillez|TOTAL)$',w['text'])]
            bottom=min(next_y) if next_y else min(im.height,y+im.height*.28)
            regions.append(('COLONNE PRIX',(max(0,x-20),max(0,y-10),im.width,bottom)))
            break
    extras=[]
    for label,box in regions:
        box=(max(0,box[0]),max(0,box[1]),min(im.width,box[2]),min(im.height,box[3]))
        if box[2]<=box[0] or box[3]<=box[1]:continue
        crop=im.crop(tuple(map(int,box)));crop=ImageOps.autocontrast(crop)
        scale=min(3,2300/max(crop.size));crop=crop.resize((max(1,int(crop.width*scale)),max(1,int(crop.height*scale))))
        try:
            text=ocr(crop)['text'].strip()
            if text:extras.append(label+' (LECTURE AGRANDIE) :\n'+text)
        except (ValueError,subprocess.TimeoutExpired):continue
    return {**result,'text':result['text']+('\n'+'\n'.join(extras) if extras else ''),'identity_regions':extras}


def photo_ocr(image):
    first=ocr(image)
    if len(re.sub(r'\W','',first['text']))>=40:
        return first
    # Flatten uneven illumination before enlarging faint printed text.
    # This changes OCR input only; the source document remains untouched.
    gray=ImageOps.grayscale(ImageOps.exif_transpose(image))
    gray.thumbnail((1600,1600))
    background=gray.filter(ImageFilter.GaussianBlur(18))
    flattened=Image.frombytes('L',gray.size,bytes(
        min(255,int(g*180/max(b,1))) for g,b in zip(gray.tobytes(),background.tobytes())))
    enhanced=ImageOps.autocontrast(flattened,cutoff=1)
    scale=min(2,2300/max(enhanced.size))
    enhanced=enhanced.resize((int(enhanced.width*scale),int(enhanced.height*scale)))
    try:
        retry=ocr(enhanced)
    except (ValueError,subprocess.TimeoutExpired):
        return first
    best={**retry,'method':'ocr_illumination_retry'} if len(re.sub(r'\W','',retry['text']))>len(re.sub(r'\W','',first['text'])) else first
    if len(re.sub(r'\W','',best['text']))<40:
        for angle in (90,270):
            try:rotated=ocr(ImageOps.exif_transpose(image).rotate(angle,expand=True))
            except (ValueError,subprocess.TimeoutExpired):continue
            if len(re.sub(r'\W','',rotated['text']))>len(re.sub(r'\W','',best['text'])):
                best={**rotated,'method':'ocr_rotation_'+str(angle)}
            if len(re.sub(r'\W','',best['text']))>=40:break
    return best

def read(path):
    pages=[]
    import learning_memory
    policy=next((r['payload'].get('value',{}) for r in learning_memory.approved_rules()
                 if r['kind']=='policy' and r['rule_key']=='document_visual_ocr'),{})
    from document_vision import enrich
    if path.suffix.lower()=='.pdf':
        with pymupdf.open(path) as doc:
            if doc.needs_pass or len(doc)>8:raise ValueError('PDF protégé ou plus de 8 pages')
            for page_number,page in enumerate(doc):
                words=page.get_text('words')
                if len(words)>=4:
                    text=rows([{'x':w[0],'y':w[1],'width':w[2]-w[0],'height':w[3]-w[1],'text':w[4]} for w in words])
                    identity_regions=[]
                    # Text extraction can omit a logo/stamp embedded as artwork.
                    # Read bounded identity regions of the first illustrated page too.
                    if page_number==0 and page.get_images():
                        for label,box in [('EN-TETE',pymupdf.Rect(0,0,page.rect.width,page.rect.height*.23)),
                                          ('EN-TETE GAUCHE',pymupdf.Rect(0,0,page.rect.width*.5,page.rect.height*.25)),
                                          ('EN-TETE DROIT',pymupdf.Rect(page.rect.width*.5,0,page.rect.width,page.rect.height*.25)),
                                          ('PIED/CACHET',pymupdf.Rect(0,page.rect.height*.82,page.rect.width,page.rect.height))]:
                            try:
                                pix=page.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=box,alpha=False)
                                with Image.open(io.BytesIO(pix.tobytes('png'))) as region:
                                    decoded=ocr(region)
                                if decoded['text'].strip():identity_regions.append({'region':label,'text':decoded['text']})
                            except (ValueError,subprocess.TimeoutExpired):
                                pass  # retain native text; do not invent an identity
                        header=next((r['text'] for r in identity_regions if r['region']=='EN-TETE'),'')
                        footer=next((r['text'] for r in identity_regions if r['region']=='PIED/CACHET'),'')
                        text=(header+'\n' if header else '')+text+('\n'+footer if footer else '')
                        for item in identity_regions:
                            if item['region'] in ('EN-TETE GAUCHE','EN-TETE DROIT'):
                                text+='\n'+item['region']+' (LECTURE SEPAREE) :\n'+item['text']
                    pages.append({'text':text,'uncertain':bool(identity_regions),'method':'pdf_words_rows',
                                  'identity_regions':identity_regions})
                else:
                    pix=page.get_pixmap(matrix=pymupdf.Matrix(2.5,2.5),alpha=False)
                    with Image.open(io.BytesIO(pix.tobytes('png'))) as scan:
                        initial=identity_and_price_regions(scan.copy(),photo_ocr(scan.copy()))
                        pages.append(enrich(scan.copy(),initial,policy if page_number==0 else {}))
    else:
        with Image.open(path) as image:
            initial=identity_and_price_regions(image.copy(),photo_ocr(image.copy()))
            pages.append(enrich(image.copy(),initial,policy))
    return {'ok':True,'pages':pages,'instructions_executed':False}

def main():
    global OUT
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--out')
    args=parser.parse_args()
    if args.out:OUT=Path(args.out).resolve()
    source=OUT/'messages-decoded.json'
    if not source.exists():source=OUT/'messages-week.json'
    messages=json.loads(source.read_text(encoding='utf-8'))
    cache=OUT/'layout-cache';cache.mkdir(exist_ok=True)
    def process(item):
        if not item.get('file'):return
        path=(OUT/item['file']).resolve()
        if not path.is_relative_to(OUT.resolve()):raise ValueError('Document hors audit')
        target=cache/(hashlib.sha256(path.read_bytes()).hexdigest()+'.json')
        if target.exists():data=json.loads(target.read_text(encoding='utf-8'))
        else:
            try:data=read(path)
            except Exception as exc:data={'ok':False,'error':type(exc).__name__}
            target.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        item['layout_decode']=data
        item['layout_text']='\n\n'.join(p['text'] for p in data.get('pages',[]))
        print(json.dumps({'id':item['id'],'ok':data['ok'],'chars':len(item['layout_text'])}),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(process,messages))
    (OUT/'messages-layout.json').write_text(json.dumps(messages,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
