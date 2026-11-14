"""Disposable account for real HTTP verification scripts; no credentials are logged."""
import secrets
from uuid import uuid4

def authenticate_test_client(client):
    response=client.post('/api/v1/chat/auth/register',json={'email':'verification-'+uuid4().hex+'@example.test','display_name':'Vérification Test','password':secrets.token_urlsafe(24)})
    response.raise_for_status()
    return response.json()
