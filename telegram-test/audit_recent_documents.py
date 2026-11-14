"""Read-only review of the already exported recent Telegram documents."""
import csv
import json
import re
from pathlib import Path
from document_memory import decode
from read_documents_layout import read
from creation import run_script

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/sob-review-20261110'


def main():
    messages=json.loads((OUT/'all-recent-test-messages.json').read_text(encoding='utf-8'))
    results=[]
    for message in messages:
        if not message['media']:
            continue
        mid=message['id']
        folder=ROOT/'runtime/telegram-test/documents/-5586539927'/str(mid)
        paths=[p for p in folder.glob('*') if p.suffix.lower() in ('.jpg','.pdf','.png')]
        replies=[r['text'] for r in messages if r.get('reply_to')==mid and r['text'].startswith('🤖 SOB')]
        reply=' / '.join(replies)
        result={'message_id':mid,'date':message['date'],'document':message.get('file_name') or 'image',
                'reply':reply,'order':'','client':'','zero_price_lines':'','reading_status':'not_checked',
                'financial_status':'not_verified'}
        if paths:
            try:
                doc=decode(paths[0],read)
                (OUT/f'audit-document-{mid}.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
                result['reading_status']='verified_exact_transcription' if doc.get('method')=='verified_exact_document' else 'ocr_or_pdf_text_requires_review'
                if not doc.get('ok'):result['reading_status']='unreadable'
            except Exception as exc:
                result['reading_status']='read_error_'+type(exc).__name__
        else:
            result['reading_status']='local_file_missing'
        number=re.search(r'\b2026ARC\d+\b',reply)
        if number:
            result['order']=number[0]
            data=run_script('sob-read.ps1',{'kind':'order_lines','code':number[0]})
            if data.get('ok') and data.get('rows'):
                result['client']=data['rows'][0]['BPCORD_0']
                result['zero_price_lines']=';'.join(r['ITMREF_0'] for r in data['rows'] if r['NETPRIATI_0']==0)
                result['financial_status']='existing_order_requires_document_comparison'
                (OUT/f'audit-order-{mid}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        if 'Bouchaib' in reply:
            result['financial_status']='creation_paused_by_user'
        if mid in (422,424):
            result['financial_status']='corrected_sql_preview_no_creation'
        results.append(result)
        print(mid,result['reading_status'],result['financial_status'],flush=True)
    target=ROOT/'TEST/SOB-VERIFICATION-DOCUMENTS-RECENTS.csv'
    with target.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(results[0]),delimiter=';')
        writer.writeheader();writer.writerows(results)
    (OUT/'all-documents-audit.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Reviewed',len(results),'documents; no Sage writes or Telegram sends')


if __name__=='__main__':main()
