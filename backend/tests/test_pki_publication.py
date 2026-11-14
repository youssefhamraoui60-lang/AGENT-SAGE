import hashlib,json
from datetime import datetime,timezone,timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import pki_publication as pki
from app.core.config import settings

def setup(monkeypatch,tmp_path,enabled=True,remote=False):
    monkeypatch.setattr(settings,'pki_publication_enabled',enabled)
    monkeypatch.setattr(settings,'pki_publication_directory',str(tmp_path))
    monkeypatch.setattr(pki,'PUBLIC_ROOT',tmp_path)
    app=FastAPI();app.include_router(pki.router);app.middleware('http')(pki.restrict_lan_to_public_pki)
    @app.get('/private')
    def private():return {'local_only':True}
    return TestClient(app,client=('192.168.9.200' if remote else '127.0.0.1',50000))

def prepare(tmp_path,expired=False):
    data=b'PUBLIC-DER-TEST-FIXTURE';(tmp_path/'issuing.crl').write_bytes(data)
    entry={'sha256':hashlib.sha256(data).hexdigest(),'expires_at':(datetime.now(timezone.utc)+timedelta(hours=-1 if expired else 24)).isoformat()}
    (tmp_path/'public-manifest.json').write_text(json.dumps({'status':'APPROVED_PUBLIC_DISTRIBUTION','files':{'issuing.crl':entry}}))

def test_disabled_even_if_files_present(monkeypatch,tmp_path):
    prepare(tmp_path);assert setup(monkeypatch,tmp_path,enabled=False).get('/pki/issuing.crl').status_code==404

def test_allowlisted_public_bytes_and_lan_private_denial(monkeypatch,tmp_path):
    prepare(tmp_path);c=setup(monkeypatch,tmp_path,remote=True)
    r=c.get('/pki/issuing.crl');assert r.status_code==200 and r.headers['content-type']=='application/pkix-crl'
    assert c.get('/private').status_code==404
    assert c.get('/pki/key.pem').status_code==404
    assert c.get('/pki/public-manifest.json').status_code==404

def test_loopback_preserved(monkeypatch,tmp_path):
    c=setup(monkeypatch,tmp_path);assert c.get('/private').status_code==200

def test_expired_or_tampered_object_refused(monkeypatch,tmp_path):
    prepare(tmp_path,expired=True);c=setup(monkeypatch,tmp_path)
    assert c.get('/pki/issuing.crl').status_code==503
    prepare(tmp_path);(tmp_path/'issuing.crl').write_bytes(b'tampered')
    assert c.get('/pki/issuing.crl').status_code==503
