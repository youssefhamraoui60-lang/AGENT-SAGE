from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator,SecretStr

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,str_strip_whitespace=True)

class PublishedField(Strict):
    group:str=Field(pattern=r'^[A-Z][A-Z0-9_]{0,39}$')
    name:str=Field(pattern=r'^[A-Z][A-Z0-9_]{0,39}$')
    value:str|list[str]
    row:int|None=Field(default=None,ge=1,le=999)
    @field_validator('value')
    @classmethod
    def bounded(cls,value):
        values=value if isinstance(value,list) else [value]
        if len(values)>100 or any(len(v)>2000 or any(ord(c)<32 for c in v) for v in values):raise ValueError('Invalid field content')
        return value

class Preparation(Strict):
    action:Literal['create','update']
    keys:dict[str,str]=Field(min_length=1,max_length=2)
    fields:list[PublishedField]=Field(min_length=1,max_length=60)
    @field_validator('keys')
    @classmethod
    def safe_keys(cls,value):
        import re
        if any(not re.fullmatch(r'[A-Z][A-Z0-9_]{0,30}',k) or not re.fullmatch(r'[A-Za-z0-9_./ -]{1,20}',v) for k,v in value.items()):raise ValueError('Invalid record key')
        if 'STOFCY' in value and not re.fullmatch(r'[A-Za-z0-9_. -]{1,5}',value['STOFCY']):raise ValueError('Invalid site code')
        return value
    @model_validator(mode='after')
    def unique_fields(self):
        paths=[(v.group,v.name,v.row) for v in self.fields]
        if len(set(paths))!=len(paths):raise ValueError('Duplicate field path')
        return self

class Approval(Strict):
    digest:str=Field(pattern=r'^[a-f0-9]{64}$')
    confirm:Literal[True]
    actor:str=Field(min_length=2,max_length=100)
    reason:str=Field(min_length=8,max_length=500)
    @field_validator('confirm',mode='before')
    @classmethod
    def explicit_boolean(cls,value):
        if value is not True:raise ValueError('Explicit boolean confirmation required')
        return value

class Execution(BaseModel):
    model_config=ConfigDict(extra='forbid')
    operation_id:UUID
    approval_token:SecretStr=Field(min_length=1,max_length=256)
