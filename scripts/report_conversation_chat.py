"""Summarize observed tests; never infer successful ERP writes from model/UI tests."""
import json,xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
log=ROOT/'logs'
evaluation=json.loads((log/'chat-real-evaluation.json').read_text(encoding='utf-8'))
browser=json.loads((log/'chat-browser-tests.json').read_text(encoding='utf-8')) if (log/'chat-browser-tests.json').exists() else {'status':'NOT_COMPLETED'}
runtime=json.loads((log/'chat-runtime-checks.json').read_text(encoding='utf-8')) if (log/'chat-runtime-checks.json').exists() else {'status':'NOT_COMPLETED'}
sqltools=json.loads((log/'chat-sql-tools-live.json').read_text(encoding='utf-8')) if (log/'chat-sql-tools-live.json').exists() else {'status':'NOT_COMPLETED'}
tests=ET.parse(log/'chat-regression.xml').getroot()
suites=list(tests.iter('testsuite'))
counts={k:sum(int(s.get(k,'0')) for s in suites) for k in ['tests','failures','errors','skipped']}
ref=evaluation.get('reference',{})
cases=evaluation.get('cases',[])
complete=ref.get('status')=='PASS' and browser.get('status')=='PASS' and runtime.get('status')=='PASS' and sqltools.get('status')=='PASS' and len(cases)==40 and all(c['status']=='PASS' for c in cases) and counts['failures']==counts['errors']==counts['skipped']==0
drafts=ref.get('drafts',[])
export={'kind':'REAL_QWEN_AND_SQL_CHECKED_DRAFTS_NOT_CREATED','conversation_id':ref.get('conversation_id'),'source':'user_reference_conversation',
        'articles':drafts,'sage_created':False,'verified_by_sage_write':False}
