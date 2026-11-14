"""Preserve the full 477-message remainder as drafts, with no Sage execution."""
import json
from import_history import ROOT,OUT,dump
import drafts
import learning_memory
from psycopg.types.json import Jsonb

def main():
    linkage=json.loads((OUT/'import-linkage.json').read_text(encoding='utf-8'))
    receipts={r['ob_number']:r for r in json.loads((OUT/'historical-creation-results.json').read_text(encoding='utf-8'))}
    retests={r['ob_number']:r for r in json.loads((OUT/'retest-34-drafts.json').read_text(encoding='utf-8'))}
    cases={tuple(r['message_ids']):r for r in json.loads((OUT/'evaluation-final.json').read_text(encoding='utf-8'))}
    messages={r['id']:r for r in json.loads((OUT/'messages-visual.json').read_text(encoding='utf-8'))}
    results=[]
    with learning_memory.db.connection() as conn:
        for item in linkage['outcomes']:
            numbers=item.get('ob_numbers') or ([item['ob_number']] if item.get('ob_number') else [])
            if numbers and all(receipts.get(n,{}).get('status')=='created' for n in numbers):continue
            ids=item['message_ids'];case=cases[tuple(item.get('parent_message_ids',ids))];retest=retests.get(item.get('ob_number'))
            history=[{'role':'user','content':messages[i]['text']+'\n'+messages[i].get('layout_text','')} for i in ids]
            record={'message_ids':ids,'ob_number':item.get('ob_number'),'draft':retest['draft'] if retest else case.get('extracted'),
                    'documents':[messages[i].get('file') for i in ids if messages[i].get('file')],
                    'issues':retest['issues'] if retest else case.get('details',{}).get('missing_fields',[]),
                    'proposals':retest.get('proposals',[]) if retest else ['Vérifier le client et les lignes sur les messages/documents avant de valider un récapitulatif.'],
                    'status':'prepared_for_manual_review','human_validation_required':True,'sage_writes':0}
            owner='remainder-human-'+','.join(map(str,ids))
            drafts.save(owner,record,history)
            conn.execute('''INSERT INTO sob_learning_examples(source_key,input_data,expected,observed,status) VALUES(%s,%s,%s,%s,%s)
                ON CONFLICT(source_key) DO UPDATE SET observed=EXCLUDED.observed,status=EXCLUDED.status''',
                (owner,Jsonb(history),Jsonb({'OB':item.get('ob_number')}),Jsonb(record),'prepared_for_manual_review'))
            results.append(record)
    dump(ROOT/'TEST/SOB-477-BROUILLONS-A-VERIFIER.json',results)
    print(json.dumps({'drafts':len(results),'messages':sum(len(r['message_ids']) for r in results),'sage_writes':0}))

if __name__=='__main__':main()
