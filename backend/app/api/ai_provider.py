from uuid import UUID
from typing import Literal
from fastapi import APIRouter,Depends
from pydantic import BaseModel,ConfigDict,Field
from app.services import chat_auth as auth,conversation_chat as chat,ai_provider,business_store as db,sage_crud as crud
from app.api.chat import guarded
router=APIRouter(prefix='/api/v1/chat',tags=['Private AI provider'])

@router.get('/ai/status')
@guarded
def status(user=Depends(auth.identity)):return ai_provider.summary(user['owner_id'])

class Mode(BaseModel):
    model_config=ConfigDict(extra='forbid')
    mode:Literal['auto','local']
    revision:int=Field(ge=1)

@router.post('/conversations/{identifier}/ai-mode')
@guarded
def mode(identifier:UUID,body:Mode,user=Depends(auth.operator)):
    with db.connection() as conn:
        row=chat.get_row(conn,user['owner_id'],identifier,True)
        if row['revision']!=body.revision or row['state'].get('_pending'):raise crud.CrudError('Une analyse est en cours ou la conversation a changé.',409)
        state=row['state'];state['ai_mode']=body.mode
        chat.save_conversation_context(conn,user['owner_id'],identifier,state)
        conn.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s',(identifier,))
    return chat.read(user['owner_id'],identifier)
