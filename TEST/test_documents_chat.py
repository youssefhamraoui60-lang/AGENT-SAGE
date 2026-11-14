from test_learning import setup,fixture
from test_natural_supplier_http import send,fake_prepare
from make_document_fixtures import make
from app.services import supplier_sql,chat_documents,business_store as db
from uuid import UUID,uuid4
from fastapi.testclient import TestClient
from app.main import app
import pytest

def upload(c,s,name):
    path=make()/name
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/files?filename='+name,content=path.read_bytes(),headers={'Content-Type':'application/pdf' if name.endswith('.pdf') else 'image/jpeg'})
    assert r.status_code==201,r.text
    return r.json()['id']

def analyze(c,s,file):
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/files/'+file+'/analyze',json={'revision':s['revision']})
    assert r.status_code==200,r.text
    return r.json()

def test_text_pdf_completes_current_draft_with_source_and_no_sage_write(setup,monkeypatch):
    c,s,owner=setup;monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    def forbidden(*a,**kw):raise AssertionError('No Sage run permitted')
    monkeypatch.setattr(supplier_sql,'run',forbidden)
    file=upload(c,s,'supplier-text.pdf');s=analyze(c,s,file)
    p=s['state']['partners'][0]
    assert p['ice']=='001234567890123' and p['identifiant_fiscal']=='01067182' and p['nom']=='DOC LECTURE TEST'
    assert p['document_sources']['ice']['page']==1 and p['document_sources']['ice']['file_id']==file
    assert not p['approved'] and p['operation']['status']=='prepared'
    assert not s['state']['document_review']['items']
    with db.connection() as conn:
        assert conn.execute('SELECT count(*) AS n FROM learning_turns WHERE conversation_id=%s',(UUID(s['id']),)).fetchone()['n']==0

def test_retry_reextracts_cached_pages_after_parser_upgrade(setup,monkeypatch):
    from psycopg.types.json import Jsonb
    c,s,owner=setup;monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    file=upload(c,s,'supplier-text.pdf')
    raw=chat_documents.decode((make()/'supplier-text.pdf').read_bytes(),'pdf')
    with db.connection() as conn:
        conn.execute('INSERT INTO chat_document_reads(file_id,owner_id,conversation_id,report) VALUES(%s,%s,%s,%s)',(UUID(file),owner,UUID(s['id']),Jsonb({**raw,'candidates':[],'warnings':[]})))
    monkeypatch.setattr(chat_documents,'decode',lambda *a:pytest.fail('Cached pages must not need OCR again'))
    s=analyze(c,s,file)
    assert s['state']['partners'][0]['ice']=='001234567890123'
    with db.connection() as conn:
        assert conn.execute('SELECT report FROM chat_document_reads WHERE file_id=%s',(UUID(file),)).fetchone()['report']['candidates']

def test_local_tax_attestation_when_available(setup,monkeypatch):
    from pathlib import Path
    path=Path.home()/'Desktop'/'AttestationREGFRASTVA207349272026. (1).pdf'
    if not path.exists():pytest.skip('Optional local reproduction document')
    c,s,owner=setup;monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    monkeypatch.setattr(supplier_sql,'run',lambda *a,**kw:pytest.fail('No Sage write'))
    response=c.post('/api/v1/chat/conversations/'+s['id']+'/files?filename=tax-attestation.pdf',content=path.read_bytes(),headers={'Content-Type':'application/pdf'})
    assert response.status_code==201
    s=analyze(c,s,response.json()['id']);p=s['state']['partners'][0]
    assert p['nom']=='DROGUERIE PALMERAIE' and p['ice']=='001850814000094'
    assert p['identifiant_fiscal']=='20734927' and p['rc']=='10909'
    assert p['adresse']=='134 LOT IMINWADAY H RDC'
    assert not p.get('ville') and not p['approved']
    assert all(p['document_sources'][key]['page']==1 for key in ('nom','ice','identifiant_fiscal','rc','adresse'))

def test_scan_values_require_chat_review_then_can_be_corrected(setup,monkeypatch):
    c,s,owner=setup;monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    s=analyze(c,s,upload(c,s,'supplier-scan.pdf'))
    p=s['state']['partners'][0];assert not p.get('ice') and s['state']['document_review']['items']
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/partners/'+p['id']+'/approve',json={'revision':s['revision'],'confirm':True})
    assert r.status_code==423 and 'document' in r.text
    s=send(c,s,'le nom est NOM CORRIGÉ')
    assert s['state']['partners'][0]['nom']=='NOM CORRIGÉ'
    s=send(c,s,'utilise les valeurs du document')
    p=s['state']['partners'][0]
    assert p['nom']=='NOM CORRIGÉ' and p['ice']=='001234567890123' and not p['approved']
    assert not s['state']['document_review']['items']

