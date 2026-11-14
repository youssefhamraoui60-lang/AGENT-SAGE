"""Human review queue: every remaining source message, with its timestamp."""
import collections
import csv
from datetime import datetime
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/sob-week-20261102'

def main():
    with (ROOT/'TEST/SOB-COMMANDES-SANS-CREATION.csv').open(encoding='utf-8-sig',newline='') as stream:
        remaining=list(csv.DictReader(stream,delimiter=';'))
    parts={str(r['message_id']):r for r in json.loads((OUT/'repair-text-parts.json').read_text(encoding='utf-8'))}
    source={str(r['id']):r for r in json.loads((OUT/'messages-visual.json').read_text(encoding='utf-8'))}
    rows=[]
    for row in remaining:
        item=source[row['message_id']]
        analysis=parts.get(row['message_id'],{})
        reason=row['raison_sans_creation']
        if item.get('file'):
            category='Document : lecture et identité/lignes à vérifier'
        elif 'conditionnement' in reason or 'Conversion' in reason or 'Quantité' in reason:
            category='Quantité ou unité à préciser'
        elif reason.startswith('Client'):
            category='Identité client à vérifier'
        elif reason.startswith('Article'):
            category='Référence article à vérifier'
        else:
            category='Commande ou complément à rattacher'
        row.update(type_verification=category,
                   analyse_IA='ÉCHEC SERVICE IA, à reprendre' if analysis.get('reason')=='RequestError' else 'Analyse disponible' if analysis else 'Revue du lot/document',
                   extrait_document=item.get('layout_text',item.get('attachment_text','')),
                   lecture_visuelle=item.get('visual_review_20261109',{}).get('transcription',''),
                   points_a_confirmer=' ; '.join(item.get('visual_review_20261109',{}).get('issues',[])),
                   correction_utilisateur='')
        rows.append(row)
    target=ROOT/'TEST/SOB-MESSAGES-A-VERIFIER-DETAIL.csv'
    with target.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter=';')
        writer.writeheader();writer.writerows(rows)
    summary={'messages':len(rows),'categories':dict(collections.Counter(r['type_verification'] for r in rows)),
             'provider_failed_messages':sum(r['analyse_IA'].startswith('ÉCHEC') for r in rows)}
    (OUT/'remaining-triage-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
