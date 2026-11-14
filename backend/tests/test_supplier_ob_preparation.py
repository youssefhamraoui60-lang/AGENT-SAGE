"""Observed OB supplier method; all writes remain disabled, TEST independently read."""
import os
import pytest
from app.services import chat_fast_extract as fast,conversation_chat as chat,chat_supplier_preparation as prep,chat_tools

TEXT='Bonjour, Merci de créer ce nouveau fournisseur : NOM : DROGUERIE PALMERAIE ICE: 001850814000094 IF : 20734927 RC : 10909'
SIMPLE='Crée un fournisseur DROGUERIE PALMERAIE, ICE 001850814000094, IF 20734927, RC 10909.'


@pytest.mark.parametrize('text',[TEXT,SIMPLE,TEXT.replace(' ICE:','\nICE:').replace(' IF :','\nIF :')])
def test_exact_supplier_messages_do_not_need_model(text):
    value=fast.extract(text,{'articles':[]});assert value is not None
    delta,source=value;state=chat.merge({'articles':[]},delta,text)
    assert not source['real_model_called'] and state['articles']==[]
    p=state['partners'][0]
    assert (p['nom'],p['ice'],p['identifiant_fiscal'],p['rc'])==('DROGUERIE PALMERAIE','001850814000094','20734927','10909')
    assert not p.get('code') and not p.get('devise') and not p.get('conditions_paiement')


def partner():return {'nom':'DROGUERIE PALMERAIE','ice':'001850814000094','identifiant_fiscal':'20734927','rc':'10909'}
def profile(folder='TEST',code='F10013'):
    return {'ok':True,'rows':[{'folder':folder,'BSGCOD_0':'FR','CRY_0':'MA','CUR_0':'MAD','PTE_0':'CHQ00','VACBPR_0':'MAR','ACCCOD_0':'STD',
        'currency_verified':1,'country_verified':1,'payment_verified':1,'tax_regime_verified':1,'accounting_verified':1,'candidate_code':code,'candidate_available':1}]}
def existing(code='DROGUERIEPALME',supplier=True):
    return {'folder':'TEST','BPRNUM_0':code,'BPRNAM_0':'erreur','BPSNUM_0':code if supplier else None,'BPSNAM_0':'erreur' if supplier else None,'XICE_0':'001850814000094','XIF_0':'20734927','XRC_0':'10909'}


def test_fiscal_duplicate_is_a_warning_even_when_name_is_wrong():
    p=prep.prepare(partner(),{'fiscal':{'ok':True,'rows':[existing()]},'profile':profile()})
    assert 'supplier_fiscal_duplicate' not in p['preparation']['errors']
    assert p['preparation']['duplicates'][0]['matched_fields']==['ice','identifiant_fiscal','rc']
    assert p['preparation']['code_proposal'] is None and not p['preparation']['creation_ready']
    assert p['nom']=='DROGUERIE PALMERAIE' and not p.get('code')


def test_existing_customer_is_not_silently_recreated_as_supplier():
    p=prep.prepare(partner(),{'fiscal':{'ok':True,'rows':[existing('C06952',False)]},'profile':profile()})
    assert 'existing_business_partner_requires_review' not in p['preparation']['errors']
    assert not p['preparation']['duplicates'][0]['supplier_exists'] and p['preparation']['code_proposal'] is None


def test_defaults_are_target_proposals_not_ob_copies_or_assigned_values():
    p=prep.prepare(partner(),{'fiscal':{'ok':True,'rows':[]},'profile':profile()})
    assert p['preparation']['suggested_defaults']['devise']=={'value':'MAD','source':'TEST.BPSCATEG','confirmed':False,'business_applicability_verified':False}
    assert not p.get('devise') and not p.get('conditions_paiement')
    code=p['preparation']['code_proposal'];assert code['code']=='F10013' and not code['reserved'] and not code['official_next_number']


