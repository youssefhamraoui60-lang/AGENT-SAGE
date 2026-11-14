"""Real HTTP article intake checks; no approval or Sage write endpoints."""
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx
from http_test_account import authenticate_test_client

TEXT = 'Bonjour, Merci de créer les 2 références d article. Fournisseur RZ timber qui est déjà existant MADRIER 37*177*4  MADRIER 37*177*3 Cdlt'
BASE = 'http://127.0.0.1:8000'


def main():
    with httpx.Client(base_url=BASE, headers={'Origin': BASE}, timeout=30, trust_env=False) as client:
        account = authenticate_test_client(client)
        client.headers['X-Chat-CSRF'] = account['csrf']
        response = client.post('/api/v1/chat/conversations', json={'discussion_mode': 'supplier_ob'})
        response.raise_for_status()
        session = response.json()
        reports = []
        ids = None
        for attempt in range(2):
            path = '/api/v1/chat/conversations/' + session['id'] + '/analysis-jobs'
            response = client.post(path, json={'content': TEXT, 'revision': session['revision'], 'request_id': str(uuid4())})
            response.raise_for_status()
            value = response.json()
            job = value['job']['id']
            started = time.monotonic()
            while value['job']['status'] not in ('completed', 'failed', 'interrupted', 'verification_incomplete'):
                if time.monotonic() - started > 180:
                    raise RuntimeError('Observation timeout; no automatic retry')
                time.sleep(1)
                response = client.get(path + '/' + job)
                response.raise_for_status()
                value = response.json()
            session = value['conversation']
            articles = session['state'].get('articles', [])
            reply = session['messages'][-1]['content']
            print(json.dumps({'reply': reply, 'phase': value['job'].get('phase')}, ensure_ascii=True), flush=True)
            assert value['job']['status'] == 'completed'
            assert [a['designation'] for a in articles] == ['MADRIER 37*177*4', 'MADRIER 37*177*3']
            assert all(a.get('fournisseur_nom') == 'RZ timber' and a.get('dossier_cible') == 'OB' for a in articles)
            assert all(not a.get('approved') for a in articles)
            assert not session['state'].get('partners')
            assert reply.count('Quelle catégorie') == 1
            assert 'Catégories existantes dans OB' in reply
            current_ids = [a['id'] for a in articles]
            if ids is not None:
                assert current_ids == ids
            ids = current_ids
            reports.append({'attempt': attempt + 1, 'draft_ids': ids, 'reply': reply})
            print('Batch attempt '+str(attempt + 1)+': exactly two OB drafts, one category question.', flush=True)
        report = {'status': 'PASS', 'conversation_id': session['id'], 'sage_write_routes_called': 0, 'checks': reports}
        Path(__file__).with_name('madrier-ob-live-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
