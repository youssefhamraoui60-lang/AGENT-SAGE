from uuid import uuid4
import hashlib
import pytest
from app.services import sage_gateway as gateway
from app.services.sage_soap import MAX_BYTES,SageError

def test_complete_soap_body_preserved_without_overwriting(monkeypatch,tmp_path):
    monkeypatch.setattr(gateway,'SOAP_RESPONSE_DIR',tmp_path)
    identifier=uuid4();body=b'<Envelope><Body><Fault>TEST ONLY</Fault></Body></Envelope>'
    proof=gateway.archive_write_response(identifier,body)
    file=tmp_path/(str(identifier)+'.xml')
    assert file.read_bytes()==body and proof['soap_response_sha256']==hashlib.sha256(body).hexdigest()
    with pytest.raises(FileExistsError):gateway.archive_write_response(identifier,b'REPLAY')
    assert file.read_bytes()==body

def test_response_archive_rejects_traversal_and_oversize(monkeypatch,tmp_path):
    monkeypatch.setattr(gateway,'SOAP_RESPONSE_DIR',tmp_path)
    with pytest.raises(ValueError):gateway.archive_write_response('../../outside',b'X')
    with pytest.raises(SageError):gateway.archive_write_response(uuid4(),b'X'*(MAX_BYTES+1))
    assert not list(tmp_path.iterdir())
