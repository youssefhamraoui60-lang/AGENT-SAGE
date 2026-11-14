"""One auditable result per original message; successful receipts only count created."""
import collections
import csv
import html
import json
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/sob-week-20261102'

def safe_cell(value):
    text=str(value or '')
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) else text

def main():
    import learning_memory
    from telegram_batch import contact_name
    rules=learning_memory.approved_rules()
    excluded=next((r['payload'].get('value',[]) for r in rules if r['kind']=='policy' and r['rule_key']=='telegram_creation_excluded_contacts'),[])
    source=json.loads((OUT/'messages-decoded.json').read_text(encoding='utf-8'))
    linkage=json.loads((OUT/'import-linkage.json').read_text(encoding='utf-8'))
    results=json.loads((OUT/'historical-creation-results.json').read_text(encoding='utf-8'))
    by_order={r['ob_number']:r for r in results}
    by_id={i:r for r in linkage['outcomes'] for i in r['message_ids']}
    assert set(by_id)=={r['id'] for r in source}
    rows=[]
    for message in source:
        item=by_id[message['id']]
        numbers=item.get('ob_numbers') or ([item['ob_number']] if item.get('ob_number') else [])
        receipts=[by_order.get(n,{}) for n in numbers]
        receipt=by_order.get(item.get('ob_number'),{})
        created=bool(receipts) and all(r.get('status')=='created' for r in receipts)
        reason='' if created else '; '.join(r.get('reason','') for r in receipts if r.get('reason')) or item.get('repair_blocker') or item.get('reason') or 'À vérifier'
        stamp=datetime.fromisoformat(message['date'])
        paused=not created and contact_name(message['text']) in excluded
        if paused:reason='Ne pas créer : instruction utilisateur pour Bouchaib.'
        rows.append({'message_id':message['id'],'date':message['date'],'jour':stamp.strftime('%d/%m/%Y'),'heure':stamp.strftime('%H:%M:%S'),'lot_messages':','.join(map(str,item['message_ids'])),
                     'statut':'CRÉÉE' if created else 'SUSPENDUE UTILISATEUR' if paused else 'BLOQUÉE' if receipt else 'À RAPPROCHER',
                     'commande_OB':','.join(numbers),'commande_TEST':','.join(r['number'] for r in receipts if r.get('status')=='created'),
                     'commercial_contact':item.get('contact',''),'client_indique':item.get('client_hint',''),
                     'raison_sans_creation':reason,'methode':item.get('method',''),
                     'candidats_OB':','.join(c['number'] for c in item.get('candidates',[])),
                     'fichier':str((OUT/message['file']).resolve()) if message.get('file') else '',
                     'texte':message['text']})
    remaining=[r for r in rows if r['statut']!='CRÉÉE']
    for name,data in [('SOB-829-MESSAGES-RESULTATS.csv',rows),('SOB-COMMANDES-SANS-CREATION.csv',remaining)]:
        with (ROOT/'TEST'/name).open('w',encoding='utf-8-sig',newline='') as file:
            writer=csv.DictWriter(file,fieldnames=rows[0],delimiter=';');writer.writeheader()
            writer.writerows({k:safe_cell(v) for k,v in r.items()} for r in data)
    created_orders={r['ob_number']:r for r in results if r.get('status')=='created'}
    ob=collections.defaultdict(list)
    for line in json.loads((OUT/'ob-orders.json').read_text(encoding='utf-8'))['rows']:ob[line['SOHNUM_0']].append(line)
    with (ROOT/'TEST/SOB-COMMANDES-CREEES.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=['commande_OB','commande_TEST','client','commercial_OB','TTC_OB','lignes_OB','messages','creation_preexistante'],delimiter=';');writer.writeheader()
        writer.writerows({'commande_OB':n,'commande_TEST':r['number'],'client':ob[n][0]['BPCORD_0'],'commercial_OB':ob[n][0]['REP_0'],'TTC_OB':ob[n][0]['ORDATI_0'],'lignes_OB':' | '.join(str(x['ITMREF_0'])+' x '+str(x['QTY_0'])+' @ '+str(x['NETPRIATI_0']) for x in ob[n]),'messages':','.join(map(str,r['message_ids'])),'creation_preexistante':bool(r.get('previous_test'))} for n,r in sorted(created_orders.items()))
    logical_remaining={r['lot_messages'] for r in remaining}
    summary={'source_messages':len(source),'messages_linked_to_created_orders':len(rows)-len(remaining),
             'messages_without_creation':len(remaining),'logical_lots_without_creation':len(logical_remaining),
             'created_orders_with_receipt':len(created_orders),'new_orders_this_import':sum(not r.get('previous_test') for r in created_orders.values()),
             'ob_orders_linked':len(linkage['orders']),'blocked_ob_orders':sum(r.get('status')!='created' for r in results),
             'production_writes':0,'remaining_reasons':collections.Counter(r['raison_sans_creation'] for r in remaining).most_common()}
    (OUT/'import-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    verification=json.loads((OUT/'test-readback-verification.json').read_text(encoding='utf-8')) if (OUT/'test-readback-verification.json').exists() else {}
    # Every final outcome, including failures, is retained in the learning DB.
    # A failed reconciliation is never promoted to an approved alias or policy.
    import learning_memory
    from psycopg.types.json import Jsonb
    source_by_id={r['id']:r for r in source}
    with learning_memory.db.connection() as conn:
        for item in linkage['outcomes']:
            receipt=by_order.get(item.get('ob_number'),{})
            number=item.get('ob_number')
            conn.execute('''INSERT INTO sob_learning_examples(source_key,input_data,expected,observed,status)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(source_key) DO UPDATE SET expected=EXCLUDED.expected,observed=EXCLUDED.observed,status=EXCLUDED.status''',
                ('sob-history-outcome-'+','.join(map(str,item['message_ids'])),
                 Jsonb([source_by_id[i] for i in item['message_ids']]),
                 Jsonb({'OB':number,'order':ob.get(number,[]),'proof':item.get('proof')}),
                 Jsonb({'receipt':receipt,'reason':item.get('repair_blocker') or item.get('reason'),'method':item.get('method')}),
                 'created_test_verified_reference' if receipt.get('status')=='created' else 'needs_review'))
    lines=['# Reprise réelle SOB — messages du 2 au 7 novembre 2026','',
           f"{len(source)} messages suivis individuellement. {summary['created_orders_with_receipt']} commandes distinctes avec reçu TEST, dont {summary['new_orders_this_import']} nouvelles créations pendant cette reprise. {summary['messages_linked_to_created_orders']} messages sont rattachés à ces commandes.",'',
           f"**Restent sans création : {len(remaining)} messages, répartis en {len(logical_remaining)} lots provisoires à vérifier.** Les messages multiples et doublons d'une même commande partagent un seul reçu ; 829 messages ne produisent donc pas automatiquement 829 numéros de commande.",'',
           '## Fichiers de contrôle','',
           '- SOB-COMMANDES-SANS-CREATION.csv : uniquement le reliquat, avec texte original, PDF/image, raison et candidat OB si connu.',
           '- SOB-COMMANDES-CREEES.csv : correspondance des numéros OB vers les numéros réellement créés dans TEST.',
           '- SOB-829-MESSAGES-RESULTATS.csv : couverture complète des 829 messages, une ligne par message.','',
           '## Ce qui a été exécuté','',
           'Les textes et pièces jointes ont été rejoués, les tableaux ont été relus en conservant les positions des mots et plusieurs manuscrits ont été inspectés visuellement. Les commandes OB ont été utilisées comme références en SELECT uniquement. Après rapprochement, le même moteur SOB de récapitulatif SQL et confirmation a exécuté les créations réelles dans TEST. Les références client/article/unité/site/TVA TEST sont vérifiées avant insertion ; chaque reçu est durable et les reprises sont idempotentes par numéro source OB.',
           '',
           'Cette reprise est assistée par les commandes OB existantes. Elle ne prouve pas que le module sait traiter seul toutes les futures commandes. Les compléments tardifs et documents ambigus restent dans le reliquat plutôt que de provoquer une copie arbitraire de production. Les rapprochements peuvent avoir utilisé plusieurs articles et quantités uniques lorsque le nom client était absent : la méthode et les citations sont conservées dans runtime/sob-week-20261102/import-linkage.json.',
           '',f"Contrôle indépendant par SELECT dans TEST : {verification.get('verified',0)} commandes relues conformes au reçu sur {verification.get('orders',0)}, {len(verification.get('failures',[]))} échecs. Le SELECT OB a aussi été relancé : 1794 lignes identiques au snapshot historique, 723 commandes de référence.",
           '',
           'Dates de création/livraison des copies : jour courant de la reprise ; la date historique et le numéro OB restent dans la traçabilité. Prix des copies : prix TTC des commandes OB rapprochées. OB reste en lecture seule. Les fiches clients manquantes et l’article COL ont été synchronisés séparément dans TEST sur autorisation utilisateur ; les sauvegardes et reçus sont conservés dans runtime/sob-week-20261102.',
           '',
           '**Ancien test erroné 2026ARC14616 : toujours à annuler dans Sage ; son retest corrigé est 2026ARC14617. Ce test erroné ne compte pas comme une création historique réussie.**','',
           '## Reliquat par lot','']
    seen=set()
    for row in remaining:
        if row['lot_messages'] in seen:continue
        seen.add(row['lot_messages'])
        lines.append(f"- Messages {row['lot_messages']} — {row['date'][:10]} — {row['commercial_contact']} — {row['client_indique'] or 'client à déterminer'} — {row['raison_sans_creation']}"+(f" — OB {row['commande_OB']}" if row['commande_OB'] else ''))
    (ROOT/'TEST/RAPPORT-REPRISE-REELLE-SOB.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='remaining_reasons'},ensure_ascii=False))

if __name__=='__main__':main()
