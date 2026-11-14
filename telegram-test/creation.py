"""Server-owned reviews and durable creation receipts. No LLM-generated SQL."""
import json
import sqlite3
import subprocess
import time
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
LEDGER = HERE.parent / 'runtime/sob-orders.sqlite3'


class CreationError(Exception):
    pass


def connection():
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(LEDGER, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS reviews (
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL,
        plan TEXT NOT NULL, expires REAL NOT NULL, status TEXT NOT NULL,
        number TEXT, error TEXT)''')
    return db


def run_script(script, request):
    try:
        proc = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(HERE / script)],
                              input=json.dumps(request, ensure_ascii=False), capture_output=True,
                              encoding='utf-8', timeout=65)
        if proc.returncode:
            raise CreationError('Service SQL indisponible.')
        return json.loads(proc.stdout.lstrip('\ufeff'))
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        raise CreationError('Résultat SQL indisponible ; vérifier le reçu avant toute nouvelle demande.') from None


def permissions():
    result = run_script('sob-read.ps1', {'kind': 'permissions', 'code': 'check'})
    if not result.get('ok') or not result.get('rows'):
        return {'ready': False, 'missing': ['Vérification SQL indisponible']}
    row = result['rows'][0]
    missing = [name for name, value in row.items() if value != 1]
    return {'ready': not missing, 'missing': missing}


def invalidate(owner):
    with connection() as db:
        if db.execute("SELECT 1 FROM reviews WHERE owner=? AND status IN ('pending','uncertain') LIMIT 1", (owner,)).fetchone():
            raise CreationError('Une création est en cours ou son résultat est incertain. Vérifier le reçu avant une nouvelle préparation.')
        db.execute("UPDATE reviews SET status='superseded' WHERE owner=? AND status='ready'", (owner,))


def build_payload(details, *, reference_date=None):
    if details['missing'] or not details['client'] or not details['lines']:
        raise CreationError('Compléter les informations du brouillon avant validation.')
    client = details['client']
    if not re.fullmatch(r'C[0-9]{4,8}',client['BPCNUM_0'].strip()) or client['CUR_0'].strip() != 'MAD':
        raise CreationError('Client Sage ou devise MAD à vérifier.')
    today = reference_date or datetime.now(ZoneInfo('Europe/Paris')).date()
    try:
        delivery = date.fromisoformat(details['delivery'] or '')
    except ValueError:
        raise CreationError('Préciser une date de livraison valide avant création.') from None
    if today.year != 2026 or delivery < today:
        raise CreationError('Date hors périmètre : année de commande 2026, livraison à partir du jour de commande.')
    lines = []
    total = Decimal(0)
    for i, line in enumerate(details['lines'], 1):
        article = line['article'].strip().upper()
        if article in ('TRS', 'TRC', 'TRANSPORT', 'MANUTENTION'):
            article = 'MANTD'
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9_./-]{0,39}',article):
            raise CreationError('Code article Sage à vérifier : ' + line['article'])
        try:
            qty, price = Decimal('1') if article == 'MANTD' else Decimal(str(line['quantity'])), Decimal(str(line['price']))
        except Exception:
            raise CreationError('Quantité et prix nécessaires.') from None
        if not qty.is_finite() or not price.is_finite() or qty <= 0 or price < 0:
            raise CreationError('Quantité ou prix invalide.')
        if max(qty, price) >= Decimal('1000000000000') or qty.as_tuple().exponent < -5 or price.as_tuple().exponent < -5:
            raise CreationError('Quantité/prix hors précision SQL (5 décimales maximum).')
        total += (qty * price).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        supplier = line.get('supplier')
        if supplier and not re.fullmatch(r'F[A-Z0-9_-]{1,29}',supplier):
            raise CreationError('Code fournisseur Sage invalide.')
        tax_code=line.get('tax_code')
        if tax_code and (tax_code!='T00' or article!='MANTD' or line.get('tax_source')!='document_transport_exempt'):
            raise CreationError('Exonération non vérifiée sur la ligne de transport.')
        lines.append({'line': i * 1000, 'article': article, 'quantity': str(qty), 'price': str(price), **({'supplier': supplier} if supplier else {}), **({'tax_code':tax_code} if tax_code else {})})
    if len(lines) > 20:
        raise CreationError('20 lignes maximum.')
    identifier = uuid4().hex
    comment=details.get('delivery_note') or 'SOB - creation TEST'
    comment=re.sub(r'\s*;\s*','; ',re.sub(r'\s+',' ',comment)).strip()
    from delivery_notes import compact
    comment=compact(comment)
    if len(comment)>100:
        raise CreationError('Indication de livraison à raccourcir à 100 caractères pour Sage.')
    return {'mode': 'preview', 'review_id': identifier, 'reference': 'SOB-' + identifier[:16], 'client': client['BPCNUM_0'].strip(),
            'comment':comment,
            'representative': (details.get('representative') or {}).get('REPNUM_0',client.get('REP_0','')).strip(),
            'order_date': today.isoformat(), 'delivery': delivery.isoformat(),
            'lines': lines, 'total': str(total)}


def review(owner, details):
    payload = build_payload(details)
    result = run_script('sob-execute.ps1', payload)
    if not result.get('ok'):
        raise CreationError('Contrôle SQL refusé (code ' + str(result.get('code', 0)) + '). Vérifier les données Sage.')
    row = next((r for r in result['rows'] if r.get('RESULTAT') == 'PREVIEW'), None)
    if not row:
        raise CreationError('Récapitulatif SQL indisponible.')
    plan = row['PLAN_JSON']
    identifier = payload['review_id']
    expires = time.time() + 900
    with connection() as db:
        db.execute('INSERT INTO reviews(id,owner,payload,plan,expires,status) VALUES(?,?,?,?,?,?)',
                   (identifier, owner, json.dumps(payload), plan, expires, 'ready'))
    return public_review(identifier, json.loads(plan), expires)


def public_review(identifier, plan, expires):
    return {'id': identifier, 'expires': expires, 'plan': plan,
            'warning': 'Création SQL directe dans TEST, selon ta requête testée. Signature non gérée, TVA vérifiée par ligne. Valider dans Sage avant livraison ou facturation.',
            'permissions': permissions()}


def get_review(owner, identifier):
    with connection() as db:
        row = db.execute('SELECT * FROM reviews WHERE id=? AND owner=?', (identifier, owner)).fetchone()
    if row is None:
        raise CreationError('Validation introuvable pour cette conversation.')
    return row


def confirm(owner, identifier, *, human_validated=False):
    row = get_review(owner, identifier)
    payload = json.loads(row['payload'])
    reference = payload['reference']
    if row['status'] == 'created':
        return {'status': 'created', 'number': row['number'], 'reference': reference}
    if row['status'] in ('pending', 'uncertain'):
        # Never retry a write after an ambiguous result. Reconcile by server reference.
        found = run_script('sob-read.ps1', {'kind': 'receipt', 'code': reference})
        if found.get('ok') and len(found.get('rows', [])) == 1:
            number = found['rows'][0]['SOHNUM_0']
            with connection() as db:
                db.execute("UPDATE reviews SET status='created',number=? WHERE id=?", (number, identifier))
            return {'status': 'created', 'number': number, 'reference': reference}
        if found.get('ok') and not found.get('rows') and row['error'] in ('2628', '8152'):
            with connection() as db:
                db.execute("UPDATE reviews SET status='failed' WHERE id=?", (identifier,))
            raise CreationError('La transaction a été annulée : référence trop longue dans la version précédente. Préparer à nouveau la commande corrigée.')
        raise CreationError('Résultat incertain. Aucune relance automatique. Faire vérifier la référence ' + reference + ' dans Sage.')
    if not human_validated:
        raise CreationError('Validation humaine obligatoire. Aucune commande créée.')
    if row['status'] != 'ready' or row['expires'] < time.time():
        raise CreationError('Récapitulatif expiré ou remplacé. Préparer à nouveau la commande.')
    if payload['order_date'] != datetime.now(ZoneInfo('Europe/Paris')).date().isoformat():
        raise CreationError('Le jour de commande a changé. Refaire le récapitulatif.')
    if not permissions()['ready']:
        raise CreationError('Droits de création absents : exécuter sage-sob-enable-creation.sql avec un administrateur dans SSMS.')
    with connection() as db:
        changed = db.execute("UPDATE reviews SET status='pending' WHERE id=? AND owner=? AND status='ready'", (identifier, owner)).rowcount
        if changed != 1:
            raise CreationError('Validation déjà en cours.')
    payload.update(mode='create', expected_plan=row['plan'])
    try:
        result = run_script('sob-execute.ps1', payload)
        if not result.get('ok'):
            code = result.get('code', 0)
            # Only a server error known to roll back its transaction is a definite failure.
            definite = isinstance(code, int) and (61001 <= code <= 62099 or code in (229, 2627, 2628, 8152, 2601, 1205, 547, 515))
            with connection() as db:
                db.execute('UPDATE reviews SET status=?,error=? WHERE id=?',
                           ('failed' if definite else 'uncertain', str(code), identifier))
            raise CreationError('Création refusée, transaction annulée (SQL ' + str(code) + '). Refaire le récapitulatif.' if definite else 'Résultat SQL incertain. Vérifier le reçu ; ne pas recréer la commande.')
        number = next((r.get('NUMERO_COMMANDE') for r in result['rows'] if r.get('NUMERO_COMMANDE')), None)
        if not number:
            raise CreationError('Reçu de création absent. Faire vérifier la référence avant toute nouvelle demande.')
        with connection() as db:
            db.execute("UPDATE reviews SET status='created',number=? WHERE id=?", (number, identifier))
        return {'status': 'created', 'number': number, 'reference': payload['reference']}
    except Exception:
        with connection() as db:
            db.execute("UPDATE reviews SET status='uncertain' WHERE id=? AND status='pending'", (identifier,))
        raise
