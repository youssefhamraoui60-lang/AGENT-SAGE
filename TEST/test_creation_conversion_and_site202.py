"""No repeated equality prompts; sole site 202 exempts supplier requirement."""
import sys,copy
from pathlib import Path
import pytest
from pydantic import ValidationError
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests'),str(ROOT/'TEST')]
from test_article_direct_sql import article,schema
from app.services import article_sql as sql,article_sql_dialogue as dialogue,unit_conversion_dialogue as flow,sage_crud as crud
from app.services.chat_model import Patch

def test_site_202_alone_does_not_require_supplier_or_principal():
 p=sql.article_plan(article(requested_sites=['202'],fournisseurs=[]),schema())
 assert p['summary']['flag_fournisseur']==1 and p['summary']['principal']==''
 assert not any(n['table']=='ITMBPS' for n in p['nodes'])
 for sites in (['201'],['202','201']):
  with pytest.raises(crud.CrudError,match='au moins un fournisseur'):sql.article_plan(article(requested_sites=sites,fournisseurs=[]),schema())

def test_equation_never_is_a_scalar_coefficient():
 with pytest.raises(ValidationError):Patch(coefficient_vente_declare='1 UN = 1000 L')

def test_user_confirmation_repairs_old_corrupt_scalar_and_stops_loop(monkeypatch):
 data=schema();data['units'].append({'UOM_0':'L'})
 monkeypatch.setattr(sql,'catalog',lambda *a,**k:copy.deepcopy(data))
 a=article(unite_vente='L',coefficient_vente_declare='1 UN = 1000 L',requested_sites=['202'],fournisseurs=[])
 s={'articles':[a],'supplier_target':'TEST'}
 for message in ('1 UN = 1000 L',"j’ai confirlmer 1 UN = 1000 L"):
  result=flow.creation_followup(message,s);s=result['state'];a=s['articles'][0]
  assert a['coefficient_vente_declare']=='1000'
  assert a['conversion_vente_declaree']['source_unit']=='UN'
  assert a['conversion_vente_declaree']['target_unit']=='L'
  assert 'Le sens est connu' in result['reply'] and 'Voulez-vous dire' not in result['reply']
  assert result['reply'].count('=')==1 and not a.get('approved')
 bad=flow.creation_followup('1 L = 1 UN = 1000 L',s)
 assert 'une seule égalité' in bad['reply']
 assert bad['state']['articles'][0]['coefficient_vente_declare']=='1000'

def test_corrupt_legacy_value_cannot_produce_recursive_equations():
 a=article(unite_vente='L',coefficient_vente_declare='1 UN = 1000 L')
 with pytest.raises(crud.CrudError) as error:sql.article_plan(a,schema())
 assert 'coefficient doit être un nombre' in error.value.code
 assert '1 L = 1 UN' not in error.value.code