def test_existing_value_is_never_overwritten_and_chat_selects_source(setup,monkeypatch):
    c,s,owner=setup;monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    s=send(c,s,'Je veux créer un fournisseur');s=send(c,s,'DOC CONFLIT TEST');s=send(c,s,'la ville est Fes')
    s=analyze(c,s,upload(c,s,'supplier-conflicts.pdf'))
    p=s['state']['partners'][0];assert p['ville']=='Fes'
    assert 'Quelle valeur retenir pour Ville' in s['messages'][-1]['content']
    s=send(c,s,'3')  # current Fes, page 1 Rabat, page 2 Casablanca
    p=s['state']['partners'][0];assert p['ville']=='Casablanca' and p['document_sources']['ville']['page']==2
    assert not p['approved']

def test_poor_photo_has_no_false_verification_and_retains_file(setup,monkeypatch):
    c,s,owner=setup;monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    file=upload(c,s,'supplier-poor-photo.jpg');s=analyze(c,s,file)
    assert not any(p.get('approved') for p in s['state']['partners'])
    assert c.get('/api/v1/chat/conversations/'+s['id']+'/files/'+file).status_code==200
    assert 'vérifier' in s['messages'][-1]['content'] or 'pas pu lire' in s['messages'][-1]['content']

def test_file_and_extraction_owner_isolation_and_deletion_releases_space(setup,monkeypatch):
    c,s,owner=setup;monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    file=upload(c,s,'supplier-text.pdf');s=analyze(c,s,file)
    other=TestClient(app,headers={'Origin':'http://testserver'})
    r=other.post('/api/v1/chat/auth/register',json={'email':'document-other-'+uuid4().hex+'@example.test','display_name':'Other docs','password':'Document-isolation-example-2026!'})
    assert r.status_code==201;other.headers['X-Chat-CSRF']=r.json()['csrf']
    assert other.get('/api/v1/chat/conversations/'+s['id']+'/files/'+file).status_code==404
    assert other.post('/api/v1/chat/conversations/'+s['id']+'/files/'+file+'/analyze',json={'revision':s['revision']}).status_code==404
    before=c.get('/api/v1/chat/storage').json()['used_bytes']
    assert c.delete('/api/v1/chat/conversations/'+s['id']+'/files/'+file).status_code==200
    after=c.get('/api/v1/chat/storage').json()['used_bytes'];assert after<before
    with db.connection() as conn:assert not conn.execute('SELECT 1 FROM chat_document_reads WHERE file_id=%s',(UUID(file),)).fetchone()

def test_document_instructions_do_not_authorize_any_operation(setup,monkeypatch):
    c,s,owner=setup;monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    s=analyze(c,s,upload(c,s,'supplier-instructions.pdf'))
    assert s['folder']=='TEST' and not s['state']['partners'][0]['approved']
    assert s['state']['partners'][0].get('dossier_cible','TEST')=='TEST'
    assert 'ignorées' in s['messages'][-1]['content']

def test_quota_blocks_analysis_and_csrf_is_required(setup,monkeypatch):
    c,s,owner=setup;monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    file=upload(c,s,'supplier-text.pdf')
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/files/'+file+'/analyze',json={'revision':s['revision']},headers={'X-Chat-CSRF':'invalid'})
    assert r.status_code==403
    with db.connection() as conn:conn.execute('UPDATE chat_storage_usage SET limit_bytes=used_bytes+200 WHERE owner_id=%s',(owner,))
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/files/'+file+'/analyze',json={'revision':s['revision']})
    assert r.status_code==507,r.text
    with db.connection() as conn:
        assert not conn.execute('SELECT 1 FROM chat_document_reads WHERE file_id=%s',(UUID(file),)).fetchone()
        assert not conn.execute('SELECT state FROM chat_conversations WHERE id=%s',(UUID(s['id']),)).fetchone()['state'].get('partners')

def test_corrupt_file_produces_simple_error_and_keeps_the_original(setup):
    c,s,owner=setup
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/files?filename=broken.pdf',content=b'%PDF-broken',headers={'Content-Type':'application/pdf'})
    assert r.status_code==201;file=r.json()['id']
    r=c.post('/api/v1/chat/conversations/'+s['id']+'/files/'+file+'/analyze',json={'revision':s['revision']})
    assert r.status_code==422 and 'illisible' in r.text
    assert c.get('/api/v1/chat/conversations/'+s['id']+'/files/'+file).status_code==200

def test_natural_conflict_choice_keeps_the_user_value(setup,monkeypatch):
    c,s,owner=setup;monkeypatch.setattr(supplier_sql,'prepare_operation',fake_prepare)
    s=send(c,s,'Je veux créer un fournisseur');s=send(c,s,'DOC CONFLIT TEST');s=send(c,s,'la ville est Fes')
    s=analyze(c,s,upload(c,s,'supplier-conflicts.pdf'))
    s=send(c,s,'garde Fes')
    assert s['state']['partners'][0]['ville']=='Fes'
    assert not s['state']['document_review']['items']
