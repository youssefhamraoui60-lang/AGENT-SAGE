from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,StrictBool
from fastapi import APIRouter,Depends
from app.services import chat_auth as auth,learning,learning_training as training
from app.api.chat import guarded

router=APIRouter(prefix='/api/v1/chat/learning',tags=['Validated memory and knowledge'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Item(Strict):
    kind:Literal['preference','rule','correction','document','example']
    title:str=Field(min_length=1,max_length=150)
    content:str=Field(min_length=1,max_length=20000)
    source:str=Field(default='user',min_length=1,max_length=400)
    input_text:str=Field(default='',max_length=12000)
    expected_delta:dict|None=None
class Review(Strict):
    status:Literal['validated','rejected','superseded']
    confirm:StrictBool
class Feedback(Strict):
    message_id:int=Field(ge=1)
    verdict:Literal['correct','incorrect']
    expected:str=Field(default='',max_length=20000)
    confirm:StrictBool
class Schedule(Strict):
    enabled:StrictBool=True
    min_examples:int=Field(default=50,ge=5,le=100000)
    interval_hours:int=Field(default=168,ge=1,le=8760)
class Live(Strict):
    kind:Literal['stock','balance','code']
    code:str=Field(min_length=1,max_length=30)
    site:str=Field(default='',max_length=30)
    company:str=Field(default='',max_length=30)
    ledger:str=Field(default='',max_length=30)
    date_from:str=Field(default='',max_length=10)
    date_to:str=Field(default='',max_length=10)
class ProposalFeedback(Strict):
    message_id:int=Field(ge=1)
    verdict:Literal['correct','incorrect']
    expected:str=Field(default='',max_length=20000)
class ChatMemoryAction(Strict):
    action:Literal['validate','edit','reject','forget']
    sha:str=Field(min_length=64,max_length=64)
    content:str=Field(default='',max_length=20000)
    confirm:StrictBool=False

class MethodProposal(Strict):
    company_id:UUID
    title:str=Field(min_length=1,max_length=150)
    content:str=Field(min_length=1,max_length=6000)
class MethodReview(Strict):
    activate:StrictBool=False
    confirm:StrictBool=False
    evaluation:dict=Field(default_factory=dict)

@router.post('/automatic-methods/{identifier}/disable')
@guarded
def disable_automatic_method(identifier:UUID,user=Depends(auth.operator)):
    from app.services.learning_auto import disable
    return disable(user['owner_id'],identifier)

@router.post('/methods')
@guarded
def method_proposal(body:MethodProposal,user=Depends(auth.operator)):
    from app.services.learning_methods import propose
    return propose(user['owner_id'],body.company_id,body.title,body.content)

@router.post('/methods/{identifier}/review')
@guarded
def method_review(identifier:UUID,body:MethodReview,user=Depends(auth.operator)):
    from app.services.learning_methods import review
    from app.services.sage_crud import CrudError
    if not body.confirm:raise CrudError('Confirmation requise.',422)
    return review(user['owner_id'],identifier,body.activate,body.evaluation)

@router.post('/conversations/{conversation}/feedback')
@guarded
def feedback_proposal(conversation:UUID,body:ProposalFeedback,user=Depends(auth.operator)):
    from app.services.learning_chat import feedback_proposal
    return feedback_proposal(user['owner_id'],conversation,body.message_id,body.verdict,body.expected)

@router.post('/conversations/{conversation}/items/{identifier}/action')
@guarded
def chat_memory_action(conversation:UUID,identifier:UUID,body:ChatMemoryAction,user=Depends(auth.operator)):
    from app.services.learning_chat import action
    return action(user['owner_id'],conversation,identifier,body.action,body.content,body.sha,body.confirm)

@router.get('')
@guarded
def status(user=Depends(auth.identity)):return learning.status(user['owner_id'])
@router.post('/items')
@guarded
def item(body:Item,user=Depends(auth.operator)):
    payload={}
    if body.input_text:payload['input_normalized']=learning.normalized(learning.clean(body.input_text))
    if body.expected_delta is not None:payload['expected_delta']=body.expected_delta
    return learning.create_item(user['owner_id'],body.kind,body.title,body.content,body.source,payload)
@router.post('/items/{identifier}/review')
@guarded
def review(identifier:UUID,body:Review,user=Depends(auth.operator)):
    if body.confirm is not True:
        from app.services.sage_crud import CrudError
        raise CrudError('Validation explicite requise.',422)
    return learning.review(user['owner_id'],identifier,body.status)
@router.post('/feedback')
@guarded
def feedback(body:Feedback,user=Depends(auth.operator)):
    return learning.feedback(user['owner_id'],body.message_id,body.verdict,body.expected,body.confirm)
@router.put('/schedule')
@guarded
def schedule(body:Schedule,user=Depends(auth.operator)):
    return training.configure(user['owner_id'],body.enabled,body.min_examples,body.interval_hours)
@router.post('/export')
@guarded
def export(user=Depends(auth.operator)):return training.export_dataset(user['owner_id'],force=True)

@router.post('/documents/{identifier}/import')
@guarded
def import_document(identifier:UUID,user=Depends(auth.operator)):return learning.import_document(user['owner_id'],identifier)

@router.post('/live')
@guarded
def live(body:Live,user=Depends(auth.operator)):
    from app.services.learning_live import read
    return read(**body.model_dump())
