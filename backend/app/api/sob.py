"""Authenticated bridge to the independent SOB service; no article logic changes."""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.services import chat_auth as auth

router = APIRouter(prefix='/api/v1/chat/sob', tags=['Commandes SOB'])
ALLOWED = {
    ('GET', 'status'), ('GET', 'conversation'), ('DELETE', 'conversation'),
    ('POST', 'chat'), ('POST', 'orders/confirm'), ('GET', 'creation-permissions.sql'),
    ('GET','learning'), ('POST','learning/article-alias'),
    ('POST','preparations/load'),
}


def sob_identity(request: Request):
    return auth.identity(request) if request.method == 'GET' else auth.operator(request)


@router.api_route('/{path:path}', methods=['GET', 'POST', 'DELETE'])
async def bridge(path: str, request: Request, user=Depends(sob_identity)):
    if (request.method, path) not in ALLOWED:
        raise HTTPException(404, 'API SOB inconnue.')
    body = await request.body()
    if len(body) > 50000:
        raise HTTPException(413, 'Demande trop volumineuse.')
    # One upstream session per browser AND authenticated account. Never forward
    # the Sage account cookie or credentials to the independent service.
    cookie_name = 'sage_sob_' + str(user['owner_id']).replace('-', '')
    cookies = {}
    if request.cookies.get(cookie_name):
        cookies['sob_session'] = request.cookies[cookie_name]
    try:
        async with httpx.AsyncClient(timeout=240, trust_env=False, follow_redirects=False, cookies=cookies) as client:
            upstream = await client.request(request.method, 'http://127.0.0.1:8011/api/sob/' + path,
                                            content=body,
                                            headers={'Content-Type': 'application/json','X-SOB-Actor':str(user['owner_id'])})
    except httpx.HTTPError:
        raise HTTPException(503, 'Service SOB indisponible. En cas de validation en cours, vérifier le reçu avant toute nouvelle commande.') from None
    response = Response(upstream.content, status_code=upstream.status_code,
                        media_type=upstream.headers.get('content-type', 'application/json'))
    response.headers['Cache-Control'] = 'no-store'
    if upstream.cookies.get('sob_session'):
        response.set_cookie(cookie_name, upstream.cookies['sob_session'], httponly=True,
                            secure=request.url.scheme == 'https', samesite='strict',
                            path='/api/v1/chat/sob', max_age=28800)
    return response
