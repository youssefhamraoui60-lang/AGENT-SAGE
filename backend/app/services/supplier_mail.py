"""Dedicated IMAP supplier channel. Never changes the interactive agent policy.

Claim before analysis, preserve ambiguous attempts, never replay a claimed email.
The TEST runner uses the same actions with a server-selected TEST target.
"""
import asyncio
import hashlib
import imaplib
import json
import re
import sqlite3
import ssl
import unicodedata
from contextlib import closing
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.services import supplier_mail_replies as replies


def matches_subject(subject):
    text = ''.join(c for c in unicodedata.normalize('NFKD', subject or '')
                   if not unicodedata.combining(c)).upper()
    return bool(re.search(r'\b(?:OB|SOB)\b', text) and
                re.search(r'\b(?:FOURNISSEURS?|FROURNISEURS?|FOURNISEURS?|FRS)\b', text))


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'): self.hidden += 1
        if tag in ('p', 'br', 'div', 'tr'): self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)


def normalize_supplier_body(body):
    """Remove transport headers and retain explicit supplier field values literally."""
    lines = []
    for line in body.replace('\r\n', '\n').splitlines():
        stripped = line.strip()
        if re.match(r'^(?:From|Sent|To|Cc|Bcc|Subject|De|Envoy[e\u00e9]|[\u00c0A]|Objet)\s*:', stripped, re.I): continue
        if re.match(r'^(?:Envoy[e\u00e9] [\u00e0a] partir de|Sent from)\b', stripped, re.I): continue
        if re.fullmatch(r'[_\-\s]+', stripped): continue
        lines.append(line)
    text = '\n'.join(lines).strip()
    # Outlook often has one slash-delimited line after "fournisseur suivant".
    intro = re.search(r'\bcr[e\u00e9]er\s+(?:(?:le|un|ce|nouveau)\s+)*fournisseur\s*(?:suivant\s*)?[:=]?\s*', text, re.I)
    if not intro: return text
    if re.search(r'\b(?:ne|pas|annul\w*|modifi\w*|corrig\w*|articles?|clients?)\b', text[:intro.start()], re.I): return text
    content = text[intro.end():]
    labels = r'adresse|ice|if|rc|num[e\u00e9]ro|t[e\u00e9]l[e\u00e9]phone|telephone|t[e\u00e9]l|tel|ville|paiement|pays|devise|fax'
    boundary = re.search(r'(?:[,;/\n]+\s*|\s*:\s*)(?=(?:'+labels+r')\s*[:=])', content, re.I)
    if boundary and content[:boundary.start()].strip(' ,;/\n'):
        name = content[:boundary.start()].strip(' ,;/\n')
        # Already labelled forms remain for the established parser.
        if not re.match(r'^(?:nom|raison sociale)\s*:', name, re.I):
            content = 'Nom : ' + name + '\n' + content[boundary.end():]
    content = re.sub(r'[,;/]*\s*:?\s*\b('+labels+r')\s*[:=]\s*',
                     lambda m: '\n' + ('Telephone' if re.fullmatch(r'num[e\u00e9]ro|t[e\u00e9]l(?:[e\u00e9]phone)?|telephone', m[1], re.I) else m[1]) + ' : ',
                     content, flags=re.I)
    return 'Cr\u00e9er un fournisseur\n' + content.strip()


def parse_message(raw):
    if len(raw) > 2_000_000: raise ValueError('message_too_large')
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    subject = str(msg.get('Subject', ''))
    if not matches_subject(subject): return None
    # Never silently ignore supplier data supplied only in a document.
    if any(p.get_content_disposition() == 'attachment' for p in msg.walk()):
        raise ValueError('attachments_require_text_body_without_attachments')
    part = msg.get_body(preferencelist=('plain', 'html'))
    if part is None: raise ValueError('empty_body')
    body = part.get_content()
    if part.get_content_type() == 'text/html':
        parser = HTMLText(); parser.feed(body); body = ''.join(parser.parts)
    text = normalize_supplier_body(body)
    if not body.strip() or len(text) > 11500: raise ValueError('invalid_body_length')
    return {'text': text, 'subject': subject, 'message_id': str(msg.get('Message-ID', '')).strip()}