def test_nonconformant_candidate_is_never_proposed():
    p=prep.prepare(partner(),{'fiscal':{'ok':True,'rows':[]},'profile':profile(code='DROGUERIEPALME')})
    assert p['preparation']['code_proposal'] is None and not p.get('code')


@pytest.mark.parametrize('code',['F012','F0012','F1115','F10022'])
def test_numeric_supplier_convention_keeps_literal_code_and_leading_zeroes(code):
    # Synthetic availability only: real F012 is occupied, not a usable proposal.
    p=prep.prepare(partner(),{'fiscal':{'ok':True,'rows':[]},'profile':profile(code=code)})
    proposal=p['preparation']['code_proposal']
    assert proposal['code']==code and not proposal['reserved']
    assert not proposal['official_next_number'] and not p.get('code')
    assert not p['preparation']['creation_ready']


def test_occupied_numeric_code_is_not_proposed():
    rules=profile(code='F012');rules['rows'][0]['candidate_available']=0
    p=prep.prepare(partner(),{'fiscal':{'ok':True,'rows':[]},'profile':rules})
    assert p['preparation']['code_proposal'] is None and not p.get('code')


@pytest.mark.parametrize('exact',[False,True])
def test_broad_supplier_name_search_distinguishes_exact_name_from_shared_word(exact):
    text='Créer un fournisseur : NOM : DROGUERIE PALMERAIE 2 ICE : 001850814005094 IF : 20734924'
    delta,_=fast.extract(text,{'articles':[]});state=chat.merge({'articles':[]},delta,text)
    p=state['partners'][0]
    name={'ok':True,'rows':[{'BPSNUM_0':'F438','BPSNAM_0':p['nom'] if exact else 'LA HAUTE DROGUERIE'}]}
    results={'n':name,'f':{'ok':True,'rows':[]},'p':profile()}
    after=chat.partners.validate(state,results,{p['id']:{'name':'n','fiscal':'f','profile':'p'}})
    supplier=after['partners'][0]
    assert 'similar_partner_requires_review' not in supplier['checks']['errors']
    assert bool(supplier['preparation']['near_names']) is not exact
    assert supplier['checks']['creation_ready'] is False
    response=chat.partners.compose(after)
    if not exact:
        assert 'F438' in response and 'ressemblances seules ne prouvent pas' in response
        assert 'Des fiches proches existent' not in response


@pytest.mark.parametrize('mode',['profile_wrong_folder','fiscal_unavailable','candidate_occupied','OB'])
def test_fail_closed_scopes_and_availability(mode):
    p=partner();fiscal={'ok':True,'rows':[]};rules=profile()
    if mode=='profile_wrong_folder':rules=profile('OB')
    if mode=='fiscal_unavailable':fiscal={'ok':False,'rows':[]}
    if mode=='candidate_occupied':rules['rows'][0]['candidate_available']=0
    if mode=='OB':p['dossier_cible']='OB';rules=profile('OB','F10023')
    p=prep.prepare(p,{'fiscal':fiscal,'profile':rules})
    assert not p['preparation']['creation_ready'] and p['preparation']['sage_writes']==0
    assert p['preparation']['code_proposal'] is None


def test_repeat_same_creation_does_not_duplicate_draft():
    delta,_=fast.extract(TEXT,{'articles':[]});state=chat.merge({'articles':[]},delta,TEXT)
    same=chat.merge(state,delta,TEXT)
    assert len(same['partners'])==1 and same['partners'][0]['id']==state['partners'][0]['id']


@pytest.mark.parametrize('message',['créer le','crée le','crrer le','créer le fournisseur','créer les fournisseurs'])
def test_short_supplier_creation_request_preserves_draft_without_authorization(message):
    delta,_=fast.extract(TEXT,{'articles':[]});state=chat.merge({'articles':[]},delta,TEXT)
    before=state['partners'][0].copy()
    delta,trace=fast.extract(message,state)
    assert delta.intent=='approve' and not trace['real_model_called']
    after=chat.merge(state,delta,message)
    assert len(after['partners'])==1
    for key in ('id','nom','ice','identifiant_fiscal','rc'):
        assert after['partners'][0][key]==before[key]
    assert after['last_turn']['creation_requested']
    assert not after['partners'][0].get('approved')
    assert 'ne déclenche aucune écriture' in chat.partners.compose(after)


