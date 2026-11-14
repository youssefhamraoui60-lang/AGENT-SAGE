from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

FieldName = Literal['designation', 'unite', 'categorie', 'fournisseur']

class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    demande: str = Field(min_length=3, max_length=4000)

class Extraction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    designation: str | None
    unite: str | None = Field(description='Code unite explicitement fourni, par exemple M3. Le mot unite seul sans code signifie null, jamais la chaine unite.')
    categorie: str | None
    fournisseur: str | None
    confiance: float = Field(ge=0, le=1)
    champs_manquants: list[FieldName]

    @model_validator(mode='after')
    def missing_fields_agree(self):
        actual = {k for k in ('designation','unite','categorie','fournisseur') if getattr(self,k) is None}
        if any(isinstance(getattr(self,k),str) and not getattr(self,k).strip() for k in ('designation','unite','categorie','fournisseur')):
            raise ValueError('Les champs vides doivent etre null')
        if set(self.champs_manquants) != actual or len(self.champs_manquants) != len(actual):
            raise ValueError('champs_manquants incoherent')
        return self