def connect():
    if not settings.gmail_user or not settings.gmail_app_password.get_secret_value():
        raise ValueError('gmail_credentials_missing')
    client = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port,
                              ssl_context=ssl.create_default_context(), timeout=20)
    try:
        client.login(settings.gmail_user, ''.join(settings.gmail_app_password.get_secret_value().split()))
    except Exception:
        client.shutdown(); raise
    return client


def check_connection():
    client = connect()
    try:
        status, _ = client.select('INBOX', readonly=True)
        if status != 'OK': raise ValueError('inbox_unavailable')
        return {'imap': 'ok', 'inbox': 'ok', 'writes': 0}
    finally:
        client.logout()


def ledger():
    path = Path(settings.supplier_mail_state_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute('''CREATE TABLE IF NOT EXISTS messages (
        key TEXT PRIMARY KEY, folder TEXT NOT NULL, status TEXT NOT NULL,
        conversation TEXT, result TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS replies (
        key TEXT PRIMARY KEY, status TEXT NOT NULL, message_id TEXT NOT NULL, recipient TEXT NOT NULL,
        error_type TEXT, sent_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS activations (
        folder TEXT PRIMARY KEY, mailbox TEXT NOT NULL, uidvalidity TEXT NOT NULL,
        min_uid INTEGER NOT NULL, activated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    return conn


def activation_cutoff(conn, client, folder):
    row = conn.execute('SELECT mailbox,uidvalidity,min_uid FROM activations WHERE folder=?', (folder,)).fetchone()
    if row is None: return 0
    if row[0] != settings.gmail_user.lower(): raise ValueError('mail_activation_account_mismatch')
    _, values = client.response('UIDVALIDITY')
    current = values[0].decode('ascii') if values and values[0] else ''
    if current != row[1]: raise ValueError('mail_uidvalidity_changed_requires_review')
    return row[2]


def claim(conn, key, folder):
    cursor = conn.execute('INSERT OR IGNORE INTO messages(key,folder,status) VALUES(?,?,?)',
                          (key, folder, 'claimed'))
    conn.commit()
    return cursor.rowcount == 1


def save(conn, key, status, conversation=None, result=None):
    conn.execute('UPDATE messages SET status=?,conversation=COALESCE(?,conversation),result=? WHERE key=?',
                 (status, str(conversation) if conversation else None, json.dumps(result or {}), key))
    conn.commit()


def assert_supplier_scope(session, folder):
    state = session['state']
    if state.get('supplier_target', 'TEST') != folder:
        raise ValueError('mail_target_mismatch')
    if state.get('articles') or state.get('pending_correction') or state.get('_pending') or state.get('document_review'):
        raise ValueError('mail_scope_or_analysis_incomplete')
    if any(p.get('kind') != 'supplier' or p.get('dossier_cible', 'TEST') != folder
           for p in state.get('partners', [])):
        raise ValueError('mail_supplier_scope_required')
    if any(d.get('resource') != 'supplier' or d.get('folder', 'TEST') != folder
           for d in state.get('modification_drafts', [])):
        raise ValueError('mail_supplier_modification_scope_required')


class MailBlocked(ValueError):
    def __init__(self, operation):
        validation = operation.get('validation') or {}
        duplicates = validation.get('diagnostics') or operation.get('duplicate_warnings') or []
        codes = sorted({str(d.get('duplicate_code') or d.get('code')) for d in duplicates
                        if d.get('duplicate_code') or d.get('code')})
        self.result = {'status': 'blocked_duplicate' if codes else 'requires_review',
                       'reason': 'supplier_already_exists' if codes else 'supplier_not_prepared',
                       'message': validation.get('message') or operation.get('message') or 'Supplier validation blocked',
                       'existing_codes': codes}
        super().__init__(self.result['reason'])


async def process_text(text, folder, checkpoint=lambda identifier: None):
    """Operator authorization is the mail channel configuration, never email text."""
    from app.services import conversation_chat as chat
    from app.services.chat_supplier_actions import action as create_action
    from app.services.modification_actions import action as modify_action
    if folder not in ('TEST', 'OB'): raise ValueError('invalid_mail_folder')
    owner = UUID(settings.supplier_mail_owner_id)
    session = chat.create(owner, 'supplier_ob' if folder == 'OB' else 'supplier')
    identifier = session['id']; checkpoint(identifier)
    from app.services import business_store as db
    with db.connection() as conn:
        chat.append(conn, identifier, 'system',
                    'Canal e-mail fournisseur : approbation automatique autorisee par la configuration operateur.',
                    {'channel': 'supplier_mail', 'automatic_approval': True, 'folder': folder})
    session = await chat.send(owner, identifier, text, session['revision'])
    assert_supplier_scope(session, folder)
    partners = list(session['state'].get('partners', []))
    modifications = list(session['state'].get('modification_drafts', []))
    if not partners and not modifications:
        return {'status': 'needs_input', 'conversation': str(identifier), 'writes': 0}
    # Validate the whole message before approving any operation.
    for p in partners:
        if not p.get('checks', {}).get('valid_basic'): raise ValueError('supplier_data_incomplete')
        op = p.get('operation') or {}
        if not op:
            session = create_action(owner, identifier, p['id'], 'prepare', session['revision'])
        elif op.get('status') != 'prepared': raise MailBlocked(op)
    for p in session['state'].get('partners', []):
        op = p.get('operation') or {}
        if op.get('status') != 'prepared' or op.get('duplicate_warnings') or op.get('draft_only_fields'):
            raise ValueError('supplier_validation_or_unsupported_fields')
    for d in modifications:
        if d.get('operation', {}).get('status') != 'prepared': raise ValueError('modification_not_prepared')
    results = []
    for p in partners:
        session = create_action(owner, identifier, p['id'], 'approve', session['revision'], confirm=True)
        from app.services.chat_storage import execution_space
        with execution_space({'owner_id': owner, 'email': settings.gmail_user}, identifier):
            session = create_action(owner, identifier, p['id'], 'execute', session['revision'], confirm=True)
        op = next(x for x in session['state']['partners'] if x['id'] == p['id'])['operation']
        verified = op.get('result', {}).get('supplier_verification', {}).get('record', {})
        results.append({'kind': 'create', 'status': op['status'], 'keys': op.get('record_keys', {}),
                        'name': verified.get('RAISON_SOCIALE') or verified.get('BPSNAM_0'),
                        'ice': verified.get('ICE') or verified.get('XICE_0')})
        if op['status'] != 'succeeded': break
    else:
        for d in modifications:
            session = modify_action(owner, identifier, d['id'], 'approve', session['revision'], confirm=True, sensitive_confirm=True)
            from app.services.chat_storage import execution_space
            with execution_space({'owner_id': owner, 'email': settings.gmail_user}, identifier):
                session = modify_action(owner, identifier, d['id'], 'execute', session['revision'], confirm=True, sensitive_confirm=True)
            updated = next(x for x in session['state']['modification_drafts'] if x['id'] == d['id'])
            op = updated['operation']
            values = {**updated.get('current', {}), **updated.get('changes', {})} if op['status'] == 'succeeded' else {}
            results.append({'kind': 'modify', 'status': op['status'], 'code': d['code'],
                            'name': values.get('name'), 'ice': values.get('ice')})
            if op['status'] != 'succeeded': break
    return {'status': 'succeeded' if all(r['status'] == 'succeeded' for r in results) else 'requires_readback',
            'conversation': str(identifier), 'operations': results}


def poll(folder=None):
    folder = folder or settings.supplier_mail_folder
    if folder not in ('TEST', 'OB'): raise ValueError('invalid_mail_folder')
    UUID(settings.supplier_mail_owner_id)  # Fail before claiming messages if not configured.
    client = connect(); outcomes = []
    try:
        status, _ = client.select('INBOX', readonly=True)
        if status != 'OK': raise ValueError('inbox_unavailable')
        # PEEK + readonly leave read/unread flags unchanged; ledger is authoritative.
        status, data = client.uid('search', None, '(OR SUBJECT "OB" SUBJECT "SOB")')
        if status != 'OK': raise ValueError('mail_search_failed')
        with closing(ledger()) as conn:
            minimum_uid = activation_cutoff(conn, client, folder)
            for uid in data[0].split():
                if int(uid) < minimum_uid: continue
                status, parts = client.uid('fetch', uid, '(BODY.PEEK[HEADER] RFC822.SIZE)')
                if status != 'OK': continue
                header = next((p[1] for p in parts if isinstance(p, tuple)), None)
                if not header: continue
                headers = BytesParser(policy=policy.default).parsebytes(header, headersonly=True)
                if replies.automatic(headers) or not matches_subject(str(headers.get('Subject', ''))): continue
                msgid = str(headers.get('Message-ID', '')).strip()
                def message_key(identity):
                    return hashlib.sha256((settings.gmail_user.lower() + '\0' + folder + '\0' + identity).encode()).hexdigest()
                key = message_key(msgid) if msgid else None
                existing = conn.execute('SELECT status,conversation,result FROM messages WHERE key=?', (key,)).fetchone() if key else None
                if existing:
                    stored = json.loads(existing[2] or '{}')
                    stored['status'] = existing[0]
                    if existing[1]: stored['conversation'] = existing[1]
                    delivery = replies.notify(conn, key, headers, stored, folder)
                    if delivery: outcomes.append({'status': existing[0], 'reply': delivery})
                    continue
                sizes = [re.search(rb'RFC822.SIZE\s+(\d+)', p[0]) for p in parts if isinstance(p, tuple)]
                if any(match and int(match[1]) > 2_000_000 for match in sizes):
                    key = key or message_key(hashlib.sha256(header).hexdigest())
                    if claim(conn, key, folder):
                        result = {'status': 'requires_review', 'reason': 'message_too_large'}
                        save(conn, key, result['status'], result=result)
                        result['reply'] = replies.notify(conn, key, headers, result, folder)
                        outcomes.append(result)
                    continue
                status, parts = client.uid('fetch', uid, '(BODY.PEEK[])')
                if status != 'OK': continue
                raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
                if not raw: continue
                key = key or message_key(hashlib.sha256(raw).hexdigest())
                if not claim(conn, key, folder): continue
                try:
                    message = parse_message(raw)
                    result = asyncio.run(process_text(message['text'], folder,
                        lambda identifier: save(conn, key, 'processing', identifier)))
                    save(conn, key, result['status'], result.get('conversation'), result)
                except Exception as exc:
                    # Never retry: an interrupted SQL execution might have committed.
                    result = exc.result if isinstance(exc, MailBlocked) else {'status': 'requires_review', 'error_type': type(exc).__name__, 'reason': str(exc) if isinstance(exc, ValueError) else 'processing_failed_see_conversation'}
                    save(conn, key, result['status'], result=result)
                row = conn.execute('SELECT conversation FROM messages WHERE key=?', (key,)).fetchone()
                if row and row[0]: result['conversation'] = row[0]
                result['reply'] = replies.notify(conn, key, headers, result, folder)
                outcomes.append(result)
    finally:
        client.logout()
    return {'folder': folder, 'messages': outcomes}
