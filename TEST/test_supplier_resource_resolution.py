"""Entity correction must not become a field value or a Sage write."""
from test_modification_multiturn_context import fixture
from test_conversation_chat import create
from app.services import modification_dialogue as d, learning
from uuid import uuid4
import subprocess,sys

REQUEST = 'Je veux modifier le téléphone de F468, mais je connais pas encore le nouveau numéro. Prépare rien à enregistrer.'
CORRECTION = "c'est un fourniseur pas articles les F qui dans le code c'est un résumer de fourniseur"

def test_standalone_unknown_phone_no_inference_or_plan(monkeypatch):
    monkeypatch.setattr(d.settings,'sage_modification_enabled',True)
    def forbidden(*a): raise AssertionError('No inference, preparation or Sage snapshot needed')
    monkeypatch.setattr(d,'semantic_changes',forbidden)
    monkeypatch.setattr(d.actions,'prepare_draft',forbidden)
    monkeypatch.setattr(d.sql,'snapshot',forbidden)
    s={'articles':[],'partners':[]}
    for text in (REQUEST,CORRECTION,'dans le fiche fourniseur pas articles'):
        result=d.turn(None,None,text,s);s=result['state']
        assert s['modification_drafts'][-1]['resource']=='supplier'
        assert s['modification_drafts'][-1]['code']=='F468'
        assert s['modification_drafts'][-1]['changes']=={}
        assert not s['modification_drafts'][-1].get('approved')

def test_old_article_draft_repaired_and_rule_persists(fixture,monkeypatch):
    c,_=fixture;conversation=create(c)
    from app.services import business_store as db
    with db.connection() as conn:
        owner=conn.execute('SELECT owner_id FROM chat_conversations WHERE id=%s',(conversation['id'],)).fetchone()['owner_id']
    monkeypatch.setattr(d.settings,'sage_modification_enabled',True)
    monkeypatch.setattr(d,'read_current_record',lambda resource,code:{'name':'TEST SUPPLIER'})
    old={'id':str(uuid4()),'folder':'TEST','resource':'article','code':'F468','changes':{},'pending_field':'phone','operation':{'status':'blocked'}}
    result=d.turn(owner,conversation['id'],CORRECTION,{'modification_drafts':[old]},[{'role':'user','content':REQUEST}])
    drafts=result['state']['modification_drafts']
    assert drafts[0]['operation']['status']=='cancelled'
    assert drafts[1]['resource']=='supplier' and drafts[1]['code']=='F468'
    assert drafts[1]['pending_field']=='phone' and not drafts[1]['changes']
    # Independent DB connection and a new conversation: durable and owner-scoped.
    new=create(c)
    context=learning.retrieve(owner,'correction fournisseur pas article type fiche')
    assert any(m['payload'].get('resource_resolution')=='supplier' and m['status']=='validated' for m in context['memory'])
    # A fresh interpreter has no in-process memory from the corrected dialogue.
    code="from app.core.config import settings; settings.business_schema="+repr(d.settings.business_schema)+"; from app.services import learning; from uuid import UUID; context=learning.retrieve(UUID("+repr(str(owner))+"),'correction fournisseur pas article type fiche'); print(any(m['payload'].get('resource_resolution')=='supplier' and m['status']=='validated' for m in context['memory']))"
    restored=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=30,check=True)
    assert restored.stdout.strip()=='True'
    s=d.turn(owner,new['id'],REQUEST,{'partners':[],'articles':[]})['state']
    assert s['modification_drafts'][-1]['resource']=='supplier'

def test_explicit_article_code_starting_f_is_not_forced_to_supplier(monkeypatch):
    monkeypatch.setattr(d.settings,'sage_modification_enabled',True)
    monkeypatch.setattr(d.actions,'prepare_draft',lambda value:value.update(operation={'status':'prepared'}))
    result=d.turn(None,None,'Modifie la désignation de l’article F468 en ARTICLE TEST',{})
    assert result['state']['modification_drafts'][-1]['resource']=='article'
