"""Configuration failures must keep the write gate closed, independent of launch directory."""
import os
from pathlib import Path
import subprocess
import sys
import pytest
from app.core.config import settings
from app.services.sage_crud import security

def test_project_environment_is_independent_of_launch_directory(tmp_path):
    backend=Path(__file__).resolve().parents[1]
    code="import hashlib;from app.core.config import settings;s=settings.approval_token.get_secret_value();print(hashlib.sha256(s.encode()).hexdigest())"
    env=os.environ.copy();env['PYTHONPATH']=str(backend);env.pop('APPROVAL_TOKEN',None)
    hashes=[]
    for cwd in [backend,tmp_path]:
        child=subprocess.run([sys.executable,'-c',code],cwd=cwd,env=env,capture_output=True,text=True,check=True)
        hashes.append(child.stdout.strip())
    assert hashes[0]==hashes[1], 'Changing the launch directory must not select a different .env'

@pytest.mark.parametrize('url',['https://[invalid','https://','https://sage:wrong','https://sage:8443/path','https://sage:8443?x=1','https://sage:8443#fragment'])
def test_invalid_transport_configuration_returns_closed_gate(monkeypatch,url):
    monkeypatch.setattr(settings,'sage_soap_base_url',url)
    state=security()
    assert not state['ready'] and 'VERIFIED_HTTPS_REQUIRED' in state['blockers']

def test_https_root_trailing_slash_matches_connector_rules(monkeypatch):
    monkeypatch.setattr(settings,'sage_soap_base_url','https://sage:8443/')
    state=security()
    assert 'VERIFIED_HTTPS_REQUIRED' not in state['blockers']
    assert not state['ready']  # No security receipt or human approval has been supplied.
