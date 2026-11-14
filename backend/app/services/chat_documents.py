"""Owner-scoped document reading, literal proposals and chat conflict resolution."""
import copy,json,re,subprocess,sys,tempfile,threading,logging
from pathlib import Path
from uuid import UUID,uuid4
from psycopg.types.json import Jsonb
from app.services import chat_storage as storage,business_store as db,sage_crud as crud,document_fields
from app.services.chat_turns import norm

SLOTS=threading.BoundedSemaphore(2)
FORMATS={'.pdf':'pdf','.png':'image','.jpg':'image','.jpeg':'image','.webp':'image','.tif':'image','.tiff':'image','.bmp':'image'}
MAX_BYTES=25*1024*1024

def decode(data,kind):
    if not SLOTS.acquire(timeout=3):raise crud.CrudError('La lecture de documents est occupée. Réessayez dans un instant.',429)
    try:
        with tempfile.TemporaryDirectory(prefix='sage-document-') as directory:
            path=Path(directory)/('input.pdf' if kind=='pdf' else 'input.image');path.write_bytes(data)
            process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('document_reader_worker.py')),str(path),kind],stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:out,_=process.communicate(timeout=70)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));process.communicate()
                raise crud.CrudError('Lecture trop longue. Envoyez un document plus court ou plus net.',422) from None
            try:body=json.loads(out.decode('utf-8-sig'))
            except (ValueError,UnicodeError):raise crud.CrudError('Ce document ne peut pas être lu. Essayez un PDF ou une image plus nette.',422) from None
            if not body.get('ok'):
                messages={'encrypted_pdf':'Ce PDF est protégé par un mot de passe. Envoyez une copie accessible.','page_limit':'Envoyez au maximum 8 pages par document.','ocr_unavailable':'La lecture des images est indisponible pour le moment. Votre fichier est conservé.'}
                raise crud.CrudError(messages.get(body.get('error'),'Document illisible ou format non pris en charge. Votre fichier est conservé.'),422)
            return body
    finally:SLOTS.release()

def equivalent(field,a,b):
    if field in ('ice','identifiant_fiscal','rc'):return str(a)==str(b)
    return ' '.join(norm(str(a)).split())==' '.join(norm(str(b)).split())

def set_field(state,field,candidate):
    from app.services.supplier_dialogue import assign
    from app.schemas.conversation_entities import SupplierPatch
    SupplierPatch.model_validate({field:candidate['value']})
    if field=='ice' and not re.fullmatch(r'[0-9]{15}',candidate['value']):raise ValueError('invalid_ice')
    if field=='email' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',candidate['value']):raise ValueError('invalid_email')
    # Only a single selected supplier is presented to the existing guarded assignment.
    selected=next(p for p in state['partners'] if p['id']==state['document_review']['target_id'])
    original=state['partners'];state['partners']=[selected]
    try:
        error=assign(state,field,candidate['value'])
        if error:raise ValueError('locked_supplier')
    finally:state['partners']=original
    selected.setdefault('document_sources',{})[field]=candidate['source']
    selected.setdefault('sources',{})[field]='document_declared'

def question(state):
    review=state.get('document_review') or {}
    if not review.get('target_id'):return 'À quel fournisseur appliquer le document ? Indiquez son nom ou son numéro.'
    if not review.get('items'):return ''
    item=review['items'][0];label=document_fields.TITLES[item['field']]
    if item['reason']=='ocr':return 'La lecture du document est à vérifier. Confirmez « utilise les valeurs du document », ou corrigez un champ dans le chat.'
    if item['reason']=='invalid':return label+' est incertain ou invalide. Indiquez sa valeur exacte dans le chat.'
    values=([{'value':item['existing'],'existing':True}] if item.get('existing') not in (None,'') else [])+item['choices']
    options=' ; '.join(str(i+1)+'. '+c['value']+(' (fiche actuelle)' if c.get('existing') else ' ('+c['source']['filename']+', page '+str(c['source']['page'])+')') for i,c in enumerate(values))
    return 'Quelle valeur retenir pour '+label+' ? '+options+'. Répondez par son numéro ou corrigez le champ.'

