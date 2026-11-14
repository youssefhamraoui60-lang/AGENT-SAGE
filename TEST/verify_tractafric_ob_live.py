"""Verify the production chat draft only; never approve or execute a Sage write."""
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx
from http_test_account import authenticate_test_client

BASE = 'http://127.0.0.1:8000'
TEXT = 'Bonjour, Je vous prie de bien vouloir procéder à la création du fournisseur suivant dans le système :   Nom de frs : TRACTAFRIC EQUIPMENT MAROC    Ice : 001524532000071  Je reste à votre disposition pour toute information complémentaire.    Cordialement.'


def main():
    with httpx.Client(base_url=BASE, headers={'Origin': BASE}, timeout=30, trust_env=False) as client:
        response = client.get('/health')
        response.raise_for_status()
        account = authenticate_test_client(client)
        client.headers['X-Chat-CSRF'] = account['csrf']
        response = client.post('/api/v1/chat/conversations', json={'discussion_mode': 'supplier_ob'})
        response.raise_for_status()
        session = response.json()
        path = '/api/v1/chat/conversations/' + session['id'] + '/analysis-jobs'
        response = client.post(path, json={'content': TEXT, 'revision': session['revision'], 'request_id': str(uuid4())})
        response.raise_for_status()
        value = response.json()
        job_id = value['job']['id']
        print('Analysis accepted; observing draft preparation.', flush=True)
        started = time.monotonic()
        while value['job']['status'] not in ('completed', 'failed', 'interrupted', 'verification_incomplete'):
            if time.monotonic() - started > 180:
                raise RuntimeError('Observation timeout; no resubmission')
            time.sleep(1)
            response = client.get(path + '/' + job_id)
            response.raise_for_status()
            value = response.json()
        session = value['conversation']
        partners = session['state'].get('partners', [])
        report = {
            'conversation_id': session['id'], 'job_status': value['job']['status'],
            'partners': [{'name': p.get('nom'), 'ice': p.get('ice'), 'folder': p.get('dossier_cible'),
                          'approved': p.get('approved'), 'operation': p.get('operation')} for p in partners],
            'reply': session['messages'][-1]['content'], 'sage_write_routes_called': 0,
        }
        Path(__file__).with_name('tractafric-ob-live-verification.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({**report, 'partners': [{k: p[k] for k in ('name', 'ice', 'folder', 'approved')} |
                         {'status': (p.get('operation') or {}).get('status')} for p in report['partners']]}, ensure_ascii=True), flush=True)
        assert value['job']['status'] == 'completed'
        assert len(partners) == 1 and partners[0]['nom'] == 'TRACTAFRIC EQUIPMENT MAROC'
        assert partners[0]['ice'] == '001524532000071' and partners[0]['dossier_cible'] == 'OB'
        assert not partners[0].get('approved')
        assert 'Le service IA ne permet pas' not in report['reply']


if __name__ == '__main__':
    main()
