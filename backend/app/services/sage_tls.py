"""Verified SOAP TLS, with explicitly managed CA/CRL files and fail-closed revocation."""
import ssl
from pathlib import Path
from requests.adapters import HTTPAdapter

class TLSConfigurationError(RuntimeError):
    pass

def verified_context(config):
    ca=getattr(config,'sage_soap_ca_bundle','')
    crls=getattr(config,'sage_soap_crl_bundle','')
    if not ca or not Path(ca).is_file():raise TLSConfigurationError('sage_ca_bundle_missing')
    if not crls or not Path(crls).is_file():raise TLSConfigurationError('sage_crl_bundle_missing')
    try:
        context=ssl.create_default_context(cafile=ca)
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.verify_flags |= ssl.VERIFY_X509_STRICT | ssl.VERIFY_CRL_CHECK_CHAIN
        context.load_verify_locations(cafile=crls)
        if context.cert_store_stats().get('crl',0)<1:
            raise TLSConfigurationError('sage_crl_bundle_contains_no_crl')
        return context
    except (OSError,ValueError):
        raise TLSConfigurationError('sage_ca_or_crl_bundle_invalid') from None


def local_tls_readiness(config):
    """Inspect local material only; a peer handshake still verifies every call."""
    try:
        context=verified_context(config)
        return {'local_material_ready':True,'peer_verified':False,'code':None,
                'strict':bool(context.verify_flags & ssl.VERIFY_X509_STRICT),
                'revocation_chain':bool(context.verify_flags & ssl.VERIFY_CRL_CHECK_CHAIN)}
    except TLSConfigurationError as exc:
        return {'local_material_ready':False,'peer_verified':False,'code':str(exc)}

class VerifiedSOAPAdapter(HTTPAdapter):
    def __init__(self,context):
        self.context=context
        super().__init__(max_retries=0,pool_connections=2,pool_maxsize=2)
    def init_poolmanager(self,*args,**kwargs):
        kwargs['ssl_context']=self.context
        return super().init_poolmanager(*args,**kwargs)
