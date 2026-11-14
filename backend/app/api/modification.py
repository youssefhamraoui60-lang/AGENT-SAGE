from contextlib import nullcontext
from uuid import UUID
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,StrictBool
from fastapi import APIRouter,Depends,Query
from app.services import chat_auth as auth,modification_actions as service,business_store as db,conversation_chat as chat
from app.services.chat_storage import execution_space
from app.api.chat import guarded
router=APIRouter(prefix='/api/v1/chat/conversations/{identifier}',tags=['Confirmed modifications TEST only'])
class Draft(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)
    resource:Literal['article','supplier','unit']
    code:str=Field(pattern=r'^[A-Za-z0-9_./-]{1,30}$')
    changes:dict=Field(min_length=1,max_length=20)
class Action(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)
    confirm:StrictBool=False
    sensitive_confirm:StrictBool=False

@router.post('/modifications/drafts')
@guarded
def draft(identifier:UUID,body:Draft,user=Depends(auth.operator)):
    return service.add(user['owner_id'],identifier,body.revision,body.resource,body.code,body.changes)

@router.post('/modifications/{draft_id}/{step}')
@guarded
def action(identifier:UUID,draft_id:UUID,step:str,body:Action,user=Depends(auth.operator)):
    with execution_space(user,identifier) if step=='execute' else nullcontext():
        return service.action(user['owner_id'],identifier,draft_id,step,body.revision,body.confirm,body.sensitive_confirm)

@router.get('/modifications/audit')
@guarded
def audit(identifier:UUID,before_id:int|None=Query(default=None,ge=1),user=Depends(auth.identity)):
    with db.connection() as conn:
        chat.get_row(conn,user['owner_id'],identifier)
        rows=conn.execute('SELECT id,draft_id,operation_id,event,payload,created_at FROM chat_modification_audit WHERE owner_id=%s AND conversation_id=%s AND (%s::bigint IS NULL OR id<%s::bigint) ORDER BY id DESC LIMIT 100',(user['owner_id'],identifier,before_id,before_id)).fetchall()
    return {'folder':'TEST','events':rows,'next_before_id':rows[-1]['id'] if len(rows)==100 else None}
