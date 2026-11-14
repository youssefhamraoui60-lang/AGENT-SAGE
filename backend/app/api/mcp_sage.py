from uuid import UUID
from fastapi import APIRouter,Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel,ConfigDict,Field
from app.services import chat_auth as auth
from app.api.chat import error
from app.mcp_sage import gateway
from app.mcp_sage.catalog import CATALOG
router=APIRouter(prefix='/api/v1/chat/conversations/{identifier}/mcp',tags=['MCP read-only TEST pilot'])
class Call(BaseModel):
    model_config=ConfigDict(extra='forbid')
    arguments:dict=Field(default_factory=dict)

@router.get('/tools')
async def tools(identifier:UUID,user=Depends(auth.identity)):
    try:
        await run_in_threadpool(gateway.authorize,user['owner_id'],identifier)
        return {**gateway.manifest(),'schemas':{name:entry[0].model_json_schema() for name,entry in CATALOG.items()}}
    except Exception as exc:raise error(exc) from None

@router.post('/tools/{name}')
async def call(identifier:UUID,name:str,body:Call,user=Depends(auth.operator)):
    try:return await gateway.dispatch(user['owner_id'],identifier,name,body.arguments)
    except Exception as exc:raise error(exc) from None