(log/'ETAPE-5-MODERN-FOAM-BROUILLONS.json').write_text(json.dumps(export,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# Étape 5 — agent conversationnel Sage X3', '',
       'Rapport du 24 octobre 2026 (Europe/Paris). Horodatages détaillés des preuves en UTC.',
       f"Compilation du rapport : {datetime.now(timezone.utc).isoformat()}.", '',
       f"Recette développement complète : **{'OUI' if complete else 'NON — voir les cas non validés ci-dessous'}**. Aucune création ERP annoncée ; les prérequis d’écriture Sage restent indépendants.", '',
       'Interface locale : http://127.0.0.1:8000/sage/. Chat unique, historique et cartes de brouillons. Session backend HttpOnly et CSRF automatiques ; aucun jeton opérateur à copier. Accès réseau fermé par défaut, aucun paramètre du serveur Sage changé.', '',
       '## Preuves exécutées', '',
       f"- Régression backend : {counts['tests']} tests, {counts['failures']} échec, {counts['errors']} erreur, {counts['skipped']} ignoré. Tests unitaires/intégration avec doubles contrôlés distincts des essais réels Qwen.",
       f"- Navigateur réel : {browser.get('status')}, Qwen réel={browser.get('real_qwen',False)}, SQL réel={browser.get('real_sql',False)} ; contrôles : {', '.join(browser.get('checks',[]))}.",
       f"- Santé des services et contrôle des secrets du bundle React : {runtime.get('status')}. Preuve : chat-runtime-checks.json. Blocages Sage conservés : {', '.join(runtime.get('sage_write_security',{}).get('blockers',[]))}.",
       f"- Registre SQL réel : {sqltools.get('status')}, {len(sqltools.get('tools_covered',[]))} outils exécutés dans TEST, aucun DML. Une requête réussie avec zéro ligne ne confirme pas la valeur recherchée. Détail : chat-sql-tools-live.json.",
       f"- Conversation de référence : {ref.get('status','NOT_COMPLETED')}, {len(ref.get('turns',[]))} messages traités par Qwen réel, consultations SQL TEST réelles. Mémoire persistée dans PostgreSQL.",
       '- Aucune écriture SQL dans les tables Sage, aucun save/modify/delete Sage. Les scénarios négatifs contrôlés sont des réponses d’outils injectées uniquement dans le processus d’évaluation ; aucune donnée fictive ajoutée à TEST.', '',
       '## Vingt exercices — deux formulations par exercice', '',
       '| N° | Exercice | Variante 1 | Variante 2 | Modèle / données SQL |',
       '|---|---|---|---|---|']
for n in range(1,21):
 rows=sorted([c for c in cases if c['number']==n],key=lambda c:c['variant'])
 status={c['variant']:c['status']+(' : '+c.get('error','') if c['status']!='PASS' else '') for c in rows}
 name=next((c.get('name') for c in rows if c.get('name')),str(n))
 lines.append(f"| {n} | {name} | {status.get(0,'NON EXÉCUTÉ')} | {status.get(1,'NON EXÉCUTÉ')} | Qwen réel ; {'SELECT TEST réels' if n==13 else 'outils SQL contrôlés de test'} |")
lines += ['', 'Chaque variante PASS comprend un ou plusieurs appels réels au modèle local avec provenance enregistrée. Les erreurs/ambiguïtés/doublons sont produits par des jeux contrôlés, sans modification de TEST. Le scénario 13 et les sept tours de référence emploient les outils SQL réels. Un PASS avec outils contrôlés n’est jamais présenté comme une validation des données ERP correspondantes.', '',
          'Les scénarios sécurité et approbation sont non destructifs : ils vérifient un refus effectif avant écriture et l’invalidation de permis de test. Aucune approbation de création Sage réelle n’a été accordée par cette campagne.', '',
          '## Brouillons Modern Foam Boards — aucun article créé', '',
          '| Champ | Article A | Article B |', '|---|---|---|']
for field in ['designation','code_article','reference_interne','categorie','unite','site','code_fournisseur','taux_tva','accounting_category','code_comptable','compte_general','code_tva','site_exclusive']:
 values=[str(a.get(field)) if a.get(field) is not None else 'Non déterminé' for a in drafts]
 lines.append('| '+field+' | '+(values[0] if len(values)>0 else 'Non disponible')+' | '+(values[1] if len(values)>1 else 'Non disponible')+' |')
lines += ['', 'Les références internes sont proposées par l’application ; elles ne sont pas des références officielles fournisseur. Site 131 connu comme déclaration, exclusivité non décidée. Une correction du fournisseur ou du code article réactualise une référence interne dérivée. Les taux et libellés sont conservés sans inventer leurs codes Sage.', '',
          '## Constat des recherches TEST pour ces brouillons', '']
if drafts:
 a=drafts[0]
 lines+=['Erreurs ou points non vérifiés retournés : '+', '.join(a.get('checks',{}).get('errors',[]))+'.',
         'La catégorie AR et le site 131 n’ont pas été trouvés par les SELECT de référence. F234 existe mais le nom retourné ne correspond pas au fournisseur déclaré Modern for Foam and Plastic : aucune association n’est confirmée. M2 existe. Un candidat de taux 20 % a été trouvé, sans preuve d’applicabilité pour ces articles. Le libellé Marchandises n’a pas permis de confirmer un code comptable applicable. Ces constats négatifs ne sont pas remplacés par des valeurs inventées.']
lines += ['', '## Corrections apportées et recontrôlées', '',
          '- Confusion initiale Qwen catégorie article/comptable : exemple explicite dans le prompt et contrôle des déclarations littérales ; les codes fiscaux/comptables restent distincts des libellés/taux.',
          '- Reconnaissance trop large des abréviations cat/u : ajout de frontières de mots pour ne pas extraire ORIE depuis catégorie ou N depuis un.',
          '- Besoin d’article interprété comme consultation : conservation d’un brouillon initial non exécutable et de la désignation complète, sans en déduire une autorisation de création.',
          '- Effet React de défilement : valeur de retour neutralisée pour éviter une erreur de nettoyage dans le navigateur. Parcours navigateur réel rejoué après correction.',
          '- Dépendance Request de la session correctement typée, puis tests d’origine, CSRF, propriétaire, rôle, expiration et confirmation booléenne.',
          '- Contrôle des valeurs non justifiées, propositions de codes bornées à 20 caractères et recontrôle de collision ; une collision utilisateur bloque, une proposition automatique peut être remplacée puis revérifiée.',
          '- Correction significative : ancien permis supprimé, ancienne approbation consommée/invalidation locale, nouvelle revue nécessaire. Vérification dans les tests PostgreSQL locaux.', '',
          '- Demande de génération de codes : un rappel des articles existants dans la réponse Qwen ne déclenche plus leur recréation comme nouveaux brouillons.',
          '- Catégorie article explicite : elle prévaut sur un fragment du libellé comptable mal classé par Qwen (March au lieu de AR). Les déclarations propres à chaque article restent séparées.', '',
          '## Limites restantes et périmètre réel', '',
          '- Créations Sage réelles non exécutées : transport vérifié, compte technique et preuves métier restent exigés ; HTTP 423 conservé. Les cas fournisseur/fiscal/unités distinctes non mappés ne sont pas envoyés approximativement.',
          '- Les conventions observées ne certifient pas une règle globale de numérotation. Codes et références proposés sont identifiés comme tels et ne sont pas réservés par un SELECT.',
          '- Fiscalité : taux, code taxe, niveau article, société, régime et date ne sont pas équivalents ; le moteur consulte les candidats mais ne prétend pas remplacer la détermination Sage.',
          '- Les unités achat/vente non déclarées et les obligations conditionnelles de catégorie restent à confirmer, sans initialisation technique inventée.',
          '- Le site est consulté et la dépendance à l’article est contrôlée ; aucune fiche article-site n’est créée implicitement.',
          '- Authentification locale par périmètre navigateur, sept jours. Pour une exposition multi-utilisateur : identité nominative, TLS et habilitations réseau à configurer séparément. Aucun accès LAN autorisé par bootstrap.',
          '- Aucun entraînement automatique : mémoire/RAG d’exemples relus par le même propriétaire, explicitement non assimilés à des règles. Architecture et conditions LoRA/QLoRA documentées, aucun fine-tuning lancé.', '',
          '## Fichiers de preuve et utilisation', '',
          '- chat-real-evaluation.json et chat-real-evaluation-run.log : inputs, JSON du modèle, provenance, messages, états et outils pour chaque cas.',
          '- chat-real-repair-run.log et chat-reference-final-run.log : échecs initiaux et rejeux après correction ; chat-reference-final.json conserve la conversation finale indépendante.',
          '- ETAPE-5-MODERN-FOAM-BROUILLONS.json : les deux brouillons et leurs contrôles, statut non créé.',
          '- chat-regression.xml/.log ; chat-browser-tests.json ; chat-desktop.png et chat-mobile.png.',
          '- chat-sql-tools-live.json : exécution réelle des treize SELECT contrôlés, notamment conversions, paramètres de catégorie et détermination fiscale.',
          '- docs/ETAPE-5-CHAT-UTILISATION.md : session, limites, mémoire, architecture, maintenance et parcours.', '',
          '## Commandes de validation et fichiers principaux', '',
          "Depuis backend (PowerShell) : `$env:RUN_STEP2_INTEGRATION='1'; .\\.venv\\Scripts\\python.exe -m pytest tests -q --junitxml=../logs/chat-regression.xml`.",
          'Depuis la racine : backend\\.venv\\Scripts\\python.exe scripts/evaluate_conversation_chat.py ; les options --repair-pass et --reference-only rejouent les scénarios après correction. Aucun de ces scripts ne lance save.',
          'Depuis frontend : Node existant avec node_modules/vite/bin/vite.js build --base=/sage/ puis tests/conversation-chat-browser.mjs.',
          'Contrôle final : backend\\.venv\\Scripts\\python.exe scripts/check_chat_runtime.py. Seul le backend agent a été redémarré ; aucun service Sage redémarré.', '',
          'Backend ajouté : app/api/chat.py, services/chat_auth.py, chat_model.py, chat_tools.py, conversation_chat.py ; migration 007-conversation-chat.sql. Frontend : ChatApp.jsx, chat.css, main.jsx. SQL contrôlé : scripts/chat_sql_tools.ps1. Tests de régression : tests/test_conversation_chat.py.', '',
          'Cette livraison ne prétend pas que les quatre objets des phases précédentes ni les deux articles Modern Foam ont été créés dans Sage.']
(log/'ETAPE-5-TESTS-AGENT-CONVERSATIONNEL.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'development_acceptance_complete':complete,'reference':ref.get('status'),'case_variants':len(cases),'passed_variants':sum(c['status']=='PASS' for c in cases),'backend_tests':counts,'browser':browser.get('status'),'sage_writes':0}))
