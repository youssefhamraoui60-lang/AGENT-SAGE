"""Disabled-by-default, allowlisted public PKI objects on existing FastAPI.
Publishing/binding changes require approval; this does not start a listener.
"""
import hashlib,json,ipaddress
from datetime import datetime,timezone
from pathlib import Path
from fastapi import APIRouter,HTTPException,Request,Response
from app.core.config import settings

router=APIRouter(prefix='/pki',tags=['Public PKI distribution'])
PUBLIC_ROOT=Path(__file__).resolve().parents[3]/'certs/approved-production'
FILES={'root.crl':'application/pkix-crl','issuing.crl':'application/pkix-crl','root.cer':'application/pkix-cert','issuing.cer':'application/pkix-cert'}

async def restrict_lan_to_public_pki(request:Request,call_next):
    if settings.pki_publication_enabled:
        try:local=ipaddress.ip_address(request.client.host).is_loopback
        except (ValueError,AttributeError):local=False
        # No forwarded headers trusted here; future launch must disable proxy headers.
        if not local and request.url.path not in {'/pki/'+name for name in FILES}:
            return Response(status_code=404)
    return await call_next(request)

@router.get('/{name}')
def download(name:str):
    if not settings.pki_publication_enabled or name not in FILES:raise HTTPException(404)
    try:
        directory=Path(settings.pki_publication_directory).resolve()
        if not directory.is_relative_to(PUBLIC_ROOT.resolve()):raise ValueError()
        manifest=json.loads((directory/'public-manifest.json').read_text(encoding='utf-8'))
        if manifest.get('status')!='APPROVED_PUBLIC_DISTRIBUTION':raise ValueError()
        entry=manifest['files'][name];file=(directory/name).resolve()
        if not file.is_relative_to(directory) or not file.is_file() or file.stat().st_size>2_000_000:raise ValueError()
        data=file.read_bytes()
        if b'PRIVATE KEY' in data or hashlib.sha256(data).hexdigest().upper()!=entry['sha256'].upper():raise ValueError()
        expires=datetime.fromisoformat(entry['expires_at'])
        remaining=(expires-datetime.now(timezone.utc)).total_seconds()
        if remaining<=0:raise ValueError()
        cache=min(300,max(0,int(remaining)-60))
    except (OSError,ValueError,KeyError,TypeError):raise HTTPException(503,'pki_object_unavailable') from None
    return Response(data,media_type=FILES[name],headers={'Cache-Control':f'public, max-age={cache}','X-Content-Type-Options':'nosniff'})
