import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb
from app.core.config import settings
from app.services import sage_powershell_chat as bridge, conversation_chat as chat, business_store as db
from app.services.sage_crud import CrudError


def article():
    return {'id':str(uuid4()),'code_article':'TESTWEB005','designation':'SYNTHETIC WEB TEST',
        'categorie':'NEG','unite':'UN','site':'201','sources':{'site':'user_declared'},
        'reviewed':True,'checks':{'valid_basic':True}}


@pytest.mark.parametrize('site,source',[(None,None),('202','user_declared'),('201','application_proposal_not_reserved')])
def test_site_201_must_be_explicit_before_any_worker(monkeypatch,site,source):
    monkeypatch.setattr(settings,'sage_powershell_chat_enabled',True)
    value=article();value['site']=site;value['sources']['site']=source
    with pytest.raises(CrudError,match='site_201_explicit_required'): bridge.validate_scope(value)


def test_attempted_web_article_cannot_be_edited():
    value=article();value['operation']={'transport':'PowerShell 5.1','status':'executing'}
    with pytest.raises(CrudError,match='attempted_article_is_immutable'):chat.invalidate(value)


def test_explicit_designation_survives_model_omission():
    from app.services.chat_model import Delta,Patch
    delta=Delta(intent='new',shared=Patch(site='201',unite='UN',categorie='NEG'),
                articles=[Patch(code_article='TESTAGENT005',site='201',unite='UN',categorie='NEG')])
    state=chat.merge({'articles':[]},delta,
        'Crée un article, code article TESTAGENT005, désignation ARTICLE TEST INTERFACE SITE 201, catégorie NEG, unité UN, site 201.')
    value=state['articles'][0]
    assert value['designation']=='ARTICLE TEST INTERFACE SITE 201'
    assert value['code_article']=='TESTAGENT005' and value['site']=='201'


def test_site_201_never_invents_stock_management_1():
    assert not chat.grounded('gestion_stock','1','Article de test, site 201, unité UN.')
    assert chat.grounded('gestion_stock','1','Article non géré, site 201.')


def test_exact_extinguisher_draft_can_be_prepared_with_supplier_and_stock(monkeypatch):
    monkeypatch.setattr(settings,'sage_powershell_chat_enabled',True)
    a=article();a.update(code_article='EXT_POUDRE',designation='Extincteur à poudre',
        code_fournisseur='F1025',fournisseur_nom='CHAOUIA PROTECT',gestion_stock='1')
    assert bridge.creation_blockers(a)==[]
    bridge.validate_scope(a)
    for field,value in [('code_article','OTHER'),('code_fournisseur','F9999'),('gestion_stock','2'),('site','202')]:
        changed=deepcopy(a);changed[field]=value
        with pytest.raises(CrudError):bridge.validate_scope(changed)


@pytest.mark.parametrize('label',['A','B'])
def test_exact_modern_foam_scope_is_M2_202_and_no_supplier(monkeypatch,label):
    monkeypatch.setattr(settings,'sage_powershell_chat_enabled',True)
    a=article();a.update(code_article=f'MFB-{label}-XPS-40',designation=f'Modern foam boards {label} XPS 4 CM',unite='M2',site='202')
    assert bridge.creation_blockers(a)==[]
    bridge.validate_scope(a)
    for field,value in [('site','201'),('unite','UN'),('designation','Other product'),('code_fournisseur','F234')]:
        changed=deepcopy(a);changed[field]=value
        with pytest.raises(CrudError):bridge.validate_scope(changed)


@pytest.fixture
def workflow(monkeypatch):
    if os.environ.get('RUN_STEP2_INTEGRATION')!='1':pytest.skip('Explicit isolated local DB')
    schema='ps_web_test_'+uuid4().hex[:12]
    monkeypatch.setattr(settings,'business_schema',schema)
    monkeypatch.setattr(settings,'sage_powershell_chat_enabled',True)
    db.migrate();chat.migrate()
    owner=uuid4();session=chat.create(owner);value=article()
    with db.connection() as conn:
        conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',
                     (Jsonb({'articles':[value]}),session['id']))
    calls=[]
    def worker(a,mode,**extra):
        calls.append(mode)
        if mode=='prepare':return {'ObjectXml':'<PARAM/>','Digest':'synthetic','DescriptionHash':'synthetic'}
        return {'State':'CREATED_AND_READ_BACK','ReadConfirmed':True,'ReadStatus':1,'SaveStatus':1,'Messages':[]}
    monkeypatch.setattr(bridge,'worker',worker)
    def select(a):
        return {'ok':True,'folder':'TEST','category':[{}],'unit':[{}],'site':[{}],
            'article':[{'ITMREF_0':a['code_article'],'ITMDES1_0':a['designation'],'TCLCOD_0':'NEG',
                        'STU_0':'UN','PUU_0':'UN','SAU_0':'UN'}] if 'execute' in calls else []}
    monkeypatch.setattr(bridge,'sql_verify',select)
    bridge.PERMITS.clear()
    yield owner,session,value,calls
    bridge.PERMITS.clear()
    with db.connection() as conn:conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def act(workflow,action,confirm=False):
    owner,session,value,calls=workflow
    return bridge.write_action(owner,session['id'],value['id'],action,session['revision'],confirm)


def test_browser_prepare_approve_execute_is_one_shot(workflow):
    prepared=act(workflow,'prepare')
    assert prepared['state']['articles'][0]['operation']['status']=='prepared'
    with pytest.raises(CrudError):act(workflow,'execute',True)
    with pytest.raises(CrudError):act(workflow,'approve',False)
    act(workflow,'approve',True)
    result=act(workflow,'execute',True)
    assert result['state']['articles'][0]['outcome']['confirmed']
    assert workflow[3]==['prepare','execute']
    with pytest.raises(CrudError):act(workflow,'execute',True)
    assert workflow[3]==['prepare','execute']


def test_expired_browser_approval_never_calls_save(workflow):
    act(workflow,'prepare');act(workflow,'approve',True)
    bridge.PERMITS[workflow[2]['id']]['expires_at']=datetime.now(timezone.utc)-timedelta(seconds=1)
    with pytest.raises(CrudError):act(workflow,'execute',True)
    assert workflow[3]==['prepare']


def test_uncertain_worker_is_committed_and_never_retried(workflow,monkeypatch):
    act(workflow,'prepare');act(workflow,'approve',True)
    def uncertain(*args,**kwargs):workflow[3].append('execute');raise TimeoutError()
    monkeypatch.setattr(bridge,'worker',uncertain)
    result=act(workflow,'execute',True)
    assert result['state']['articles'][0]['operation']['status']=='ambiguous'
    with pytest.raises(CrudError):act(workflow,'execute',True)
    assert workflow[3].count('execute')==1


@pytest.mark.parametrize('action',['prepare','approve','execute'])
def test_missing_or_other_site_blocks_every_browser_action(workflow,action):
    owner,session,value,calls=workflow
    value['site']='202'
    with db.connection() as conn:
        conn.execute('UPDATE chat_conversations SET state=%s WHERE id=%s',(Jsonb({'articles':[value]}),session['id']))
    with pytest.raises(CrudError,match='site_201_explicit_required'):act(workflow,action,True)
    assert calls==[]
