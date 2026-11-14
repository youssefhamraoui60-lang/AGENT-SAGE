import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.extraction import Extraction

client = TestClient(app)

def test_health():
    assert client.get('/health').json() == {'status':'ok','stage':1}

def test_input_validation():
    assert client.post('/api/ai/extract',json={'demande':' '}).status_code == 422
    assert client.post('/api/ai/extract',json={'demande':'article','extra':True}).status_code == 422

def test_missing_field_consistency():
    with pytest.raises(ValueError):
        Extraction(designation='Test',unite=None,categorie='FG',fournisseur='Test',confiance=0.5,champs_manquants=[])

def test_upstream_invalid_json(monkeypatch):
    async def bad(_):
        raise ValueError('invalid JSON')
    monkeypatch.setattr('app.main.extract',bad)
    assert client.post('/api/ai/extract',json={'demande':'article de test'}).status_code == 502

def test_timeout(monkeypatch):
    async def timeout(_):
        raise httpx.ReadTimeout('timeout')
    monkeypatch.setattr('app.main.extract',timeout)
    assert client.post('/api/ai/extract',json={'demande':'article de test'}).status_code == 504
