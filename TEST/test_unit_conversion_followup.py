"""A coefficient is durable user data, never an invented unit equivalence."""
import sys,copy,asyncio
from pathlib import Path
from uuid import uuid4
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests'),str(ROOT/'TEST')]
from app.services import unit_conversion_dialogue as flow,conversation_state,conversation_tools as engine,modification_actions

def state():
 return {'supplier_target':'TEST','modification_drafts':[{'id':str(uuid4()),'resource':'article','code':'NEG_CAF_778XT8_3XLL','current':{'stock_unit':'UN','purchase_unit':'UN','sale_unit':'UN'},'changes':{'stock_unit':'M2','sale_unit':{'code':'RLX'}},'approved':True,'sensitive_approved':True,'operation':{'status':'blocked','message':'Old repeated blocker'}}]}

def test_exact_reported_coefficient_followups_keep_units_direction_and_json():
 s=state();original=copy.deepcopy(s);identifier=s['modification_drafts'][0]['id'];modification_actions.PERMITS[identifier]={'old':'permit'}
 first=flow.followup('le cofission est  1000 POUR UN  VERe RLX',s)
 assert s==original
 s=first['state'];d=s['modification_drafts'][0]
 r=d['unit_conversion_requests'][-1]
 assert (r['coefficient'],r['source_unit'],r['target_unit'])==('1000','UN','RLX')
 assert '1 UN = 1000 RLX' in first['reply'] and '1 RLX = 1000 UN' in first['reply'] and 'UN / M2' in first['reply']
 assert not d['approved'] and identifier not in modification_actions.PERMITS
 second=flow.followup('conversion  1000',s);d=second['state']['modification_drafts'][0]
 assert len(d['unit_conversion_requests'])==1 and d['changes']==original['modification_drafts'][0]['changes']
 assert d['operation']['status']=='needs_input' and 'Appel non validé' not in second['reply']
 exported=conversation_state.project(second['state'],'test')
 assert exported['operations'][0]['unit_conversion_requests'][0]['coefficient']=='1000'
 third=flow.followup('1 RLX = 1000 UN',second['state'])
 assert third['state']['modification_drafts'][0]['unit_conversion_requests'][-1]['status']=='declared_equivalence'
 assert 'UN / M2' in third['reply'] and 'ne modifie pas' in third['reply']

def test_number_alone_never_infers_direction_or_units():
 result=flow.followup('conversion 1000',state())
 r=result['state']['modification_drafts'][0]['unit_conversion_requests'][0]
 assert r['source_unit'] is None and r['target_unit'] is None
 assert 'Entre quelles unités' in result['reply']

@pytest.mark.parametrize('text',['1M2 = 1000 UN','1 M2=1000UN','1M2=1000UN'])
def test_compact_equivalence_and_technical_limit(text):
 result=flow.followup(text,state());d=result['state']['modification_drafts'][0]
 assert d['unit_conversion_requests'][-1]['source_unit']=='M2'
 assert d['operation']['status']=='blocked'
 assert 'est renseignée' in result['reply'] and 'blocage est technique' in result['reply']
 assert 'reste à préciser' not in result['reply']

def test_exact_user_sequence_detects_opposite_contradictory_equations():
 s=state()
 for text in ('1M2 = 1000 UN','1 UN = 1000 RLX','1 UN = 1000 M2'):
  result=flow.followup(text,s);s=result['state']
 d=s['modification_drafts'][0]
 assert d['unit_conversion_conflicts'] and 'contredit' in result['reply']
 assert d['operation']['status']=='blocked'
 corrected=flow.followup('corrige : 1 UN = 1000 M2',s)
 d=corrected['state']['modification_drafts'][0]
 assert not d['unit_conversion_conflicts'] and d['unit_conversion_history']
 assert 'blocage est technique' in corrected['reply']
 assert any(r['target_unit']=='RLX' for r in d['unit_conversion_requests'])

