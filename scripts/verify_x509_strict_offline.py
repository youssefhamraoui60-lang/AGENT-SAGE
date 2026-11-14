"""Verify public leaf with supplied CA using native OpenSSL; no network/store change."""
import ctypes as C,json,ssl,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
lib=C.CDLL(str(Path(sys.base_prefix)/'DLLs/libcrypto-3.dll'))
P=C.c_void_p
def bind(name,restype,args):
    f=getattr(lib,name);f.restype=restype;f.argtypes=args;return f
d2i=bind('d2i_X509',P,[P,C.POINTER(P),C.c_long])
free=bind('X509_free',None,[P])
def load(data):
    buf=C.create_string_buffer(data);ptr=C.cast(buf,P)
    cert=d2i(None,C.byref(ptr),len(data))
    if not cert:raise RuntimeError('invalid_certificate')
    return cert
ca_der=ssl.PEM_cert_to_DER_cert((ROOT/'certs/ca.cacrt').read_text())
leaf_der=(ROOT/'logs/https-presented-sage-20261024.cer').read_bytes()
leaf=load(leaf_der);ca=load(ca_der)
store=bind('X509_STORE_new',P,[])();ctx=bind('X509_STORE_CTX_new',P,[])()
try:
    assert bind('X509_STORE_add_cert',C.c_int,[P,P])(store,ca)==1
    assert bind('X509_STORE_set_flags',C.c_int,[P,C.c_ulong])(store,0x20)==1 # X509_V_FLAG_X509_STRICT
    assert bind('X509_STORE_CTX_init',C.c_int,[P,P,P,P])(ctx,store,leaf,None)==1
    ok=bind('X509_verify_cert',C.c_int,[P])(ctx)
    error=bind('X509_STORE_CTX_get_error',C.c_int,[P])(ctx)
    depth=bind('X509_STORE_CTX_get_error_depth',C.c_int,[P])(ctx)
    text=bind('X509_verify_cert_error_string',C.c_char_p,[C.c_long])(error).decode()
    report={'openssl':ssl.OPENSSL_VERSION,'python':sys.version,'strict_validation':True,'verified':ok==1,'error':error,'error_text':text,'error_depth':depth,'depth_zero_is_server_certificate':depth==0,'leaf_sha256':hashlib.sha256(leaf_der).hexdigest().upper(),'ca_sha256':hashlib.sha256(ca_der).hexdigest().upper(),'trust_store_modified':False,'revocation_checked':False,'scope':'offline attribution of strict X509 error only, not connection acceptance'}
    (ROOT/'logs/https-openssl-strict-attribution-20261024.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
finally:
    bind('X509_STORE_CTX_free',None,[P])(ctx);bind('X509_STORE_free',None,[P])(store);free(leaf);free(ca)
