"""Threaded supplier status replies, sent once to the original message participants."""
import json
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import getaddresses, make_msgid, formatdate
from app.core.config import settings


def automatic(message):
    return (str(message.get('Auto-Submitted', 'no')).strip().lower() != 'no'
            or str(message.get('Precedence', '')).strip().lower() in ('bulk', 'list', 'junk')
            or bool(message.get('X-Auto-Response-Suppress')))


def recipient(message):
    if automatic(message): return None
    values = message.get_all('Reply-To') or message.get_all('From') or []
    addresses = getaddresses([str(value) for value in values])
    if len(addresses) != 1: return None
    address = addresses[0][1]
    if len(address) > 254 or not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+', address): return None
    if address.split('@')[0].lower() in ('mailer-daemon', 'postmaster'): return None
    return address


def reply_recipients(message):
    primary = recipient(message)
    if not primary: return None
    seen = {settings.gmail_user.strip().casefold()}
    groups = {'To': [], 'Cc': [], 'Bcc': []}
    for field, values in (
        ('To', [primary] + [str(v) for v in message.get_all('To', [])]),
        ('Cc', [str(v) for v in message.get_all('Cc', [])]),
        ('Bcc', [str(v) for v in message.get_all('Bcc', [])]),
    ):
        for _, address in getaddresses(values):
            if (len(address) > 254 or not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+', address)
                    or address.split('@')[0].lower() in ('mailer-daemon', 'postmaster')): continue
            identity = address.casefold()
            if identity in seen: continue
            seen.add(identity); groups[field].append(address)
    return groups if any(groups.values()) else None


def supplier_details(op):
    code = op.get('keys', {}).get('BPSNUM') or op.get('code') or 'Non disponible'
    return ['Code fournisseur : ' + str(code),
            'Nom du fournisseur : ' + str(op.get('name') or 'Non renseigné'),
            'ICE : ' + str(op.get('ice') or 'Non renseigné')]


def response_text(result, folder):
    lines = ['Bonjour,', '']
    status = result.get('status')
    if status == 'succeeded':
        for op in result.get('operations', []):
            if op.get('status') == 'succeeded':
                lines.append('Nous vous informons que le fournisseur a bien été '
                             + ('créé' if op.get('kind') == 'create' else 'modifié')
                             + ' dans le dossier ' + folder + '. Les informations ont été vérifiées.')
                lines += ['', *supplier_details(op), '']
    elif status == 'blocked_duplicate':
        lines.append('Le fournisseur existe déjà dans le dossier ' + folder + ' : ' + ', '.join(result.get('existing_codes', [])) + '. Aucune nouvelle fiche créée pour éviter un doublon.')
    elif status == 'requires_readback':
        lines.append('Le résultat d’une opération reste à vérifier. Ne renvoyez pas la demande avant vérification pour éviter une double opération.')
        for op in result.get('operations', []):
            if op.get('status') == 'succeeded':
                lines += ['Opération déjà effectuée dans ' + folder + ' :', *supplier_details(op)]
    else:
        reasons = {
            'attachments_require_text_body_without_attachments': 'Les pièces jointes ne sont pas traitées automatiquement. Envoyez les informations du fournisseur dans le corps du message, sans pièce jointe.',
            'supplier_data_incomplete': 'Les données du fournisseur sont incomplètes ou invalides. Vérifiez le nom, les identifiants fiscaux et les coordonnées.',
            'invalid_body_length': 'Le corps du message est vide ou trop long.',
            'empty_body': 'Le corps du message est vide.',
            'message_too_large': 'Le message dépasse la taille autorisée de 2 Mo.',
            'supplier_validation_or_unsupported_fields': 'Des champs ne peuvent pas être enregistrés par la création actuelle. La fiche doit être vérifiée.',
            'modification_not_prepared': 'La modification est bloquée par les contrôles métier et doit être vérifiée.',
            'mail_target_mismatch': 'Le dossier demandé ne correspond pas au dossier autorisé pour le canal e-mail.',
        }
        lines.append('Traitement non terminé dans ' + folder + ' : ' + reasons.get(result.get('reason'), 'Les informations ou le résultat doivent être vérifiés.'))
        if status == 'needs_input':
            lines.append('Indiquez explicitement la création ou la modification souhaitée et les informations du fournisseur dans le corps du message.')
    if status != 'succeeded' and result.get('conversation'): lines.append('Référence de suivi : ' + str(result['conversation']))
    if lines[-1] != '': lines.append('')
    lines += ['Cordialement,', 'Équipe SI.']
    return '\n'.join(lines)


def build_reply(original, result, folder):
    recipients = reply_recipients(original)
    if not recipients: return None
    reply = EmailMessage()
    reply['From'] = settings.gmail_user
    for field, addresses in recipients.items():
        if addresses: reply[field] = ', '.join(addresses)
    subject = re.sub(r'[\r\n]+', ' ', str(original.get('Subject', 'Demande fournisseur')))
    reply['Subject'] = subject if re.match(r'^re\s*:', subject, re.I) else 'Re: ' + subject
    reply['Message-ID'] = make_msgid()
    reply['Date'] = formatdate(localtime=False)
    message_id = str(original.get('Message-ID', '')).strip()
    if re.fullmatch(r'<[^\s<>]+@[^\s<>]+>', message_id):
        reply['In-Reply-To'] = message_id
        refs = re.findall(r'<[^\s<>]+@[^\s<>]+>', str(original.get('References', '')))[-10:]
        reply['References'] = ' '.join(refs + [message_id])
    reply['Auto-Submitted'] = 'auto-replied'
    reply['X-Auto-Response-Suppress'] = 'All'
    reply.set_content(response_text(result, folder))
    return reply


def send(reply):
    if settings.smtp_port == 465:
        transport = smtplib.SMTP_SSL(settings.smtp_host, 465, timeout=20, context=ssl.create_default_context())
    elif settings.smtp_port == 587:
        transport = smtplib.SMTP(settings.smtp_host, 587, timeout=20)
    else:
        raise ValueError('smtp_tls_port_required')
    with transport as client:
        if settings.smtp_port == 587:
            client.ehlo(); client.starttls(context=ssl.create_default_context()); client.ehlo()
        client.login(settings.gmail_user, ''.join(settings.gmail_app_password.get_secret_value().split()))
        refused = client.send_message(reply)
        if refused: raise ValueError('smtp_recipient_refused')


def notify(conn, key, original, result, folder):
    if result.get('status') in ('claimed', 'processing'): return None
    reply = build_reply(original, result, folder)
    if reply is None: return None
    cursor = conn.execute('INSERT OR IGNORE INTO replies(key,status,message_id,recipient) VALUES(?,?,?,?)',
                          (key, 'sending', str(reply['Message-ID']), json.dumps({field: str(reply.get(field, '')) for field in ('To', 'Cc', 'Bcc')})))
    conn.commit()
    if not cursor.rowcount: return None
    try:
        send(reply)
    except Exception as exc:
        # SMTP may already have accepted DATA. Do not replay an uncertain delivery.
        conn.execute('UPDATE replies SET status=?,error_type=? WHERE key=?', ('requires_review', type(exc).__name__, key))
        conn.commit()
        return 'requires_review'
    conn.execute("UPDATE replies SET status='sent',sent_at=CURRENT_TIMESTAMP WHERE key=?", (key,))
    conn.commit()
    return 'sent'
