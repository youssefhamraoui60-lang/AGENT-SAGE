"""Password accounts, opaque rotating sessions and same-origin CSRF protection."""
import hashlib,hmac,re,secrets,threading
from uuid import uuid4
from datetime import datetime,timedelta,timezone
from urllib.parse import urlsplit
from fastapi import Request,HTTPException
from app.core.config import settings
from app.services import business_store as db

COOKIE='sage_chat_session'
_HASH_SLOTS=threading.BoundedSemaphore(4)

def trusted_local(request):
    host=urlsplit(str(request.base_url)).hostname
    return request.client is not None and request.client.host in ('127.0.0.1','::1','testclient') and host in ('127.0.0.1','localhost','::1','testserver')

def origin_check(request):
    if not trusted_local(request):raise HTTPException(403,'Accès local uniquement.')
    if request.headers.get('origin','').rstrip('/')!=str(request.base_url).rstrip('/'):
        raise HTTPException(403,'Origine de la requête refusée.')

def csrf(token):
    secret=settings.approval_token.get_secret_value()
    if not secret:raise HTTPException(503,'Clé de session non configurée.')
    return hmac.new(secret.encode(),('chat-csrf:'+token).encode(),hashlib.sha256).hexdigest()

def password_hash(password):
    salt=secrets.token_bytes(16)
    with _HASH_SLOTS:key=hashlib.scrypt(password.encode('utf-8'),salt=salt,n=32768,r=8,p=3,maxmem=64*1024*1024,dklen=32)
    return 'scrypt$32768$8$3$'+salt.hex()+'$'+key.hex()

_DUMMY=password_hash('not-an-actual-user-password')

def verify_password(password,encoded):
    try:
        parts=encoded.split('$')
        if parts[:4]!=['scrypt','32768','8','3'] or len(parts)!=6:raise ValueError()
        salt=bytes.fromhex(parts[4]);expected=bytes.fromhex(parts[5])
        if len(salt)!=16 or len(expected)!=32:raise ValueError()
    except (ValueError,AttributeError):salt=bytes.fromhex(_DUMMY.split('$')[4]);expected=b'0'*32
    with _HASH_SLOTS:actual=hashlib.scrypt(password.encode('utf-8'),salt=salt,n=32768,r=8,p=3,maxmem=64*1024*1024,dklen=32)
    return hmac.compare_digest(actual,expected)

def throttle(request,email,purpose):
    keys=[(purpose+':ip:'+request.client.host,100 if purpose=='login' else 40)]
    if purpose=='login':keys.append((purpose+':email:'+email,10))
    blocked=False
    with db.connection() as conn:
        for value,maximum in keys:
            key=hashlib.sha256(value.encode()).hexdigest()
            row=conn.execute("""INSERT INTO chat_auth_attempts(key,attempts) VALUES(%s,1)
                ON CONFLICT(key) DO UPDATE SET attempts=CASE WHEN chat_auth_attempts.window_start<now()-interval '15 minutes' THEN 1 ELSE chat_auth_attempts.attempts+1 END,
                window_start=CASE WHEN chat_auth_attempts.window_start<now()-interval '15 minutes' THEN now() ELSE chat_auth_attempts.window_start END RETURNING attempts""",(key,)).fetchone()
            blocked=blocked or row['attempts']>maximum
    if blocked:raise HTTPException(429,'Trop de tentatives. Réessayez dans 15 minutes.')

