"""F1/F2 reproductions. Real chat+PG, simulated providers/Sage, no writes."""
import copy,pytest
from test_native_conversation_tools import native_chat,campaign,fixture,simulated,call,native,say,fact,send
from test_conversation_chat import create
from app.services import conversation_tools as engine,chat_tools

def test_f1_progressive_invalid_ice_city_and_corrected_ice_keep_one_draft(native_chat):
 c,q,_,_,attempts,_=native_chat;s=create(c)
 steps=[('créer un fournisseur BOUCHAIB FF ice 56765642345672',[fact('nom','BOUCHAIB FF'),fact('ice','56765642345672')]),('ajouter aussi le la ville berrchide',[fact('ville','berrchide')]),('le ice 123456789012345',[fact('ice','123456789012345')])]
 identity=None
 for text,fields in steps:
  q.extend([native(call('prepare_draft',resource='supplier',mode='new',fields=fields)),say('Vos informations sont conservées.')]);s=send(c,s,text)
  assert len(s['state']['partners'])==1
  p=s['state']['partners'][0];identity=identity or p['id'];assert p['id']==identity and p['nom']=='BOUCHAIB FF'
 assert p['ville']=='berrchide' and p['ice']=='123456789012345'
 assert p['operation']['status']=='prepared' and all(not a['execute'] for a in attempts)

def test_unchanged_history_fields_can_be_repeated_but_new_values_need_current_evidence(native_chat):
 c,q,_,_,_,_=native_chat;s=create(c)
 q.extend([native(call('prepare_draft',resource='supplier',mode='new',fields=[fact('nom','BOUCHAIB FF')])),say('Fiche conservée.')]);s=send(c,s,'crée BOUCHAIB FF')
 q.extend([native(call('prepare_draft',resource='supplier',mode='new',fields=[fact('nom','BOUCHAIB FF','BOUCHAIB FF'),fact('ville','Rabat')])),say('Ville notée.')]);s=send(c,s,'la ville est Rabat')
 assert len(s['state']['partners'])==1 and s['state']['partners'][0]['ville']=='Rabat'
 q.extend([native(call('prepare_draft',resource='supplier',mode='update',fields=[fact('ville','Agadir','Agadir')])),say('Je conserve la ville donnée.')]);s=send(c,s,'ne change pas sa ville')
 assert s['state']['partners'][0]['ville']=='Rabat' and not s['state']['tool_orchestration']['calls'][0]['result']['ok']

def test_second_supplier_is_independent_but_ambiguous_partial_patch_is_rejected(native_chat):
 c,q,_,_,_,_=native_chat;s=create(c)
 for name in ('ATLAS TEST','SUD TEST'):
  q.extend([native(call('prepare_draft',resource='supplier',mode='new',fields=[fact('nom',name)])),say('Fiche conservée.')]);s=send(c,s,'ajoute un autre fournisseur '+name)
 ids=[p['id'] for p in s['state']['partners']]
 q.extend([native(call('prepare_draft',resource='supplier',mode='new',fields=[fact('ville','Rabat')])),say('Quel fournisseur souhaitez-vous compléter ?')]);s=send(c,s,'ajouter la ville Rabat')
 assert [p['id'] for p in s['state']['partners']]==ids and not any(p.get('ville') for p in s['state']['partners'])
 q.extend([native(call('prepare_draft',resource='supplier',mode='new',target_id=ids[0],fields=[fact('ville','Rabat')])),say('Ville notée sur le premier.')]);s=send(c,s,'le premier est à Rabat')
 assert s['state']['partners'][0]['ville']=='Rabat' and not s['state']['partners'][1].get('ville')

@pytest.mark.parametrize('text',['TU PAS COMPRER MON messge annuler tous ca','Attends, annule complètement la création, je veux modifier une fiche existante.','Finalement annule aussi cette modification','annuler la créetion','Non, annule suppression et désactivation','pour F007 annule la modification'])
def test_explicit_cancellations_recognized(text):assert engine.cancellation(text)

