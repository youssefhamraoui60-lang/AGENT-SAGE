"""Business draft fields, independent from any published SOAP write mapping."""
from pydantic import BaseModel, ConfigDict, Field,field_validator
from typing import Literal


class PartnerPatch(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    index:int|None=Field(default=None,ge=1,le=10)
    code:str|None=Field(default=None,min_length=1,max_length=15)
    nom:str|None=Field(default=None,min_length=1,max_length=100)
    nom_commercial:str|None=Field(default=None,max_length=100)
    intitule_court:str|None=Field(default=None,max_length=10)
    adresse:str|None=Field(default=None,max_length=250)
    pays:str|None=Field(default=None,max_length=70)
    devise:str|None=Field(default=None,max_length=3)
    email:str|None=Field(default=None,max_length=100)
    telephone:str|None=Field(default=None,max_length=40)
    identifiant_fiscal:str|None=Field(default=None,max_length=50)
    forme_juridique:str|None=Field(default=None,max_length=50)
    capital:str|None=Field(default=None,max_length=60)
    annee_creation:str|None=Field(default=None,pattern=r'^\d{4}$')
    rc:str|None=Field(default=None,max_length=50)
    ville_rc:str|None=Field(default=None,max_length=70)
    ice:str|None=Field(default=None,pattern=r'^\d{15}$')
    conditions_paiement:str|None=Field(default=None,max_length=70)
    statut:str|None=Field(default=None,max_length=30)
    societe:str|None=Field(default=None,max_length=5)
    site:str|None=Field(default=None,max_length=5)
    code_comptable:str|None=Field(default=None,max_length=10)
    dossier_cible:Literal['TEST','OB']|None=None
    categorie_fournisseur:str|None=Field(default=None,max_length=5)
    regime_taxe:str|None=Field(default=None,max_length=10)
    ville:str|None=Field(default=None,max_length=50)
    fax:str|None=Field(default=None,max_length=30)
    date_regularite:str|None=Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}$')
    type_montant:Literal['HT','TTC']|None=None
    type_montant_valeur:int|None=Field(default=None,ge=1,le=2)

class SupplierPatch(PartnerPatch):
    @field_validator('nom')
    @classmethod
    def supplier_identity_is_not_an_instruction(cls,value):
        from app.services.conversation_guardrails import invalid_supplier_name
        if value and invalid_supplier_name(value):raise ValueError('Indiquez la raison sociale du fournisseur, pas une consigne de conversation.')
        return value
    # Preserve a declared malformed numeric ICE in a draft so it can be corrected.
    # supplier_sql.parameters still requires exactly 15 digits before any SQL action.
    ice:str|None=Field(default=None,pattern=r'^[0-9]{1,30}$')
    # Preserve explicit oversized input for a clear SQL size diagnostic in TEST.
    # This never relaxes Sage's actual 10-character short-name constraint.
    intitule_court:str|None=Field(default=None,max_length=30)