def identity(request:Request):
    if not trusted_local(request):raise HTTPException(403,'Accès local uniquement.')
    token=request.cookies.get(COOKIE,'')
    if not token or len(token)>128:raise HTTPException(401,'Connectez-vous pour accéder à vos conversations.')
    with db.connection() as conn:
        row=conn.execute('''SELECT s.owner_id,s.role,s.expires_at,a.email,a.display_name FROM chat_web_sessions s
            JOIN chat_accounts a ON a.id=s.owner_id WHERE s.token_hash=%s AND s.authenticated=true AND a.active=true''',
            (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not row or row['expires_at']<=datetime.now(timezone.utc):raise HTTPException(401,'Session expirée. Reconnectez-vous.')
    return {**row,'csrf':csrf(token)}

def operator(request:Request):
    user=identity(request);origin_check(request)
    if user['role']!='operator' or not hmac.compare_digest(request.headers.get('x-chat-csrf',''),user['csrf']):raise HTTPException(403,'Action non autorisée.')
    return user

def public(user):
    from app.services.chat_storage import status
    return {'role':user['role'],'csrf':user['csrf'],'expires_at':user['expires_at'],'mode':'password_account',
            'user':{'id':str(user['owner_id']),'email':user['email'],'display_name':user['display_name']},'storage':status(user['owner_id'])}

def bootstrap(request,response):
    if request.method!='GET':origin_check(request)
    response.headers['Cache-Control']='no-store'
    return public(identity(request))

def normalize_email(email):
    email=email.strip().lower()
    if len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise HTTPException(422,'Adresse e-mail invalide.')
    return email

def establish(conn,request,response,owner):
    old=request.cookies.get(COOKIE,'')
    if old:conn.execute('DELETE FROM chat_web_sessions WHERE token_hash=%s',(hashlib.sha256(old.encode()).hexdigest(),))
    token=secrets.token_urlsafe(32);expires=datetime.now(timezone.utc)+timedelta(days=7)
    conn.execute('INSERT INTO chat_web_sessions(token_hash,owner_id,role,expires_at,authenticated) VALUES(%s,%s,%s,%s,true)',(hashlib.sha256(token.encode()).hexdigest(),owner,'operator',expires))
    response.set_cookie(COOKIE,token,max_age=604800,httponly=True,secure=request.url.scheme=='https',samesite='strict',path='/api/v1/chat')
    response.headers['Cache-Control']='no-store'
    account=conn.execute('SELECT email,display_name FROM chat_accounts WHERE id=%s',(owner,)).fetchone()
    return {**account,'owner_id':owner,'role':'operator','expires_at':expires,'csrf':csrf(token)}

def register(request,response,email,display_name,password):
    origin_check(request);email=normalize_email(email);display_name=display_name.strip()
    if not 2<=len(display_name)<=80:raise HTTPException(422,'Indiquez un nom de 2 à 80 caractères.')
    if not 12<=len(password)<=128:raise HTTPException(422,'Le mot de passe doit contenir de 12 à 128 caractères.')
    throttle(request,email,'register');encoded=password_hash(password)
    with db.connection() as conn:
        owner=uuid4();old=request.cookies.get(COOKIE,'')
        if old:
            legacy=conn.execute('SELECT owner_id,authenticated,expires_at FROM chat_web_sessions WHERE token_hash=%s FOR UPDATE',(hashlib.sha256(old.encode()).hexdigest(),)).fetchone()
            if legacy and not legacy['authenticated'] and legacy['expires_at']>datetime.now(timezone.utc):owner=legacy['owner_id']
        if conn.execute('SELECT id FROM chat_accounts WHERE email=%s',(email,)).fetchone():raise HTTPException(409,'Cette inscription n’est pas disponible. Utilisez la connexion.')
        conn.execute('INSERT INTO chat_accounts(id,email,display_name,password_hash) VALUES(%s,%s,%s,%s)',(owner,email,display_name,encoded))
        user=establish(conn,request,response,owner)
    return public(user)

def login(request,response,email,password):
    origin_check(request);email=normalize_email(email)
    if len(password)>128:raise HTTPException(401,'E-mail ou mot de passe incorrect.')
    throttle(request,email,'login')
    with db.connection() as conn:account=conn.execute('SELECT id,password_hash,active FROM chat_accounts WHERE email=%s',(email,)).fetchone()
    valid=verify_password(password,account['password_hash'] if account else _DUMMY)
    if not account or not valid or not account['active']:raise HTTPException(401,'E-mail ou mot de passe incorrect.')
    with db.connection() as conn:user=establish(conn,request,response,account['id'])
    return public(user)

def logout(request,response):
    operator(request)
    with db.connection() as conn:conn.execute('DELETE FROM chat_web_sessions WHERE token_hash=%s',(hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest(),))
    response.delete_cookie(COOKIE,path='/api/v1/chat',secure=request.url.scheme=='https',httponly=True,samesite='strict')
    response.headers['Cache-Control']='no-store'
    return {'signed_out':True}
