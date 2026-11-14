"""Disposable campaign credentials encrypted with Windows user DPAPI, never printed."""
import ctypes,hashlib,json,secrets,time
from ctypes import wintypes
from pathlib import Path
import httpx
from app.services import business_store as db

PRIVATE=Path(__file__).resolve().parent/'article-100-session-campaign/private'
FILE=PRIVATE/'accounts.dpapi'
class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_byte))]

def crypt(data,decrypt=False):
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_byte)));output=Blob()
    fn=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(source),None,None,None,None,0,ctypes.byref(output)):raise ctypes.WinError()
    try:return ctypes.string_at(output.data,output.size)
    finally:ctypes.windll.kernel32.LocalFree(output.data)

def load():return json.loads(crypt(FILE.read_bytes(),True))

def create_pool():
    if FILE.exists():print('Encrypted campaign accounts already available');return
    # Respect the real registration throttle instead of clearing its counters.
    key=hashlib.sha256(b'register:ip:127.0.0.1').hexdigest()
    with db.connection() as conn:
        r=conn.execute("SELECT greatest(0,extract(epoch FROM window_start+interval '15 minutes'-now())) AS wait FROM chat_auth_attempts WHERE key=%s AND attempts>=36",(key,)).fetchone()
    remaining=float(r['wait'])+2 if r else 0
    print('Respecting registration window; wait_seconds',round(remaining),flush=True)
    while remaining>0:
        delay=min(remaining,30);time.sleep(delay);remaining-=delay
    credentials=[]
    for i in range(4):
        entry={'email':f'article-pool-{secrets.token_hex(8)}-{i}@example.test','password':secrets.token_urlsafe(32)}
        with httpx.Client(headers={'Origin':'http://127.0.0.1:8000'},timeout=30) as client:
            r=client.post('http://127.0.0.1:8000/api/v1/chat/auth/register',json={**entry,'display_name':'Campagne articles TEST'})
            if r.status_code!=201:raise RuntimeError('Campaign registration unavailable: HTTP '+str(r.status_code))
        credentials.append(entry)
    PRIVATE.mkdir(parents=True,exist_ok=True);(PRIVATE/'.gitignore').write_text('*\n!.gitignore\n',encoding='utf-8')
    FILE.write_bytes(crypt(json.dumps(credentials).encode()))
    assert load()==credentials
    print('Four disposable test accounts prepared; DPAPI roundtrip verified',flush=True)

if __name__=='__main__':create_pool()
