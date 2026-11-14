"""Strict, non-executable proposals. All approval state is computed server-side."""
from typing import Literal
from uuid import UUID
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Intent = Literal['create_article','create_supplier','check_article','check_supplier','update_article_request','unknown']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True,str_strip_whitespace=True)

class TextFields(StrictModel):
    @field_validator('*')
    @classmethod
    def valid_text(cls,value):
        if isinstance(value,str):
            if not value or len(value)>500 or re.search(r'[\x00-\x1f\x7f]',value):
                raise ValueError('Empty, oversized or control-character field')
            if value.casefold() in {'null','none','undefined','n/a'}:
                raise ValueError('Use JSON null, not a placeholder string')
        return value

class Article(TextFields):
    designation: str | None
    unite: str | None
    categorie: str | None
    famille: str | None
    fournisseur: str | None
    code_fournisseur: str | None
    code_article: str | None
    site: str | None

class Supplier(TextFields):
    nom: str | None
    code_fournisseur: str | None
    informations: dict[str,str] = Field(max_length=20)

    @field_validator('informations')
    @classmethod
    def bounded_information(cls,value):
        for key,item in value.items():
            if len(key)>80 or len(item)>500 or re.search(r'[\x00-\x1f\x7f]',key+item):
                raise ValueError('Invalid supplier information')
        return value

class ProposalData(StrictModel):
    intention: Intent
    articles: list[Article] = Field(max_length=20)
    fournisseurs: list[Supplier] = Field(max_length=20)
    ambigu: bool
    questions: list[str] = Field(max_length=20)

class Proposal(ProposalData):
    @model_validator(mode='after')
    def complete_intent(self):
        if any(all(value is None for value in item.model_dump().values()) for item in self.articles):
            raise ValueError('An entirely empty article is not an extracted entity')
        if any(item.nom is None and item.code_fournisseur is None and not item.informations for item in self.fournisseurs):
            raise ValueError('An entirely empty supplier is not an extracted entity')
        if self.intention in ('create_article','check_article') and not self.articles:
            raise ValueError('Article intent requires articles')
        if self.intention in ('create_supplier','check_supplier') and not self.fournisseurs:
            raise ValueError('Supplier intent requires suppliers')
        if any(len(question)>500 for question in self.questions):
            raise ValueError('Question too long')
        return self

class AnalyzeInput(StrictModel):
    demande: str = Field(min_length=3,max_length=8000)

class ValidateInput(StrictModel):
    proposition: Proposal

class DuplicateInput(StrictModel):
    designation: str = Field(min_length=2,max_length=500)
    type_objet: Literal['article','supplier'] = 'article'
    limit: int = Field(default=5,ge=1,le=20)

class ArticlePatch(TextFields):
    designation: str | None = None
    unite: str | None = None
    categorie: str | None = None
    famille: str | None = None
    fournisseur: str | None = None
    code_fournisseur: str | None = None
    code_article: str | None = None
    site: str | None = None

class SupplierPatch(TextFields):
    nom: str | None = None
    code_fournisseur: str | None = None
    informations: dict[str,str] | None = None

class ArticleChange(StrictModel):
    index: int = Field(ge=0,le=19)
    champs: ArticlePatch

class SupplierChange(StrictModel):
    index: int = Field(ge=0,le=19)
    champs: SupplierPatch

class CorrectionInput(StrictModel):
    revision_attendue: int = Field(ge=1)
    acteur: str = Field(min_length=1,max_length=100)
    raison: str = Field(min_length=3,max_length=1000)
    articles: list[ArticleChange] = Field(default_factory=list,max_length=20)
    fournisseurs: list[SupplierChange] = Field(default_factory=list,max_length=20)
    lever_ambiguite: bool = False

    @model_validator(mode='after')
    def changes_present(self):
        if not self.articles and not self.fournisseurs and not self.lever_ambiguite:
            raise ValueError('At least one correction required')
        for changes in (self.articles,self.fournisseurs):
            if len({change.index for change in changes})!=len(changes):
                raise ValueError('Duplicate correction index')
            if any(not change.champs.model_fields_set for change in changes):
                raise ValueError('Empty correction')
        return self

class DecisionInput(StrictModel):
    revision_attendue: int = Field(ge=1)
    decision: Literal['approve','reject']
    acteur: str = Field(min_length=1,max_length=100)
    raison: str = Field(min_length=3,max_length=1000)

class DuplicateCandidate(StrictModel):
    code: str
    designation: str
    score: float = Field(ge=0,le=1)
    correspondance: Literal['exact','normalized','approximate']
    source: str
    scope: Literal['local_only']

class ArticleEvaluation(StrictModel):
    extrait: Article
    confirme: dict[str,str]
    sources_confirmation: dict[str,str]
    statut_validation: Literal['ready_for_human_review','needs_information']
    champs_manquants: list[str]
    erreurs: list[str]
    avertissements: list[str]
    doublons: list[DuplicateCandidate]

class SupplierEvaluation(StrictModel):
    extrait: Supplier
    confirme: dict[str,str]
    statut_validation: Literal['ready_for_human_review','needs_information']
    champs_manquants: list[str]
    erreurs: list[str]
    avertissements: list[str]
    doublons: list[DuplicateCandidate]

class Evaluation(StrictModel):
    articles: list[ArticleEvaluation]
    fournisseurs: list[SupplierEvaluation]
    business_valid: bool
    scope: Literal['local_only']
    sage_x3_checked: Literal[False]
    execution_sage_autorisee: Literal[False]
    reference_count: int
    reference_status: Literal['empty','configured']
    questions: list[str]
    ambigu: bool
    rules_version: str
    rules_validated: bool
    rules_provenance: str

class RequestResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    statut: Literal['processing','pending_approval','needs_clarification','analysis_failed','approved_locally','rejected']
    revision: int
    demande_originale: str
    extraction_initiale: ProposalData | None
    proposition: ProposalData | None
    controle: Evaluation | None
    provenance: dict
    historique: list[dict]
    execution_sage_autorisee: Literal[False] = False
