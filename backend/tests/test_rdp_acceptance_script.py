"""No network: acceptance tool must reject unsafe pre-maintenance settings."""
import importlib.util,json,sys
from pathlib import Path
from types import SimpleNamespace
from pydantic import SecretStr
import pytest

@pytest.mark.parametrize('change,error',[
 ({'sage_soap_base_url':'http://192.168.9.200:8124'},'approved_https_sage_8443_not_configured'),
 ({'sage_soap_username':SecretStr('admin')},'aiagt_not_configured'),
 ({'sage_writes_enabled':True},'writes_must_remain_disabled_during_read_acceptance'),
 ({'fingerprint':'invalid'},'invalid_public_certificate_fingerprint')])
def test_acceptance_refuses_before_any_network(tmp_path,monkeypatch,change,error):
    file=Path(__file__).resolve().parents[2]/'scripts/verify_sage_after_rdp_maintenance.py'
    spec=importlib.util.spec_from_file_location('rdp_acceptance_test',file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    values={'sage_soap_base_url':'https://sage:8443','sage_soap_username':SecretStr('AIAGT'),'sage_writes_enabled':False}
    values.update({k:v for k,v in change.items() if k!='fingerprint'})
    monkeypatch.setattr(module,'settings',SimpleNamespace(**values));monkeypatch.setattr(module,'ROOT',tmp_path)
    (tmp_path/'logs').mkdir()
    monkeypatch.setattr(module.sage_crud,'security',lambda:{'ready':False,'blockers':['WRITES_DISABLED']})
    def forbidden(*a,**k):raise AssertionError('Network must not be reached')
    monkeypatch.setattr(module.socket,'create_connection',forbidden);monkeypatch.setattr(module,'Gateway',forbidden)
    monkeypatch.setattr(sys,'argv',['check','--article','EXISTING','--site-article','EXISTING','--expected-server-sha256',change.get('fingerprint','A'*64)])
    assert module.main()==1
    result=json.loads(next((tmp_path/'logs').glob('*.json')).read_text())
    assert result['status']=='BLOCKED' and result['error_code']==error and result['save_sent'] is False
