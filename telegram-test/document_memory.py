"""Reuse reviewed transcriptions only for exact document bytes, with audit actor."""
import hashlib
import learning_memory


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode(path, reader):
    digest = fingerprint(path)
    issuer=None
    review_reason=None
    for rule in learning_memory.approved_rules():
        if rule['kind'] == 'interpretation' and rule['rule_key'] == 'document_sha256_' + digest:
            issuer=rule['payload'].get('issuer_name')
            if rule['payload'].get('requires_review'):review_reason=rule['payload'].get('review_reason','Lecture à préciser')
            text = rule['payload'].get('transcription', '').strip()
            if text:
                if review_reason:text+='\nLECTURE INCERTAINE A CONFIRMER : '+review_reason
                return {'ok': True, 'text': text, 'truncated': False,
                        'uncertain': bool(review_reason), 'requires_review':bool(review_reason), 'method': 'verified_exact_document', 'sha256': digest}
    result = reader(path)
    text = '\n\n'.join(p['text'] for p in result['pages']).strip()
    if not text:
        return {'ok': False, 'text': 'Photo conservée, écriture non lisible automatiquement : articles et quantités à préciser.', 'sha256': digest}
    if issuer and not text.startswith('Client : '+issuer+'\n'):text='Client : '+issuer+'\n'+text
    if review_reason:text+='\nLECTURE INCERTAINE A CONFIRMER : '+review_reason
    return {'ok': True, 'text': text[:18000], 'truncated': len(text) > 18000,
            'uncertain': bool(review_reason) or any(p['uncertain'] for p in result['pages']), 'sha256': digest,
            'methods':[p.get('method','unknown') for p in result['pages']],
            'vision_errors':[p['vision_error'] for p in result['pages'] if p.get('vision_error')],
            'requires_review':'LECTURE INCERTAINE A CONFIRMER' in text}
