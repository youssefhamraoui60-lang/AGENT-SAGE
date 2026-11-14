"""Coverage and explicit remaining blockers; no Sage writes."""
import collections
import csv
import json
from pathlib import Path
import sys
import hashlib
sys.path.insert(0,str(Path(__file__).parent))
from evaluate_week import sql_day,quantities

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/sob-week-20261102'
messages=json.loads((OUT/'messages-decoded.json').read_text(encoding='utf-8'))
result_file=OUT/('evaluation-final.json' if (OUT/'evaluation-final.json').exists() else 'evaluation-corrected.json')
results=json.loads(result_file.read_text(encoding='utf-8'))
orders=collections.defaultdict(list)
for row in json.loads((OUT/'ob-orders.json').read_text(encoding='utf-8'))['rows']:orders[row['SOHNUM_0']].append(row)
covered=[i for r in results for i in r['message_ids']]
assert sorted(covered)==sorted(r['id'] for r in messages),'Replay incomplet ou messages dupliqués'
matches=0
ready=0
missing=collections.Counter()
export=[]
for item in results:
    d=item.get('details',{})
    client=(d.get('client') or {}).get('BPCNUM_0','').strip()
    rep=(d.get('representative') or {}).get('REPNUM_0','').strip()
    actual=quantities(d.get('lines',[]),'article','quantity')
    candidates=[]
    for number,lines in orders.items():
        if client==lines[0]['BPCORD_0'].strip() and sql_day(lines[0]['ORDDAT_0'])==item['source_date'][:10] and actual and actual==quantities(lines,'ITMREF_0','QTY_0'):
            candidates.append(number)
    exact=len(candidates)==1 and rep==orders[candidates[0]][0]['REP_0'].strip()
    matches+=exact
    complete=d.get('intent')=='order' and not d.get('missing',['unknown'])
    ready+=complete
    missing.update(d.get('missing_fields',[]))
    export.append({'message_ids':','.join(map(str,item['message_ids'])),'date':item['source_date'],'intent':d.get('intent'),'client':client,'representative':rep,'ob_structure_and_rep_match':exact,'ob_candidates':','.join(candidates),'missing':'; '.join(d.get('missing_fields',[])),'error':item.get('error',''),'attachment_uncertain':item.get('attachment_uncertain',False)})
target=ROOT/'TEST/RESULTATS-SEMAINE-SOB-2026-11-02-07.csv'
with target.open('w',encoding='utf-8-sig',newline='') as file:
    writer=csv.DictWriter(file,fieldnames=export[0]);writer.writeheader();writer.writerows(export)
summary={'messages':len(messages),'cases':len(results),'attachments_with_text':sum(bool(r.get('attachment_text')) for r in messages),'ob_orders':len(orders),'complete_ob_reference_drafts':ready,'unique_client_rep_article_quantity_matches':matches,'errors':sum(not r['ok'] for r in results),'active_rules':None,'blockers':missing.most_common(),'sage_production_writes':0}
import learning_memory
summary['active_rules']=len(learning_memory.approved_rules())
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
manifest={'period_start':'2026-11-02','period_end_inclusive':'2026-11-07','evaluation_file':result_file.name,
          'hash_scope':'installed_sources_at_report_generation','extraction_replayed':True,'ob_writes':0,'hashes':{name:hashlib.sha256((ROOT/'telegram-test'/name).read_bytes()).hexdigest()
          for name in ('prepare.py','understanding.py','creation.py','sob-create.sql','sob-read.ps1','learning_memory.py','evaluate_week.py')}}
(OUT/'release-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
report=f'''# Évaluation SOB du 2 au 7 novembre 2026

{len(messages)} messages couverts exactement une fois, 109 pièces jointes analysées dont {summary['attachments_with_text']} avec texte exploitable, {len(results)} lots provisoires. Un fichier a échoué à la lecture, d'autres ont donné un texte vide. Les lots à 30 secondes ne sont pas un découpage métier validé : certains compléments tardifs ou clients différents demandent encore une reprise. Références OB : {len(orders)} commandes, lecture seule.

Sur les mêmes extractions DeepSeek rejouées après corrections : {matches} correspondances uniques client + commercial + articles/quantités ; {ready} brouillons sans champ manquant avec les références OB ; {summary['errors']} erreurs techniques. Ces nombres ne prouvent ni la création dans TEST de tous ces cas ni la compréhension de toutes les commandes.

Les prix de référence proviennent du même historique OB déjà créé. Ils ne constituent pas une évaluation indépendante de prédiction des prix. Les documents OCR peuvent contenir des erreurs. Une correspondance de structure n'est pas une validation des prix, de la TVA, des unités commerciales ou des règles métier Sage natives.

## Corrections et mémoire

{summary['active_rules']} règles actives dans PostgreSQL agent_sage / sage_ai : alias, interprétation des contacts/commerciaux, règles de prix/date, absence de liste arbitraire de deux clients, diamètres de fer, distinction des unités, absence de double transport et prix décimal commun au fer. Historique des révisions conservé. Les {len(results)} lots sont enregistrés dans sob_learning_examples avec statut needs_review ; les rapprochements automatiques OB ne sont pas approuvés comme vérité d'apprentissage. Il s'agit de mémoire consultée par le module, pas d'un entraînement des poids DeepSeek.

## Créations réelles dans TEST

- 2026ARC14613 : EDDAHRAOUI YOUSSEF, ciment + MANTD.
- 2026ARC14614 : TAIK CONSTRUCTION, deux ciments + MANTD, prix historiques TEST.
- 2026ARC14615 : HAIT RACHID, deux diamètres de fer, prix historiques TEST.
- 2026ARC14616 : **test en échec fonctionnel**, prix isolé 9.20 ignoré avant correction ; prix fer à zéro. Ne pas utiliser pour livraison/facturation. Aucun effacement ni modification automatique de cette commande.
- 2026ARC14617 : MMY IMMOBILIER, cinq diamètres de fer à 9.20 TTC + MANTD 300, retest corrigé du précédent.

Reçus idempotents conservés dans runtime/sob-orders.sqlite3 et runtime/sob-week-20261102/test-*-receipt*.json. Aucune commande historique n'a été recréée dans OB.

## Travail restant

Les cas non rapprochés restent ouverts : clients absents de TEST, homonymes/phonétique, certains articles sans site TEST, unités et conditionnements, tableaux OCR, prix HT/TTC, compléments tardifs et regroupements multi-commandes. Le lecteur Telegram actuel traite les messages texte ; l'ingestion automatique des pièces jointes et la modification d'une commande déjà créée après un PLUS tardif restent à implémenter. Les facteurs de conditionnement observés ne sont pas autorisés aveuglément pour les créations live.

Principaux champs manquants :

'''+''.join(f'- {name} : {count}\n' for name,count in missing.most_common(25))+'''
Le détail de chaque lot est dans RESULTATS-SEMAINE-SOB-2026-11-02-07.csv et runtime/sob-week-20261102/evaluation-final.json. L'agent n'est pas encore validé pour créer toutes les formes de commande de cette semaine sans intervention.

Validation locale : 51 tests SOB passent. Le service interne a été rechargé ; DeepSeek configuré et droits de création TEST disponibles. Les empreintes des sources livrées figurent dans runtime/sob-week-20261102/release-manifest.json. Aucun changement au moteur articles/fournisseurs.
'''
(ROOT/'TEST/RAPPORT-SEMAINE-SOB-2026-11-02-07.md').write_text(report,encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
