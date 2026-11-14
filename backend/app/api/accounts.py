from uuid import UUID
from urllib.parse import quote
from tempfile import SpooledTemporaryFile
from fastapi import APIRouter,Depends,Request,Response,HTTPException,Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel,ConfigDict,SecretStr,Field
from app.services import chat_auth as auth,chat_storage as storage
from app.api.chat import guarded,error

router=APIRouter(prefix='/api/v1/chat',tags=['Accounts and private storage'])
class Credentials(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email:str=Field(max_length=254)
    password:SecretStr=Field(max_length=128)
class Registration(Credentials):display_name:str=Field(max_length=80)
class Rename(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    title:str=Field(min_length=1,max_length=100)
class DraftEdit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)
    fields:dict[str,str|None]

@router.post('/auth/register',status_code=201)
@guarded
def register(body:Registration,request:Request,response:Response):
    return auth.register(request,response,body.email,body.display_name,body.password.get_secret_value())

@router.post('/auth/login')
@guarded
def login(body:Credentials,request:Request,response:Response):
    return auth.login(request,response,body.email,body.password.get_secret_value())

@router.post('/auth/logout')
@guarded
def logout(request:Request,response:Response):return auth.logout(request,response)

@router.get('/storage')
@guarded
def usage(user=Depends(auth.identity)):return storage.status(user['owner_id'])

@router.get('/storage/prepared-files')
@guarded
def prepared_files(user=Depends(auth.identity)):return {'files':storage.artifacts(user['owner_id'])}

@router.delete('/storage/prepared-files/{identifier}')
@guarded
def delete_prepared_files(identifier:UUID,user=Depends(auth.operator)):
    storage.artifacts(user['owner_id'],identifier,True)
    return {'deleted':True,'storage':storage.status(user['owner_id'])}

@router.get('/supplier-references')
@guarded
def references(user=Depends(auth.identity)):
    from app.services.supplier_sql import load_reference_labels
    return {'payments':[r for r in load_reference_labels() if r['kind']=='Paiement']}

@router.patch('/conversations/{identifier}')
@guarded
def rename(identifier:UUID,body:Rename,user=Depends(auth.operator)):
    storage.rename(user['owner_id'],identifier,body.title)
    return {'renamed':True}

@router.patch('/conversations/{identifier}/partners/{partner_id}')
@guarded
def edit_draft(identifier:UUID,partner_id:UUID,body:DraftEdit,user=Depends(auth.operator)):
    from app.services import conversation_chat as chat,supplier_sql,sage_crud as crud
    from app.schemas.conversation_entities import SupplierPatch
    from app.services import business_store as db
    allowed=set(supplier_sql.MAPPING.values())|{'fax'}
    if not body.fields or set(body.fields)-allowed:raise HTTPException(422,'Champs de fiche non autorisés.')
    try:values=SupplierPatch.model_validate({key:(value if value else None) for key,value in body.fields.items()}).model_dump(exclude_unset=True)
    except ValueError:raise HTTPException(422,'Vérifiez le format des champs de la fiche, notamment l’ICE à 15 chiffres.') from None
    with db.connection() as conn:
        row=chat.get_row(conn,user['owner_id'],identifier,True);state=row['state']
        if row['revision']!=body.revision or state.get('_pending'):raise crud.CrudError('La fiche a changé. Rechargez-la avant de modifier.',409)
        p=next((p for p in state.get('partners',[]) if p['id']==str(partner_id) and p['kind']=='supplier'),None)
        if not p:raise crud.CrudError('Fiche introuvable.',404)
        if (p.get('operation') or {}).get('status') in ('executing','succeeded','ambiguous','unverified','failed'):raise crud.CrudError('Consultez le résultat de création avant de modifier cette fiche.',409)
        p.update(values);p['approved']=False;p['reviewed']=False;p['operation']={'status':'invalidated'}
        for key in values:p.setdefault('sources',{})[key]='user_declared'
        chat.save_conversation_context(conn,user['owner_id'],identifier,state)
        conn.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s',(identifier,))
        chat.append(conn,identifier,'assistant','La fiche a été modifiée. Vérifiez les nouvelles informations avant de confirmer sa création.',{'manual_draft_edit':True})
    return chat.read(user['owner_id'],identifier)

@router.delete('/conversations/{identifier}')
@guarded
def delete(identifier:UUID,user=Depends(auth.operator)):
    storage.delete(user['owner_id'],identifier)
    return {'deleted':True,'storage':storage.status(user['owner_id'])}

@router.get('/conversations/{identifier}/files')
@guarded
def files(identifier:UUID,user=Depends(auth.identity)):return {'files':storage.files(user['owner_id'],identifier)}

@router.post('/conversations/{identifier}/files',status_code=201)
async def upload(identifier:UUID,request:Request,filename:str=Query(min_length=1,max_length=200),user=Depends(auth.operator)):
    # Authorize before reading the body. Disk spool bounds RAM during transfer.
    try:
        await run_in_threadpool(storage.files,user['owner_id'],identifier)
        available=await run_in_threadpool(storage.status,user['owner_id'])
        if available['full']:raise HTTPException(507,'Votre espace de 200 Mo est plein. Supprimez des données pour continuer.')
        total=0
        with SpooledTemporaryFile(max_size=1024*1024) as temporary:
            async for chunk in request.stream():
                total+=len(chunk)
                if total>min(storage.LIMIT,available['remaining_bytes']):raise HTTPException(507,'Ce fichier dépasse votre espace disponible.')
                temporary.write(chunk)
            temporary.seek(0)
            return await run_in_threadpool(storage.upload,user['owner_id'],identifier,filename,request.headers.get('content-type','application/octet-stream'),temporary.read())
    except HTTPException:raise
    except Exception as exc:raise error(exc) from None

@router.get('/conversations/{identifier}/files/{file_id}')
@guarded
def download(identifier:UUID,file_id:UUID,user=Depends(auth.identity)):
    row=storage.file(user['owner_id'],identifier,file_id)
    return Response(bytes(row['content']),media_type='application/octet-stream',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['filename'],safe=''),'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})

class DocumentAnalysis(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)

@router.post('/conversations/{identifier}/files/{file_id}/analyze')
@guarded
def analyze_document(identifier:UUID,file_id:UUID,body:DocumentAnalysis,user=Depends(auth.operator)):
    from app.services.chat_documents import analyze
    return analyze(user['owner_id'],identifier,file_id,body.revision)

@router.delete('/conversations/{identifier}/files/{file_id}')
@guarded
def delete_file(identifier:UUID,file_id:UUID,user=Depends(auth.operator)):
    storage.file(user['owner_id'],identifier,file_id,True)
    return {'deleted':True,'storage':storage.status(user['owner_id'])}
