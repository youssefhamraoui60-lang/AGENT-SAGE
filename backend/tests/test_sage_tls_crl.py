"""Real TLS MemoryBIO verification with test-only certificates; no listening port."""
import os,ssl
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.services.sage_tls import verified_context,TLSConfigurationError
from app.services.sage_soap import SageReader,SageError
from pydantic import SecretStr

def test_missing_ca_fails_closed(tmp_path):
    with pytest.raises(TLSConfigurationError,match='sage_ca_bundle_missing'):
        verified_context(SimpleNamespace(sage_soap_ca_bundle=str(tmp_path/'missing')))

def test_missing_crl_fails_before_any_network(tmp_path,monkeypatch):
    ca=tmp_path/'ca';ca.write_text('not used before missing CRL check')
    config=SimpleNamespace(sage_soap_base_url='https://sage:8443',sage_soap_ca_bundle=str(ca),sage_soap_crl_bundle='',sage_soap_username=SecretStr('AIAGT'),sage_soap_password=SecretStr('synthetic'))
    def forbidden(*args,**kwargs):raise AssertionError('network must not be used')
    monkeypatch.setattr('requests.Session.request',forbidden)
    with pytest.raises(SageError,match='sage_crl_bundle_missing'):SageReader(config)._client()

def test_invalid_bundle_sanitized(tmp_path):
    file=tmp_path/'invalid';file.write_text('not a certificate')
    with pytest.raises(TLSConfigurationError,match='^sage_ca_or_crl_bundle_invalid$'):
        verified_context(SimpleNamespace(sage_soap_ca_bundle=str(file),sage_soap_crl_bundle=str(file)))


def test_certificates_are_not_a_substitute_for_a_real_crl():
    ca=Path(__file__).resolve().parents[2]/'certs/ca.cacrt'
    with pytest.raises(TLSConfigurationError,match='sage_crl_bundle_contains_no_crl'):
        verified_context(SimpleNamespace(sage_soap_ca_bundle=str(ca),sage_soap_crl_bundle=str(ca)))


def test_security_gate_exposes_missing_crl_without_network(monkeypatch,tmp_path):
    from app.core.config import settings
    from app.services.sage_crud import security
    monkeypatch.setattr(settings,'sage_soap_base_url','https://sage:8443')
    monkeypatch.setattr(settings,'sage_soap_ca_bundle',str(Path(__file__).resolve().parents[2]/'certs/ca.cacrt'))
    monkeypatch.setattr(settings,'sage_soap_crl_bundle',str(tmp_path/'missing'))
    def forbidden(*args,**kwargs):raise AssertionError('no network from write-gate check')
    monkeypatch.setattr('requests.Session.request',forbidden)
    state=security('suppliers','create')
    assert not state['ready'] and 'CA_CRL_MATERIAL_REQUIRED' in state['blockers']
    assert state['tls']['code']=='sage_crl_bundle_missing' and not state['tls']['peer_verified']


def test_admin_scope_cannot_override_a_missing_crl(monkeypatch,tmp_path):
    from app.core.config import settings
    from app.services import sage_crud
    monkeypatch.setattr(settings,'sage_writes_enabled',True)
    monkeypatch.setattr(settings,'sage_soap_base_url','https://sage:8443')
    monkeypatch.setattr(settings,'sage_soap_ca_bundle',str(Path(__file__).resolve().parents[2]/'certs/ca.cacrt'))
    monkeypatch.setattr(settings,'sage_soap_crl_bundle',str(tmp_path/'missing'))
    monkeypatch.setattr(sage_crud,'temporary_admin_scope',lambda *args:True)
    state=sage_crud.security('articles','create',record_keys={'ITMREF':'TESTAGENT004'})
    assert not state['ready'] and 'CA_CRL_MATERIAL_REQUIRED' in state['blockers']

TEST_ROOT=Path(__file__).resolve().parents[2]/'runtime/pki-test'
LAB=Path(os.environ.get('SAGE_TEST_PKI_FIXTURE_DIR',str(TEST_ROOT/'chain-validation-20261024')))
@pytest.mark.skipif(os.environ.get('RUN_PKI_INTEGRATION')!='1',reason='Explicit local PKI test fixtures, no production certificates')
@pytest.mark.parametrize('bundle,hostname,error', [('crls-valid.pem','sage',None),('crls-revoked.pem','sage',23),('crls-valid.pem','wrong.invalid',62)])
def test_real_context_memory_handshake(tmp_path,bundle,hostname,error):
    assert LAB.resolve().parent==TEST_ROOT.resolve() and LAB.name.startswith('chain-validation-')
    from app.core.dpapi_credential import _unprotect
    config=SimpleNamespace(sage_soap_ca_bundle=str(LAB/'root/cert.pem'),sage_soap_crl_bundle=str(LAB/'public'/bundle))
    client=verified_context(config)
    assert client.check_hostname and client.verify_mode==ssl.CERT_REQUIRED
    assert client.verify_flags & ssl.VERIFY_X509_STRICT
    assert client.verify_flags & ssl.VERIFY_CRL_CHECK_CHAIN
    chain=tmp_path/'chain.pem';chain.write_bytes((LAB/'server/cert.pem').read_bytes()+(LAB/'issuer/cert.pem').read_bytes())
    server=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(str(chain),str(LAB/'server/private/key.pem'),password=_unprotect((LAB/'server/private/passphrase.dpapi').read_bytes()))
    ci,co,si,so=[ssl.MemoryBIO() for _ in range(4)]
    c=client.wrap_bio(ci,co,server_hostname=hostname);s=server.wrap_bio(si,so,server_side=True)
    def handshake():
        complete=set()
        for _ in range(100):
            for label,peer in [('client',c),('server',s)]:
                if label not in complete:
                    try:peer.do_handshake();complete.add(label)
                    except ssl.SSLWantReadError:pass
            if co.pending:si.write(co.read())
            if so.pending:ci.write(so.read())
            if len(complete)==2:return
        raise AssertionError('Memory handshake did not complete')
    if error:
        with pytest.raises(ssl.SSLCertVerificationError) as exc:handshake()
        assert exc.value.verify_code==error
    else:handshake() # Historical pre-revocation CRL fixture, never production trust.