def test_known_stock_equivalence_is_not_asked_again_on_sale_followup():
 s=flow.followup('1M2 = 1000 UN',state())['state']
 result=flow.followup('1 UN = 1000 RLX',s)
 assert 'reste à préciser' not in result['reply']
 assert 'relation UN / M2 est renseignée' in result['reply']

def test_verify_does_not_replace_precise_blocker_or_reread_unchanged_data(monkeypatch):
 s=flow.followup('1M2 = 1000 UN',state())['state'];d=s['modification_drafts'][0];before=copy.deepcopy(d['operation'])
 monkeypatch.setattr(modification_actions.service,'catalog',lambda *a,**k:pytest.fail('No repeated SQL for unchanged blocked conversion'))
 modification_actions.prepare_draft(d)
 assert d['operation']==before and not d['approved']

def test_consistent_inverse_is_not_a_contradiction_and_repeat_keeps_equivalence():
 s=flow.followup('1M2=1000UN',state())['state']
 s=flow.followup('1 UN = 0,001 M2',s)['state']
 assert not s['modification_drafts'][0]['unit_conversion_conflicts']
 result=flow.followup('conversion 0,001',s)
 assert result['state']['modification_drafts'][0]['operation']['status']=='blocked'
 assert 'voulez-vous dire' not in result['reply']

@pytest.mark.parametrize('text',['bonjour','conversion -1','conversion 0','conversion 1000 puis annule','conversion 1000 et modifie le fournisseur','1 RLX = 1000 KG'])
def test_out_of_scope_or_unsafe_input_not_intercepted(text):
 assert flow.followup(text,state()) is None

def test_multiple_pending_articles_require_target():
 s=state();s['modification_drafts'].append({**copy.deepcopy(s['modification_drafts'][0]),'id':str(uuid4()),'code':'OTHER'})
 assert flow.followup('conversion 1000',s) is None

def test_same_session_unit_target_is_read_and_reused(monkeypatch):
 s=state();s['modification_drafts']=[]
 s['articles']=[{'id':'created','code_article':'NEG_CAF_778XT8_3XLL','operation':{'status':'succeeded'}}]
 def read(args,changed,text):
  assert args.code=='NEG_CAF_778XT8_3XLL'
  return {'ok':True,'code':args.code,'fields':{'unite':'UN','unite_achat':'UN','unite_vente':'UN'}}
 monkeypatch.setattr(engine,'read',read)
 result=asyncio.run(engine.turn(None,None,'je veux corriger la UN de mon articele',s,[]))
 assert result['phase']=='unit_target_followup' and 'stock UN' in result['reply']
 assert len(result['state']['modification_drafts'])==1

def test_native_primary_never_sends_coefficient_followup_to_model(monkeypatch):
 async def forbidden(*a,**k):pytest.fail('Literal follow-up must not call the model or reprepare SQL')
 monkeypatch.setattr(engine.ai_provider,'chat',forbidden,raising=False)
 result=asyncio.run(engine.turn(None,None,'conversion 1000',state(),[]))
 assert result['phase']=='unit_conversion_followup'

def test_batch_tool_for_verified_single_article_preserves_both_scopes(monkeypatch):
 s={'supplier_target':'TEST','tool_read_results':[{'ok':True,'resource':'article','folder':'TEST','code':'NEG_CAF_778XT8_3XLL','name':'CAF 778XT8 3XLL'}]}
 def prepare(d):
  d.update(operation={'status':'blocked','message':'Conversions à vérifier'})
  return d
 monkeypatch.setattr(modification_actions,'prepare_draft',prepare)
 monkeypatch.setattr(engine.settings,'sage_modification_enabled',True)
 result=engine.dispatch('request_article_unit_batch',engine.BatchUnits(query='NEG_CAF_778XT8_3XLL',unit='M2',unit_scope='stock',evidence='unités dois m2 et le vente dois RLX'),s,'unités dois m2 et le vente dois RLX')
 assert result['ok'] and len(s['modification_drafts'])==1 and not s.get('batch_modification_requests')
 assert s['modification_drafts'][0]['changes']=={'stock_unit':'M2','sale_unit':{'code':'RLX'}}
