from uuid import UUID,uuid4
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from fastapi import APIRouter,Depends
from psycopg.types.json import Jsonb
from app.services import chat_auth as auth,business_store as db,conversation_chat as chat,article_sql
from app.services.chat_article_sql_actions import action
from app.api.chat import guarded,Action
from app.core.config import settings
router=APIRouter(prefix='/api/v1/chat/conversations/{identifier}',tags=['Confirmed direct SQL articles TEST'])
class Category(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    revision:int=Field(ge=1)
    code:str=Field(pattern=r'^[A-Z0-9_]{1,5}$')
    designation:str=Field(min_length=1,max_length=100)
    nom_court:str=Field(min_length=1,max_length=30)
    modele:str=Field(pattern=r'^[A-Z0-9_]{1,5}$')
    gestion_stock:Literal[1,2,3]
    achete:Literal[1,2]
    vendu:Literal[1,2]
    fabrique:Literal[1,2]
    livrable:Literal[1,2]
    sous_traite:Literal[1,2]
    receptionne:Literal[1,2]
    unite:str=Field(min_length=1,max_length=10)
    code_comptable:str=Field(min_length=1,max_length=20)
    taxe:str=Field(min_length=1,max_length=20)

@router.post('/categories/drafts')
@guarded
def category_draft(identifier:UUID,body:Category,user=Depends(auth.operator)):
    if not settings.sage_article_sql_enabled:article_sql.fail('Service SQL articles désactivé.')
    with db.connection() as conn:
        row=chat.get_row(conn,user['owner_id'],identifier,True)
        if row['revision']!=body.revision:raise article_sql.crud.CrudError('La conversation a changé.',409)
        state=row['state']
        folder=article_sql.supplier_sql.target(state.get('supplier_target','TEST'))
        draft=body.model_dump(exclude={'revision'});draft['id']=str(uuid4());draft['dossier_cible']=folder
        try:draft['operation']=article_sql.prepare(draft,'category')
        except article_sql.crud.CrudError as exc:draft['operation']={'status':'blocked','message':exc.code,'transport':'direct_sql_article'}
        state.setdefault('category_drafts',[]).append(draft)
        chat.save_conversation_context(conn,user['owner_id'],identifier,state)
        conn.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s AND owner_id=%s',(identifier,user['owner_id']))
        message='La catégorie '+body.code+' est préparée. Relisez ses paramètres puis confirmez sa creation dans '+folder+'.' if draft['operation']['status']=='prepared' else draft['operation']['message']
        chat.append(conn,identifier,'assistant',message,{'category_draft':True,'sage_writes':0})
    return chat.read(user['owner_id'],identifier)

@router.post('/categories/{category_id}/{step}')
@guarded
def category_action(identifier:UUID,category_id:UUID,step:str,body:Action,user=Depends(auth.operator)):
    return action(user['owner_id'],identifier,category_id,step,body.revision,body.confirm,resource='category')
