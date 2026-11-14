from decimal import Decimal,InvalidOperation
import re
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator

class ArticlePreparation(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,str_strip_whitespace=True)
    reference:str=Field(min_length=1,max_length=20)
    designation:str=Field(min_length=3,max_length=70)
    categorie:str=Field(min_length=1,max_length=5)
    unite_stock:str=Field(min_length=1,max_length=3)
    unite_achat:str=Field(min_length=1,max_length=3)
    unite_vente:str=Field(min_length=1,max_length=3)
    coefficient_achat:str=Field(min_length=1,max_length=20)
    coefficient_vente:str=Field(min_length=1,max_length=20)
    statut:Literal['1','2','3','4','5','6']|None=None
    gestion_stock:Literal['1','2','3']|None=None
    gestion_lots:str|None=Field(default=None,min_length=1,max_length=3)
    code_comptable:str|None=Field(default=None,min_length=1,max_length=10)

    @field_validator('reference')
    @classmethod
    def reference_valid(cls,value):
        if not re.fullmatch(r'[A-Za-z0-9_. -]+',value):raise ValueError('Reference contains unsupported characters')
        return value
    @field_validator('*')
    @classmethod
    def safe_text(cls,value):
        if value is None:return value
        if any(ord(char)<32 for char in value):raise ValueError('Control characters forbidden')
        return value
    @field_validator('coefficient_achat','coefficient_vente')
    @classmethod
    def coefficient_valid(cls,value):
        try: number=Decimal(value)
        except InvalidOperation:raise ValueError('Decimal coefficient required') from None
        if not number.is_finite() or number<=0 or number>=Decimal('100000') or number.as_tuple().exponent < -6:
            raise ValueError('Positive finite coefficient, at most 6 decimals')
        return format(number,'f')
