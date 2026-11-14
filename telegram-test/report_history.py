"""Build the reviewable audit report from completed, read-only checkpoints."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/sob-audit'
REPORT=ROOT/'TEST/RAPPORT-EVALUATION-COMMANDES-SOB-2026-11-08.md'


def load(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))


def main():
    source=load('messages-200.json')
    selected=load('messages-selected.json')
    before=load('evaluation-baseline.json')
    after=load('evaluation-release.json')
    assert len(after)==52 and sorted(i for r in after for i in r['message_ids'])==sorted(r['id'] for r in selected)
    scored=[r for r in after if r['ob_orders']]
    matched=[r for r in scored if r.get('complete_match')]
    before_matched=sum(bool(r.get('complete_match')) for r in before)
    kinds=Counter(r['kind'] for r in after)
    known_customers=load('test_customers.json')['rows']
    known_articles=load('test_articles.json')['rows']
    missing_customers=[r['BPCORD_0'] for r in known_customers if not r['IN_TEST']]
    no_site=[r['ITMREF_0'] for r in known_articles if not r['SITE_OK']]
    files=[r for r in selected if r.get('file')]
    unique_files={hashlib.sha256((OUT/r['file']).read_bytes()).hexdigest() for r in files}
    physical=sum(bool(r.get('current_test_creation_scope')) for r in after)
    table=[]
    with (ROOT/'TEST/RESULTATS-COMMANDES-SOB-2026-11-08.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream,delimiter=';')
        writer.writerow(['Messages','Type','Commandes OB','Client identique','Commercial identique','Articles/quantités identiques','Structure identique','Montants TTC identiques','Périmètre TEST actuel','Informations à préciser'])
        for r in after:
            details=r.get('details',{})
            writer.writerow([','.join(map(str,r['message_ids'])),r['kind'],','.join(r['ob_orders'] or []),
                             r.get('client_match'),r.get('rep_match'),r.get('lines_match'),r.get('complete_match'),
                             r.get('prices_totals_match'),r.get('current_test_creation_scope'),
                             ' / '.join(details.get('missing_fields',[])) or r.get('error','')])
            if r['ob_orders'] and not r.get('complete_match'):
                fields=' ; '.join(details.get('missing_fields',[])) or 'Écart entre le contenu demandé et la commande OB enrichie manuellement'
                table.append('| '+','.join(map(str,r['message_ids']))+' | '+r['kind']+' | '+fields+' |')
    report=f'''# Évaluation des commandes Telegram SOB — 8 novembre 2026

**Conclusion : la compréhension a progressé, mais l’agent ne peut pas encore créer automatiquement tous les types de commandes du groupe.**

## Périmètre réellement lu

- Groupe source : **sob commandes**, distinct du groupe de test « COMMANDES SOB ».
- **{len(source)} derniers messages exportés**, du {source[0]['date']} au {source[-1]['date']}.
- Période confirmée par l’utilisateur : **à partir du samedi 7 novembre 2026**.
- **{len(selected)} messages** de ces 200 appartiennent à cette période ; ils ont tous été inclus une seule fois dans les tests.
- **52 cas logiques** : 50 demandes et 2 relances/actions sur une commande existante.
- {len(files)} pièces jointes dans la période, dont {len(unique_files)} fichiers distincts ; lecture PDF texte et OCR Windows du lecteur déjà présent.
- Les 21 pièces jointes des 200 messages ont été examinées par le décodeur. Certains anciens scans et la photo manuscrite n’ont pas fourni un texte OCR exploitable.
- **71 commandes OB / 145 lignes lues** pour le 7 novembre : 43 cas rapprochés de commandes OB, 7 demandes sans rapprochement assez certain, 2 actions sans création.

## Résultats mesurés

| Contrôle | Premier passage | Après corrections et rejeu contrôlé |
|---|---:|---:|
| Cas évalués | 52 | 52 |
| Cas avec référence OB établie | 43 | 43 |
| Client + commercial + articles/quantités identiques | {before_matched}/43 | **{len(matched)}/43 ({len(matched)/43:.1%})** |
| Client identique | — | {sum(bool(r.get('client_match')) for r in scored)}/43 |
| Commercial identique | — | {sum(bool(r.get('rep_match')) for r in scored)}/43 |
| Articles et quantités identiques | — | {sum(bool(r.get('lines_match')) for r in scored)}/43 |
| Structure et montants TTC identiques | — | {sum(bool(r.get('structural_and_price_match')) for r in scored)}/43 |
| Relances/activations classées sans nouvelle création | — | {sum(bool(r.get('not_create_correct')) for r in after if r['ob_orders']==[])}/2 |
| Cas passant le filtre actuel de création TEST | — | **{physical}/52** |
| Commandes réellement créées par cette évaluation | **0** | **0** |

Le dernier chiffre de capacité TEST est distinct du taux de compréhension : le filtre de l’exécuteur reste limité aux clients C01401/C10370 et à ses articles déjà validés. Le cas FASM.IMO passe ce filtre. Ce rapport n’autorise ni de nouvelles écritures OB ni le rejeu réel des commandes historiques.

## Corrections apportées au module SOB

- Noms clients dans les deux ordres, ponctuation/accents et variantes proches ; homonymes départagés par commercial lorsqu’il est reconnu.
- Commercial reconnu par nom court et nom complet, sans inventer un code REP.
- Alias ciment/sima/cima, Perfecto, TRADICEM, fer/RAB, unités mêlées au nom d’article ; préférence pour la fiche de base plutôt que ses doublons fournisseurs.
- Conversion explicite tonnes → kg ; ciment CPJ35/45/35P en sacs de 50 kg pour les occurrences vérifiées ; conservation des unités inconnues sans conversion inventée.
- Conditionnements observés dans OB : palettes, voyages, fardeaux et barres. **Ils restent bloquants à vérifier en création TEST**, car un exemple historique ne suffit pas à garantir tous les conditionnements futurs.
- Lecture des abréviations « 18t45 », « 09t35 », et regroupement des informations complémentaires dans le cas de test.
- Date de référence du message pour les replays ; livraison du jour si absente.
- Prix explicite prioritaire, sinon historique client/article, sinon zéro TTC selon l’autorisation de l’utilisateur ; une panne SQL ne devient pas un prix zéro.
- Normalisation des réponses JSON pour éviter les échecs sur une question vide retournée par le modèle.

Les règles et le fournisseur IA existants des articles/fournisseurs n’ont pas été modifiés. Il n’y a eu aucun entraînement du modèle : ce sont des corrections de lecture, résolution de références et contrôles dans SOB.

## Blocages de données TEST

Comparaison des références des 71 commandes OB lues :

- {len(known_customers)} clients distincts ; **{len(missing_customers)} absents de TEST** : {', '.join(missing_customers)}.
- {len(known_articles)} articles distincts ; tous existent dans TEST, mais **{', '.join(no_site)}** n’y ont pas le rattachement attendu au site 201.
- TRADICEM/COL a aussi une unité différente entre les fiches lues dans OB et TEST (SAC / UN). Aucune unité ni fiche n’a été modifiée.
- Les clients/articles reconnus dans OB ne sont pas automatiquement utilisables par l’exécuteur TEST ; la simulation doit toujours relire les fiches cibles.

## Cas restant différents ou ambigus

| Messages source | Type | À résoudre |
|---|---|---|
'''+ '\n'.join(table)+'''

Ces différences ne sont pas toutes des erreurs du modèle : par exemple, la commande OB associée au message 4804 contient un transport de 300 MAD absent du message source. L’agent ne doit pas inventer ce supplément pour améliorer son score.

Autres limites concrètes :

- Les captions expéditeur/fournisseur, le nom de l’émetteur du PDF et le client acheteur ne sont pas toujours identiques. Un nom « OULD BOUAZZA » ne suffit pas à identifier le bon client.
- Plusieurs commandes sont regroupées manuellement dans un seul bon PDF, avec des lignes réparties sur plusieurs commandes OB.
- La photo manuscrite produit trop peu de texte OCR pour certifier les diamètres et les poids ; aucune création automatique n’est justifiée à partir de ce résultat.
- Le test emploie un regroupement chronologique revu manuellement. Le délai de 30 secondes du bot ne suffit pas aux ajouts « PLUS » arrivant 4 ou 24 minutes plus tard : il faut une gestion de modification de commande existante, pas une seconde création.
- Les pièces jointes ont été décodées dans le banc d’essai. Le flux Telegram de production actuel ne traite pas encore les pièces jointes de bout en bout : ce résultat ne prouve pas leur création automatique depuis le bot.

## Limites de la mesure

Il s’agit d’un rejeu des mêmes cas, pas d’un jeu de validation indépendant. Les numéros OB servent seulement à noter les résultats ; ils ne sont pas fournis au modèle pour lui dicter le client ou les lignes. Le dernier rejeu réutilise les extractions JSON du passage précédent afin de tester les corrections du résolveur sans nouveaux appels IA.

Les prix historiques sont relus dans l’état actuel d’OB, qui contient déjà les commandes cibles. L’accord sur les montants n’est donc **pas une preuve indépendante** de ce que l’agent aurait prédit avant leur création. Les montants n’ont pas été utilisés pour noter le rapprochement client/commercial/articles/quantités.

L’insertion SQL directe existante n’est pas une création X3 certifiée et ne reproduit pas tous les traitements métier X3. Aucune affirmation de livraison, allocation ou facturation correcte n’est faite ici.

## Vérifications et artefacts

- 37 tests de régression ciblés exécutés avec succès.
- Simulations SQL C10370/CPJ45/pointes/MANTD effectuées en mode preview avec ROLLBACK, sans commande réelle.
- Scripts de lecture OB : SELECT fixes uniquement ; aucune nouvelle attribution de droits.
- Aucun message envoyé au groupe source ; aucune activation, relance ou duplication des commandes OB.
- Détails consultables dans `TEST/RESULTATS-COMMANDES-SOB-2026-11-08.csv`.
- Données brutes et reçus de test privés : `runtime/sob-audit/`, déjà exclu de Git.
- Checkpoints : `evaluation-baseline.json`, `evaluation-final.json`, `evaluation-release.json` ; empreintes des sources dans `source-release.json`.

Rejeu sans création, sur cet export figé :

```powershell
backend/.venv/Scripts/python.exe telegram-test/evaluate_history.py controle final
backend/.venv/Scripts/python.exe telegram-test/report_history.py
```

Le manifeste couvre ces 73 messages précis ; un nouvel export doit être regroupé et rapproché à nouveau avant de réutiliser ces résultats.
'''
    REPORT.write_text(report,encoding='utf-8')
    summary={'messages_exported':len(source),'messages_in_period':len(selected),'cases':len(after),'matched_cases':len(matched),
             'scored_cases':len(scored),'current_creation_scope_cases':physical,'sage_writes':0}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':
    main()
