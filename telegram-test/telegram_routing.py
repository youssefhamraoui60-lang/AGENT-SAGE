"""Persistent, operator-approved SOB source/response routing."""
import argparse
import json
import re
import sqlite3
import subprocess
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULE = 'telegram_group_routing'


def validate_policy(payload):
    source = payload.get('source_chat_id')
    response = payload.get('response_chat_id')
    if type(source) is not int or type(response) is not int or source >= 0 or response >= 0 or source == response:
        raise ValueError('Distinct Telegram source and response groups required')
    if payload.get('folder') != 'TEST' or payload.get('all_senders') is not True:
        raise ValueError('Only operator-approved all-sender TEST routing supported')
    return payload


def load_policy():
    process = subprocess.run([str(ROOT/'backend/.venv/Scripts/python.exe'), '-X', 'utf8',
                              str(Path(__file__).resolve()), '--load'],
                             capture_output=True, text=True, encoding='utf-8', timeout=20)
    if process.returncode: raise RuntimeError('SOB routing policy unavailable')
    return validate_policy(json.loads(process.stdout))


def privileged(text):
    return bool(re.match(r'(?i)^\s*(?:/?corrig(?:e|er)|correction|remplace(?:r)?)\b', text or '')
                or re.fullmatch(r"\s*(?:non[, :]\s*)?(?:l['\u2019]article|article)\s+.{1,80}?\s+(?:c['\u2019]est|est|correspond\s+[\u00e0a])\s+[A-Za-z][A-Za-z0-9_-]{0,39}\s*[.!]?\s*", text or '', re.I))


class RouteJournal:
    def __init__(self, path=None):
        self.path = Path(path or ROOT/'runtime/sob-telegram-routing.sqlite3')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY, source INTEGER NOT NULL, destination INTEGER NOT NULL,
                sender INTEGER NOT NULL, status TEXT NOT NULL, reply TEXT,
                destination_message INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS source_messages (
                source INTEGER NOT NULL, message INTEGER NOT NULL, batch TEXT NOT NULL,
                PRIMARY KEY(source,message))''')

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn: yield conn
        finally: conn.close()

    def claim(self, source, destination, sender, ids):
        if source == destination or not ids: raise ValueError('Invalid route')
        key = str(source)+':'+str(ids[0])
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if any(conn.execute('SELECT 1 FROM source_messages WHERE source=? AND message=?',
                                (source, mid)).fetchone() for mid in ids): return None
            conn.execute('INSERT INTO batches(id,source,destination,sender,status) VALUES(?,?,?,?,?)',
                         (key, source, destination, sender, 'executing'))
            conn.executemany('INSERT INTO source_messages VALUES(?,?,?)', [(source, mid, key) for mid in ids])
        return key

    def claim_replay(self, source, destination, sender, ids, day):
        """Explicit dated replay; preserve prior batches and block in-flight work."""
        if source == destination or not ids or not re.fullmatch(r'20\d{2}-\d{2}-\d{2}', day):
            raise ValueError('Invalid replay scope')
        key = str(source)+':'+str(ids[0])+':replay:'+day
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if conn.execute('SELECT 1 FROM batches WHERE id=?', (key,)).fetchone(): return None
            for mid in ids:
                previous = conn.execute('''SELECT b.status FROM source_messages m JOIN batches b ON b.id=m.batch
                    WHERE m.source=? AND m.message=?''', (source, mid)).fetchone()
                if previous and previous['status'] != 'sent': return None
            conn.execute('INSERT INTO batches(id,source,destination,sender,status) VALUES(?,?,?,?,?)',
                         (key, source, destination, sender, 'executing'))
            conn.executemany('''INSERT INTO source_messages VALUES(?,?,?)
                ON CONFLICT(source,message) DO UPDATE SET batch=excluded.batch''', [(source, mid, key) for mid in ids])
        return key

    def result(self, key, reply):
        with self.connection() as conn:
            conn.execute("UPDATE batches SET status='ready',reply=? WHERE id=? AND status='executing'", (reply, key))

    def begin_delivery(self, key):
        with self.connection() as conn:
            return conn.execute("UPDATE batches SET status='sending' WHERE id=? AND status='ready'", (key,)).rowcount == 1

    def delivered(self, key, message_id):
        with self.connection() as conn:
            conn.execute("UPDATE batches SET status='sent',destination_message=? WHERE id=? AND status='sending'", (message_id, key))

    def delivery_uncertain(self, key):
        with self.connection() as conn:
            conn.execute("UPDATE batches SET status='delivery_uncertain' WHERE id=? AND status='sending'", (key,))


async def publish(client, source, destination, ids, reply):
    """Reply only in the destination, linked to original source messages."""
    if source.id == destination.id: raise ValueError('Source and destination must differ')
    # Do not forward protected messages or expand the publication beyond the
    # requested result. Source links preserve attribution and message identity.
    source_id = str(source.id).removeprefix('-100')
    references = ', '.join('#'+str(mid) for mid in ids)
    link = 'https://t.me/c/'+source_id+'/'+str(ids[0]) if str(source.id).startswith('-100') else references
    text = str(reply) + '\n\nSource : ' + source.name + ' · ' + references + '\n' + link
    return await client.send_message(destination.entity, text[:4000], parse_mode=None)


def main():
    import learning_memory
    parser = argparse.ArgumentParser()
    parser.add_argument('--load', action='store_true')
    parser.add_argument('--save', action='store_true')
    args = parser.parse_args()
    if args.save:
        payload = validate_policy({'source_chat_id': -1004375687420,
            'source_name': 'sob commandes', 'response_chat_id': -5586539927,
            'response_name': 'COMMANDES SOB', 'folder': 'TEST', 'all_senders': True})
        learning_memory.save('policy', RULE, payload, actor='operator',
            source='Instruction utilisateur : lire les demandes du premier groupe multi-utilisateurs, créer dans TEST, répondre uniquement dans l’autre groupe COMMANDES SOB.', approved=True)
    rules = learning_memory.approved_rules()
    matches = [r['payload'] for r in rules if r['kind']=='policy' and r['rule_key']==RULE]
    if len(matches) != 1: raise ValueError('SOB routing policy missing or ambiguous')
    print(json.dumps(validate_policy(matches[0]), ensure_ascii=False))


if __name__ == '__main__': main()
