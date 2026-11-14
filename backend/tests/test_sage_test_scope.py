from datetime import datetime, timedelta, timezone
from copy import deepcopy
import pytest
from app.services.sage_test_scope import temporary_admin_scope, scope_matches


def policy():
    return {'temporary_admin_test':True,'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
        'solution':'V12','folder':'TEST','pool':'POOL_AI_TEST','base_url':'https://sage:8443',
        'scope':{'resource':'articles','action':'create','keys':{'ITMREF':'TESTAGENT004'}},
        'permissions':{'articles':{'create':{}}}}


def test_only_fixed_article_scope():
    p=policy()
    assert temporary_admin_scope(p,'admin')
    assert scope_matches(p,'articles','create',{'ITMREF':'TESTAGENT004'})
    for resource,action,keys in [('articles','create',{'ITMREF':'OTHER'}),
        ('articles','update',{'ITMREF':'TESTAGENT004'}),('suppliers','create',{'BPSNUM':'TESTAGENT004'})]:
        assert not scope_matches(p,resource,action,keys)


@pytest.mark.parametrize('change',[{'folder':'PROD'},{'pool':'OTHER'},
    {'expires_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()},
    {'expires_at':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()},
    {'scope':{'resource':'articles','action':'create','keys':{'ITMREF':'OTHER'}}},
    {'permissions':{'articles':{'create':{},'update':{}}}}])
def test_expanded_or_expired_exception_rejected(change):
    p=policy();p.update(change)
    assert not temporary_admin_scope(p,'admin')


def test_scoped_other_http_write_routes_stay_423(monkeypatch):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from app.main import app
    from app.core.config import settings
    from app.services import sage_crud
    monkeypatch.setattr(settings,'approval_token',SecretStr('synthetic-scope-test'))
    monkeypatch.setattr(sage_crud,'security',lambda *a,**k:{'ready':True,'blockers':[], 'scope':policy()['scope']})
    client=TestClient(app)
    client.headers['X-Approval-Token']='synthetic-scope-test'
    for method,path in [('post','/api/v1/sage/suppliers'),('post','/api/v1/sage/article-sites'),
                        ('patch','/api/v1/sage/articles/TESTAGENT004')]:
        assert getattr(client,method)(path,json={}).status_code==423


def test_real_security_binds_admin_exception_to_exact_key(monkeypatch,tmp_path):
    import hashlib,json
    from pydantic import SecretStr
    from app.core.config import settings
    from app.services import sage_crud
    # Isolate the exact-key policy test; TLS is exercised separately, including
    # a negative test proving this exception never bypasses a missing CRL.
    monkeypatch.setattr(sage_crud,'local_tls_readiness',lambda config:{'local_material_ready':True,'peer_verified':False})
    p=policy()
    proof=tmp_path/'proof';proof.write_text('synthetic evidence only')
    evidence={'path':str(proof),'sha256':hashlib.sha256(proof.read_bytes()).hexdigest()}
    p.update(credentials_rotated=True,dedicated_account_verified=False,
             http_login_sha256=hashlib.sha256(b'admin').hexdigest())
    p['permissions']['articles']['create']={
        'rights_verified':True,'business_rules_reviewed':True,'manual_keys_preserved':True,
        'rights_evidence':evidence,'business_rules_evidence':evidence}
    file=tmp_path/'policy.json';file.write_text(json.dumps(p))
    monkeypatch.setattr(settings,'sage_writes_enabled',True)
    monkeypatch.setattr(settings,'sage_soap_username',SecretStr('admin'))
    monkeypatch.setattr(settings,'sage_soap_base_url','https://sage:8443')
    monkeypatch.setattr(settings,'sage_soap_pool','POOL_AI_TEST')
    monkeypatch.setattr(settings,'sage_security_policy_file',str(file))
    assert sage_crud.security('articles','create',record_keys={'ITMREF':'TESTAGENT004'})['ready']
    result=sage_crud.security('articles','create',record_keys={'ITMREF':'OTHER'})
    assert not result['ready'] and 'OUTSIDE_SINGLE_ARTICLE_TEST_SCOPE' in result['blockers']