def apply_candidates(state,report,file_id,filename):
    state=copy.deepcopy(state);suppliers=[p for p in state.get('partners',[]) if p.get('kind')=='supplier']
    if not suppliers:
        p={'id':str(uuid4()),'kind':'supplier','nom':None,'sources':{},'approved':False,'reviewed':False}
        state.setdefault('partners',[]).append(p);suppliers=[p]
    review={'file_id':str(file_id),'filename':filename,'target_id':suppliers[0]['id'] if len(suppliers)==1 else None,'items':[]}
    state['document_review']=review
    for partner in suppliers:
        partner['approved']=False;partner['reviewed']=False
        partner['operation']={'status':'invalidated','document_review_required':True}
    grouped={}
    for candidate in report['candidates']:
        field=candidate['field'];choices=grouped.setdefault(field,[])
        if not any(equivalent(field,c['value'],candidate['value']) for c in choices):choices.append(candidate)
    for field,choices in grouped.items():
        existing=suppliers[0].get(field) if len(suppliers)==1 else None
        conflict=len(choices)>1 or existing not in (None,'') and not equivalent(field,existing,choices[0]['value'])
        reason='conflict' if conflict else 'ocr' if any(c['uncertain'] for c in choices) else None
        if review['target_id'] and not reason:
            if existing not in (None,''):continue  # Existing values are never silently replaced.
            try:set_field(state,field,choices[0]);continue
            except ValueError:reason='invalid'
        review['items'].append({'field':field,'choices':choices,'existing':existing,'reason':reason or 'selection'})
    return state

def table(report):
    def cell(value):return str(value).replace('|','／').replace('\n',' ')
    rows=['| Information | Valeur lue | Source | Relecture |','| --- | --- | --- | --- |']
    for c in report['candidates']:
        source=c['source'];rows.append('| '+document_fields.TITLES[c['field']]+' | '+cell(c['value'])+' | '+cell(source['filename'])+', page '+str(source['page'])+' | '+('À vérifier (OCR)' if c['uncertain'] else 'À relire')+' |')
    return '\n'.join(rows) if report['candidates'] else ''

def analyze(owner,conversation,file_id,revision):
    from app.services import conversation_chat as chat
    metadata=next((f for f in storage.files(owner,conversation) if f['id']==file_id),None)
    if not metadata:raise crud.CrudError('Fichier introuvable.',404)
    kind=FORMATS.get(Path(metadata['filename']).suffix.lower())
    if not kind:raise crud.CrudError('Lecture disponible pour PDF, PNG, JPEG, WEBP, TIFF et BMP.',422)
    if metadata['size_bytes']>MAX_BYTES:raise crud.CrudError('La lecture est limitée à 25 Mo et 8 pages par document.',422)
    with db.connection() as conn:
        conn.execute("SET LOCAL lock_timeout='5s'")
        row=chat.get_row(conn,owner,conversation)
        if row['revision']!=revision:raise crud.CrudError('La conversation a changé. Relancez la lecture.',409)
        if row['state'].get('_pending'):raise crud.CrudError('Attendez la fin de l’analyse avant de lire ce document.',409)
        pending=row['state'].get('document_review') or {}
        if pending.get('items') and pending.get('file_id')!=str(file_id):raise crud.CrudError('Terminez la relecture du document courant avant d’en lire un autre.',409)
        previous=conn.execute('SELECT report FROM chat_document_reads WHERE file_id=%s AND owner_id=%s',(file_id,owner)).fetchone()
    if previous:
        raw=previous['report']
        report={**raw,**document_fields.parse(raw,metadata['filename'],file_id)}
    else:
        data=storage.file(owner,conversation,file_id)
        raw=decode(bytes(data['content']),kind)
        report={**document_fields.parse(raw,metadata['filename'],file_id),'pages':raw['pages'],'reader_version':raw['reader_version'],'authority':'document_data_only'}
    with db.connection() as conn:
        conn.execute("SET LOCAL lock_timeout='5s'")
        row=chat.get_row(conn,owner,conversation,True)
        # Re-check file ownership/existence after decoding and serialize with file deletion.
        if not conn.execute('SELECT id FROM chat_files WHERE id=%s AND owner_id=%s AND conversation_id=%s FOR KEY SHARE',(file_id,owner,conversation)).fetchone():raise crud.CrudError('Le fichier a été supprimé pendant sa lecture.',409)
        conn.execute('INSERT INTO chat_document_reads(file_id,owner_id,conversation_id,report) VALUES(%s,%s,%s,%s) ON CONFLICT(file_id) DO UPDATE SET report=excluded.report WHERE chat_document_reads.owner_id=excluded.owner_id AND chat_document_reads.conversation_id=excluded.conversation_id',(file_id,owner,conversation,Jsonb(report)))
        state=row['state']
        if state.get('_pending'):raise crud.CrudError('Une analyse est en cours. Relancez la lecture ensuite.',409)
        pending=state.get('document_review') or {}
        if pending.get('items') and pending.get('file_id')!=str(file_id):raise crud.CrudError('Un autre document attend votre relecture.',409)
        if any((p.get('operation') or {}).get('status') in ('executing','succeeded','ambiguous','unverified','failed') for p in state.get('partners',[])):
            reply='Document lu. Consultez le résultat de la création précédente avant de modifier cette fiche.'
        else:
            state=apply_candidates(state,report,file_id,metadata['filename'])
            reply='Voici les valeurs lues dans le document.\n\n'+table(report)
            if not report['candidates']:reply='Je n’ai pas pu lire les informations utiles. Quel est le nom du fournisseur ? Vous pouvez aussi envoyer un document plus net.'
            elif state['document_review']['items'] or not state['document_review']['target_id']:reply+='\n\n'+question(state)
            else:
                from app.services.supplier_chat_flow import prepare_state
                reply+='\n\n'+prepare_state(state)
            if report['warnings']:reply+='\n\n'+ ' '.join('Page '+str(w['page'])+' : '+w['reason'] for w in report['warnings'])
        chat.save_conversation_context(conn,owner,conversation,state)
        conn.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s',(conversation,))
        chat.append(conn,conversation,'assistant',reply,{'document_read':True,'file_id':str(file_id),'sage_writes':0,'not_an_execution_approval':True})
    return chat.read(owner,conversation)

