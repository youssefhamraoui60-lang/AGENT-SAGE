"""Aggregate executed evidence, keeping simulated and real results separate."""
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tests/ai-evaluation'


def main():
    reports=BASE/'reports';reports.mkdir(exist_ok=True)
    runs=[];failures=[]
    for file in sorted(BASE.glob('*.xml')):
        root=ET.parse(file).getroot();suites=list(root.iter('testsuite'))
        runs.append({'file':file.name,**{k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','errors','failures','skipped')}})
        for case in root.iter('testcase'):
            failure=case.find('failure')
            if failure is None:failure=case.find('error')
            if failure is not None:failures.append({'run':file.name,'id':case.get('name'),'message':failure.get('message'),'details':failure.text})
    conversations=[]
    for file in sorted((BASE/'conversations').glob('*/run_manifest.json')):
        manifest=json.loads(file.read_text(encoding='utf8'));turns=[]
        for item in manifest.get('conversations',[]):
            record=json.loads((file.parent/(item['id']+'.json')).read_text(encoding='utf8'))
            turns.extend(record.get('results',[]))
        conversations.append({'directory':str(file.parent.relative_to(BASE)),
            'status':manifest.get('status','completed' if manifest.get('finished_at') else 'running'),
            'finished':bool(manifest.get('finished_at')),'conversations':len(manifest.get('conversations',[])),
            'passed':sum(c['passed'] for c in manifest.get('conversations',[])),
            'turns':len(turns),'failed_turns':sum(t['status']!='passed' for t in turns),
            'real_model_calls':sum(bool((t.get('provenance') or {}).get('real_model_called')) for t in turns),
            'model':manifest.get('model'),'model_digest':manifest.get('model_digest'),
            'ERP_writes':manifest.get('real_ERP_writes'),'human_review_performed':False})
    source_changes=[]
    progress=json.loads((BASE/'progress.json').read_text(encoding='utf8'))
    baseline=json.loads((Path(progress['backup'])/'manifest.json').read_text(encoding='utf8'))['files']
    for part in ('backend/app','backend/tests','frontend/src','frontend/tests','scripts'):
        for path in (ROOT/part).rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts:continue
            name=path.relative_to(ROOT).as_posix();sha=hashlib.sha256(path.read_bytes()).hexdigest()
            if baseline.get(name)!=sha:source_changes.append({'path':name,'sha256':sha,'status':'modified' if name in baseline else 'new'})
    consolidated=json.loads((BASE/'run_manifest.json').read_text(encoding='utf8')) if (BASE/'run_manifest.json').exists() else None
    summary={'at':datetime.now(timezone.utc).isoformat(),'goal_complete':False,'runs':runs,
             'consolidated':consolidated,
             'conversation_cycles':conversations,'source_changes':source_changes,
             'real_creations':0,'real20_approval':'changes_requested_not_approved',
             'open':['human review of language quality pending',
                     'SQL reader table INSERT/UPDATE privileges require separate approval',
                     'customer publication not observed','write connector changes require separate approval',
                     'existing article-site readback mismatch reproduced; connector correction not approved/applied',
                     'real20 exact data changes requested by user']}
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    (reports/('summary-'+stamp+'.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    faildir=BASE/'failures';faildir.mkdir(exist_ok=True)
    (faildir/('historical-'+stamp+'.json')).write_text(json.dumps(failures,ensure_ascii=False,indent=2),encoding='utf8')
    lines=['# Fiabilisation Agent Sage X3 — rapport de progression vérifié','',
           'Mission incomplète. Les résultats ci-dessous proviennent de fichiers effectivement produits par les exécutions.',
           '', '## Architecture actuelle','',
           'React → API FastAPI (travail asynchrone et statut) → demande originale PostgreSQL → extraction locale ou Qwen → checkpoint des brouillons → outils SELECT prédéfinis → validation et dépendances → réponse. Les fiches fournisseurs/clients sont des brouillons distincts ; aucun nouveau service d’écriture n’est activé.',
           '', 'Les expériences sont enregistrées uniquement lors de la relecture explicite d’un brouillon. La récupération combine mots et similarité de caractères, reste isolée par propriétaire et ne constitue aucun entraînement.',
           '', '## Résultats exécutés','', '| Rapport | Tests | Échecs | Erreurs | Ignorés |','|---|---:|---:|---:|---:|']
    for r in runs:lines.append(f'| {r["file"]} | {r["tests"]} | {r["failures"]} | {r["errors"]} | {r["skipped"]} |')
    lines+=['','Les cycles se recouvrent : ne pas additionner leurs nombres pour prétendre à autant de scénarios distincts. La campagne dédiée contient 1 000 cas paramétrés dans 11 domaines ; elle ne mesure pas à elle seule la compréhension libre de Qwen.',
            '', '## Conversations simulées','', '| Cycle | État | Terminées | Réussies | Tours | Échecs de tours | Appels réels Qwen |','|---|---|---:|---:|---:|---:|---:|']
    for r in conversations:lines.append(f'| {r["directory"]} | {r["status"]} | {r["conversations"]} | {r["passed"]} | {r["turns"]} | {r["failed_turns"]} | {r["real_model_calls"]} |')
    lines+=['','Les utilisateurs sont simulés. SQL et SOAP sont simulés dans ces conversations ; PostgreSQL et les appels Qwen identifiés par leur provenance sont réels. Une revue humaine de la pertinence des réponses reste nécessaire.',
            '', '## Corrections et vérifications','',
            '- Corrections explicites conservées en présence de questions ; catégories et unités de destination correctement distinguées des anciennes valeurs.',
            '- Absence et facultativité du fournisseur distinguées ; cibles d’articles et de tiers séparées.',
            '- Conventions de codes locales à la conversation ou à une sélection ; contrôles de longueur et de disponibilité conservés.',
            '- Historique des valeurs et exemples relus, sans apprentissage automatique de règles métier.',
            '- Désignations contenant CONTROLE traitées comme données plutôt que commandes.',
            '- Catalogue de catégories lu dans TEST avec codes et intitulés, sans l’ancienne limite de 21 lignes ; les indisponibilités restent explicites.',
            '- Demande AHMNDE multi-opérations reproduite ; champs juridiques, brouillons dépendants et reprise après interruption vérifiés. Voir RAPPORT-TIMEOUT-MULTI-OPERATIONS.md.',
            '- Tests de doublons, approbations, réémissions et résultats article-site ambigus exercés en simulation.',
            '', '## Sécurité et recette réelle','',
            'Aucun SAVE réel dans ces travaux. Les lectures TEST ont confirmé l’absence des 20 codes proposés et leurs couples article-site. Les données restent non approuvées : l’utilisateur demande des corrections.',
            '', 'Le lecteur SQL possède INSERT/UPDATE sur TEST.ITMMASTER, TEST.ITMFACILIT, TEST.BPSUPPLIER et TEST.BPCUSTOMER. Aucun de ces droits n’a été utilisé ni modifié. Leur correction exige une décision séparée.',
            '', 'La politique d’écriture, les certificats, la révocation et les privilèges restent inchangés. Le connecteur article-site est toujours borné à EXT_POUDRE. Le rapport RAPPORT-20-CREATIONS-REELLES.md contient les propositions et les blocages.',
            '', '**Défaut sensible reproduit et non corrigé :** le retour ALREADY_EXISTS du connecteur article-site peut confirmer la relecture sans comparer les champs attendus. La simulation UN attendu / M2 existant retourne ReadConfirmed=true. Preuve : failures/existing-site-mismatch-simulation.json. Le patch proposé dans reports/PROPOSITION-ARTICLE-SITE-READBACK.patch reste non appliqué, en attente d’une approbation distincte.',
            '', '## Fichiers applicatifs et tests modifiés ou ajoutés','']
    if consolidated:
        c=consolidated['conversations']
        lines.insert(lines.index('## Corrections et vérifications'),f"Consolidation des mêmes entrées et attentes : {c['distinct']} conversations distinctes, {c['initial_passed']} réussies au premier cycle complet, {c['final_passed']} réussies après les rejeux identifiés. Le premier échec de délai reste conservé.\n")
    lines+=['- `'+r['path']+'` — '+r['status'] for r in source_changes]
    lines+=['','## Travail restant','']+['- '+x for x in summary['open']]
    lines+=['','Les parcours d’écriture fournisseurs/clients et la recette réelle ne sont pas déclarés opérationnels. Les limitations restantes ne sont pas compensées par des succès de simulation.','']
    (reports/'RAPPORT-FIABILISATION.md').write_text('\n'.join(lines),encoding='utf8')
    print(json.dumps({'report':str(reports/'RAPPORT-FIABILISATION.md'),'cycles':len(runs),'conversation_cycles':conversations},ensure_ascii=False))


if __name__=='__main__':main()