def test_wrong_schema_cannot_be_requested_by_tool():
    with pytest.raises(ValueError,match='folder denied'):
        chat_tools.run([{'id':'x','tool':'check_supplier_fiscal_duplicates','args':{'Folder':'PROD'}}])


@pytest.mark.parametrize('text',['Dans OB, '+SIMPLE,SIMPLE.rstrip('.')+', dossier OB'])
def test_explicit_ob_is_retained_as_read_only_reference(text):
    delta,_=fast.extract(text,{'articles':[]});state=chat.merge({'articles':[]},delta,text)
    assert state['partners'][0]['dossier_cible']=='OB'


def test_identity_fields_are_not_misread_as_accounting_codes():
    delta,_=fast.extract(TEXT,{'articles':[]})
    p=delta.fournisseurs[0]
    assert p.nom=='DROGUERIE PALMERAIE' and p.identifiant_fiscal=='20734927'
    assert not p.code_comptable and not p.forme_juridique and not p.annee_creation and not p.capital


from test_conversation_chat import fixture,create,FakeSQL
integration=pytest.mark.skipif(os.environ.get('RUN_STEP2_INTEGRATION')!='1',reason='Isolated local PostgreSQL only')


@integration
def test_full_conversation_fiscal_collision_does_not_fail_extraction(fixture,monkeypatch):
    c,_=fixture;s=create(c)
    from app.services import supplier_sql
    def preview(p):return {'id':'33333333-3333-4333-8333-333333333333','status':'prepared','transport':'direct_sql',
        'parameters':{'Nom':p['nom'],'ICE':p['ice']},'duplicate_warnings':[{'code':'DROGUERIEPALME'}],'proposed_code':'F10016'}
    monkeypatch.setattr(supplier_sql,'prepare_operation',preview)
    async def extract(text,state,*args):return fast.extract(text,state)
    monkeypatch.setattr(chat.model,'extract',extract)
    def sql(calls):
        results=FakeSQL()(calls)
        for call in calls:
            if call['tool']=='check_supplier_fiscal_duplicates':results[call['id']]={'ok':True,'rows':[existing(),existing('C06952',False)]}
            if call['tool']=='get_supplier_preparation_profile':results[call['id']]=profile()
        return results
    monkeypatch.setattr(chat.tools,'run',sql)
    response=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':TEXT,'revision':s['revision']})
    assert response.status_code==200,response.text
    s=response.json();p=s['state']['partners'][0]
    assert s['state']['analysis_job']['status']=='completed' and not s['state'].get('_pending')
    assert 'supplier_fiscal_duplicate' not in p['checks']['errors'] and p['operation']['status']=='prepared'
    assert 'DROGUERIEPALME' in s['messages'][-1]['content']
    assert p['operation']['parameters']['ICE']=='001850814000094'
    assert p['operation']['duplicate_warnings'][0]['code']=='DROGUERIEPALME'
    original_id=p['id']
    for message in ['créer le','créer le fournisseur','ok']:
        response=c.post('/api/v1/chat/conversations/'+s['id']+'/messages',json={'content':message,'revision':s['revision']})
        assert response.status_code==200,response.text
        s=response.json();p=s['state']['partners'][0]
        assert s['state']['analysis_job']['status']=='completed'
        assert len(s['state']['partners'])==1 and p['id']==original_id
        assert p['ice']=='001850814000094' and p['identifiant_fiscal']=='20734927'
        assert 'supplier_fiscal_duplicate' not in p['checks']['errors']
        assert p['operation']['status']=='prepared' and not p.get('approved')
        assert 'conservée' in s['messages'][-1]['content']