def reconcile(state):
    review=state.get('document_review') or {};target=next((p for p in state.get('partners',[]) if p['id']==review.get('target_id')),None)
    if not target:return
    # A natural chat correction supersedes pending document proposals for that field.
    review['items']=[i for i in review.get('items',[]) if not (target.get('sources',{}).get(i['field'])=='user_declared' and target.get(i['field'])!=i.get('existing'))]

def turn(owner,conversation,text,state):
    review=state.get('document_review')
    if not review:return None
    n=norm(text).strip(' .!');state=copy.deepcopy(state);review=state['document_review']
    if n in ('ignore ce document','ignore les propositions du document','annule la relecture du document'):
        state.pop('document_review',None)
        return {'state':state,'reply':'Les propositions en attente sont écartées. Les valeurs déjà affichées dans la fiche sont conservées.'}
    if review.get('target_id') and not review.get('items'):return None
    confirmations=('utilise les valeurs du document','confirme les valeurs du document','les valeurs du document sont correctes','je confirme la lecture')
    literal=None
    if review.get('items'):
        first=review['items'][0]
        choices=([{'value':first['existing'],'keep_existing':True}] if first.get('existing') not in (None,'') else [])+first['choices']
        phrase=re.sub(r'^(?:garde|utilise|retiens)\s+','',n)
        matches=[c for c in choices if equivalent(first['field'],phrase,c['value'])]
        if len(matches)==1:literal=matches[0]
    if n not in confirmations+('garde les valeurs actuelles',) and not re.fullmatch(r'(?:valeur )?[1-9]',n) and literal is None and review.get('target_id'):return None
    storage.file(owner,conversation,UUID(review['file_id']))  # Never use another owner's or a deleted file.
    if not review.get('target_id'):
        partners=[p for p in state.get('partners',[]) if p.get('kind')=='supplier']
        choice=re.fullmatch(r'(?:fournisseur )?([1-9])',n)
        selected=partners[int(choice[1])-1] if choice and int(choice[1])<=len(partners) else next((p for p in partners if norm(p.get('nom') or '')==n),None)
        if not selected:return None
        review['target_id']=selected['id']
        for item in review['items']:
            item['existing']=selected.get(item['field']);item['reason']='conflict' if item['existing'] not in (None,'') and not equivalent(item['field'],item['existing'],item['choices'][0]['value']) or len(item['choices'])>1 else 'ocr' if item['choices'][0]['uncertain'] else 'selection'
        return {'state':state,'reply':question(state) or 'Aucune valeur exploitable dans ce document. Indiquez les informations du fournisseur dans le chat.'}
    remaining=[]
    for index,item in enumerate(review['items']):
        selected=None
        if n in confirmations:
            if item['reason'] in ('ocr','selection') and len(item['choices'])==1:selected=item['choices'][0]
        elif n=='garde les valeurs actuelles':
            if item['reason']=='conflict' and item.get('existing') not in (None,''):continue
        elif index==0:
            if literal is not None:
                if literal.get('keep_existing'):continue
                selected=literal
            else:
                choices=([None] if item.get('existing') not in (None,'') else [])+item['choices']
                number=int(n.split()[-1])-1
                if number<len(choices):
                    selected=choices[number]
                    if selected is None:continue
        if selected:
            try:set_field(state,item['field'],selected);continue
            except ValueError:item['reason']='invalid'
        remaining.append(item)
    review['items']=remaining
    if remaining:return {'state':state,'reply':question(state)}
    return {'state':state,'prepare':True}
