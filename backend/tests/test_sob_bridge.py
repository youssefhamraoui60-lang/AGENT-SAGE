import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import sob


def test_bridge_account_cookie_isolation_and_allowlist(monkeypatch):
    app = FastAPI()
    app.include_router(sob.router)
    owner = {'owner_id': 'first-account'}
    app.dependency_overrides[sob.sob_identity] = lambda: owner
    seen = []

    def upstream(request):
        seen.append(request)
        return httpx.Response(200, json={'ok': True}, headers={'set-cookie': 'sob_session=private-token; Path=/; HttpOnly'})

    original = httpx.AsyncClient

    class Client(original):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(upstream), **kwargs)

    monkeypatch.setattr(sob.httpx, 'AsyncClient', Client)
    with TestClient(app) as client:
        first = client.get('/api/v1/chat/sob/conversation')
        assert first.status_code == 200
        assert 'Path=/api/v1/chat/sob' in first.headers['set-cookie']
        assert 'HttpOnly' in first.headers['set-cookie']
        client.cookies.set('sage_chat_session', 'account-secret')
        client.get('/api/v1/chat/sob/conversation')
        assert seen[-1].headers['cookie'] == 'sob_session=private-token'
        owner = {'owner_id': 'second-account'}
        client.get('/api/v1/chat/sob/conversation')
        assert 'cookie' not in seen[-1].headers
        before = len(seen)
        assert client.get('/api/v1/chat/sob/anything').status_code == 404
        assert client.post('/api/v1/chat/sob/chat', content=b'x' * 50001).status_code == 413
        assert len(seen) == before


def test_read_and_write_use_existing_auth(monkeypatch):
    calls = []
    monkeypatch.setattr(sob.auth, 'identity', lambda r: calls.append('identity') or {})
    monkeypatch.setattr(sob.auth, 'operator', lambda r: calls.append('operator') or {})
    from starlette.requests import Request
    sob.sob_identity(Request({'type': 'http', 'method': 'GET'}))
    sob.sob_identity(Request({'type': 'http', 'method': 'POST'}))
    sob.sob_identity(Request({'type': 'http', 'method': 'DELETE'}))
    assert calls == ['identity', 'operator', 'operator']