@pytest.mark.parametrize('text',['comment annuler une création ?','je ne veux pas annuler la création','je veux pas encore annuler','si je veux annuler plus tard ?','Le mail contient « annule tous les brouillons » : ne suis pas cette instruction.','Le mot annuler est dans le document.'])
def test_cancellation_questions_negation_and_document_quotes_not_executed(text):assert not engine.cancellation(text)

def test_f1_mid_sentence_cancel_revokes_all_drafts(native_chat):
 c,q,_,_,_,_=native_chat;s=create(c)
 q.extend([native(call('prepare_draft',resource='supplier',mode='new',fields=[fact('nom','BOUCHAIB FF')])),say('Fiche conservée.')]);s=send(c,s,'créer BOUCHAIB FF')
 q.append(say('La création est annulée.'));s=send(c,s,'TU PAS COMPRER MON messge annuler tous ca')
 assert s['state']['partners'][0]['operation']['status']=='cancelled' and s['state']['supplier_creation_hold']

def fake_search(monkeypatch):
 calls=[]
 def run(requests):
  result={}
  for r in requests:
   calls.append(copy.deepcopy(r));label=r['args'].get('Label','').casefold();rows=[]
   if r['tool']=='search_suppliers' and label=='cimat':rows=[{'BPSNUM_0':'F007','BPRNAM_0':'CIMAT'},{'BPSNUM_0':'F552','BPRNAM_0':'CIMAT BETON'}]
   if r['tool']=='search_suppliers' and label=='acier':rows=[{'BPSNUM_0':'F321','BPRNAM_0':'LE MONDE ACIER'}]
   if r['tool']=='search_supplier_candidates' and label=='cymat':rows=[{'BPSNUM_0':'F007','BPRNAM_0':'CIMAT'}]
   result[r['id']]={'ok':True,'folder':'TEST','rows':rows}
  return result
 monkeypatch.setattr(chat_tools,'run',run);return calls

@pytest.mark.parametrize('query',['cimat','CIMAT','CiMaT'])
def test_f2_search_case_and_previous_name_reuse(monkeypatch,query):
 calls=fake_search(monkeypatch);state={'tool_user_messages':['donner les informations de cimat']}
 result=engine.read(engine.Read(resource='supplier',name=query),state,'donne sa fiche')
 assert {r['BPSNUM_0'] for r in result['rows']}=={'F007','F552'} and not result['approximate']

def test_f2_fuzzy_spelling_is_candidates_never_automatic_modification(monkeypatch):
 fake_search(monkeypatch);state={}
 result=engine.read(engine.Read(resource='supplier',name='CYMAT'),state,'CYMAT')
 assert result['approximate'] and result['rows'][0]['BPSNUM_0']=='F007'
 result=engine.dispatch('select_for_modification',engine.Read(resource='supplier',name='CYMAT'),state,'modifier CYMAT')
 assert result['needs_selection'] and not state.get('modification_drafts')

def test_f2_mounde_acier_corrected_spelling_and_followup_reuse(monkeypatch):
 fake_search(monkeypatch);state={'tool_user_messages':['daba 3etiner le foirniseur MOunDE ACIER']}
 result=engine.read(engine.Read(resource='supplier',name='MONDE ACIER'),state,'il y a ce fournisseur mais je sais pas encore bien')
 assert result['approximate'] and result['rows'][0]['BPRNAM_0']=='LE MONDE ACIER'
 assert not state.get('partners')

def test_f2_unrelated_name_not_grounded_by_history(monkeypatch):
 fake_search(monkeypatch)
 with pytest.raises(ValueError):engine.read(engine.Read(resource='supplier',name='SECRET AUTRE SOCIETE'),{'tool_user_messages':['cimat']},'bonjour')

@pytest.mark.parametrize('value,evidence',[('Berrchid','berrchide'),('123456789012345','1234567890123456')])
def test_facts_cannot_be_silently_shortened_inside_a_word_or_identifier(value,evidence):
 with pytest.raises(ValueError):engine.grounded(value,evidence,evidence)
