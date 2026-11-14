"""Build a report exclusively from measured, saved evidence; no ERP calls."""
import json
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
LOG=ROOT/'logs'
def load(name):return json.loads((LOG/name).read_text(encoding='utf-8-sig'))
def ms(value):return 'n/a' if value is None else f'{value:.2f}'
before=load('chat-performance-before.json');after=load('chat-performance-after.json')
browser=load('chat-performance-browser.json');quality=load('chat-performance-final-routing-quality.json')
profile=load('chat-performance-qwen-profile.json')
modern=load('chat-performance-modern-browser.json');navigation=load('chat-performance-navigation.json')
replay=load('chat-performance-replay.json');pool=load('chat-performance-sql-pool.json')
assert all(c['status']=='PASS' for c in before['cases']+after['cases'])
assert browser['status']==replay['status']=='PASS'
assert modern['status']==navigation['status']=='PASS'
assert len(quality['cases'])==40 and all(c['status']=='PASS' for c in quality['cases'])
lines=['# Performances du chatbot AGENT-SAGE-X3','',f'Rapport généré le {datetime.now(timezone.utc).isoformat()}.',
       '', 'Application : http://127.0.0.1:8000/sage/',
       '', 'Optimisations exécutées sur la VM agent. Aucune écriture Sage, aucun changement des services, index, comptes ou paramètres de la production.',
       '', '## Comparaison réelle FastAPI',
       '', 'Même texte par cas, sessions locales HTTP réelles, SQL TEST réel et PostgreSQL réel. Une observation par combinaison, pas un percentile statistique. Froid = modèle Ollama déchargé ; cache disque Windows et caches SQL du chatbot non vidés. Le nombre d’articles et les validations sont vérifiés.',
       '', '| Articles | Modèle | Avant complet (s) | Après complet (s) | Premier événement après (s) | Route après |',
       '|---|---|---:|---:|---:|---|']
for a,b in zip(before['cases'],after['cases']):
    assert (a['articles'],a['mode'])==(b['articles'],b['mode'])
    lines.append(f"| {a['articles']} | {a['mode']} | {a['http_total_ms']/1000:.2f} | {b['http_total_ms']/1000:.2f} | {b['first_response_ms']/1000:.2f} | {b['performance']['extraction_route']} |")
lines+=['', 'Le premier événement est un accusé de réception, pas un résultat métier. Les désignations comprises arrivent ensuite, explicitement à vérifier, puis les brouillons et résultats SQL contrôlés.',
        '', 'Les cas explicites à un, deux et dix articles utilisent un parseur strict : aucune clause ignorée, aucune valeur par défaut ajoutée. Une clause non reconnue retourne à Qwen. Ces temps ne représentent donc pas une inférence Qwen accélérée. La phrase Modern Foam est entièrement structurée et reconnue ; les autres formulations libres continuent d’utiliser Qwen.',
        '', '## Décomposition des mesures après optimisation',
        '', '| Articles | Mode | SQL mural ms | Somme requêtes SQL ms | Cache hits | SQL frais | Connexions PG ms | Lectures PG ms | Total requêtes PG ms | Composition réponse ms |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for c in after['cases']:
    p=c['performance']
    lines.append(f"| {c['articles']} | {c['mode']} | {ms(p.get('sql_wall_ms'))} | {ms(p.get('sql_query_ms'))} | {p.get('sql_cache_hits',0)} | {p.get('sql_fresh_calls',0)} | {ms(p.get('pg_connect_ms'))} | {ms(p.get('pg_read_ms'))} | {ms(p.get('pg_query_ms'))} | {ms(p.get('response_compose_ms'))} |")
lines+=['', 'Les durées SQL murales incluent les échanges avec les workers ; les durées des requêtes sont additionnées et peuvent dépasser le temps mural avec deux connexions parallèles. Les mesures PostgreSQL concernent uniquement la base interne de l’agent. Les lectures PG incluent les SELECT de configuration de session. Avant optimisation, les requêtes PG étaient chronométrées ensemble, sans séparation lecture/écriture.',
        '', '## Qwen : mesures distinctes',
        '', '| Version | Articles | Mode | Chargement s | Premier token s | Évaluation prompt s | Génération tokens s | Appel Qwen total s | Tokens prompt / sortie |',
        '|---|---|---|---:|---:|---:|---:|---:|---|']
for label,data in [('Avant HTTP',before),('Après HTTP',after),('Après profilage modèle séparé',profile)]:
    for c in data['cases']:
        q=c['performance'].get('qwen')
        if not q:continue
        observed=label+' — extraction NON VALIDE' if c.get('status')=='FAILED' else label
        lines.append(f"| {observed} | {c['articles']} | {c['mode']} | {q['load_duration']/1e9:.2f} | {q['qwen_first_token_ms']/1000:.2f} | {q['prompt_eval_duration']/1e9:.2f} | {q['eval_duration']/1e9:.2f} | {q['qwen_http_ms']/1000:.2f} | {q['prompt_eval_count']} / {q['eval_count']} |")
lines+=['', 'Le profilage forcé du modèle, hors routage normal, a produit deux extractions non conformes : AR classé comme compte général. Les temps correspondants sont uniquement des mesures techniques, pas des réponses métier validées. Dans le parcours réel, cette formulation entièrement structurée utilise le parseur strict et conserve AR comme catégorie ; les 40 scénarios et le rejeu React passent. Cette faiblesse du modèle brut reste une limite : ne pas le traiter comme une autorité métier ni prétendre que toute formulation libre est fiable. Les sorties brutes et statuts négatifs restent dans chat-performance-qwen-profile.json.']
lines+=['', 'Une seule extraction Qwen par demande nécessitant le modèle ; la réponse finale est composée à partir des données validées, sans second appel génératif. keep_alive=30m, contexte borné à 8192, même modèle et même quantification. Le JSON partiel du modèle n’est pas présenté comme un fait. Le prompt métier éprouvé est conservé ; schéma sans titres/defaults superflus, valeurs inconnues toujours autorisées, état structuré et deux messages utilisateur antérieurs maximum de 600 caractères chacun.',
        '', '## Affichage React réel dans Edge',
        '', '| Articles | Mode | Premier événement navigateur ms | Réponse et affichage complets ms | Réception finale → deux frames ms |',
        '|---|---|---:|---:|---:|']
for c in browser['results']:
    lines.append(f"| {c['articles']} | {c['mode']} | {ms(c['first_event_ms'])} | {ms(c['total_ms'])} | {ms(c['final_render_ms'])} |")
lines+=['', 'Mesures obtenues avec fetch SSE et requestAnimationFrame dans Edge réel. Aucun mock réseau dans ces essais. La peinture React avant optimisation n’était pas instrumentée : aucune valeur avant n’est inventée. Les comparaisons avant/après complètes viennent du benchmark HTTP séparé.',
        '', 'La zone de saisie reste éditable pendant l’analyse, le texte préparé n’est pas perdu. Historique et nouvelle conversation restent accessibles. Une seule génération à la fois est autorisée pour éviter les révisions concurrentes ; les résultats d’une conversation ne remplacent pas une autre conversation ouverte.',
        '', '## SQL et cache',
        '', 'Deux workers PowerShell persistants et deux connexions physiques SQL maximum. Chaque worker utilise un pool .NET borné à une connexion. Réutilisation réelle des connexions confirmée : '+str(pool['same_physical_connections_reused'])+'. Requêtes prédéfinies SELECT paramétrées et limitées ; aucune requête arbitraire du modèle. Les phases indépendantes utilisent les deux workers ; les phases dépendantes restent ordonnées.',
        '', 'Cache borné à 512 clés : référentiels 300 s, fiscalité 60 s, recherches/articles récents/fournisseurs 15 s. Doublons, existence article-site et références fournisseur/article toujours frais. Échecs jamais mis en cache. Le contrôle initial et l’âge du cache restent visibles ; un résultat servi du cache n’est pas annoncé comme une nouvelle lecture. Invalidation par « Actualise les informations » / « Rafraîchis les informations » et au redémarrage du backend. Le mode de transport SQL existant est conservé ; aucune modification TLS réalisée pendant cette tâche.',
        '', '## Validation fonctionnelle',
        '', 'Campagne : 20 scénarios × 2 variantes, 40/40 PASS sur le routage réellement utilisé. Appels Qwen réels : '+str(sum(bool(s['provenance'].get('real_model_called')) for c in quality['cases'] for s in c.get('steps',[])))+'. Les cas négatifs SQL utilisent des fixtures explicitement identifiées ; le scénario 13 consulte réellement TEST. Les benchmarks, le rejeu Modern Foam et la preuve de pool utilisent aussi SQL réel.',
        '', 'Rejeu Modern Foam : 12/12 tours PASS, également 12/12 depuis React → FastAPI → SQL réel avec relecture de la mémoire PostgreSQL. Deux identités et deux codes conservés, unité M2, site 131, fournisseur corrigé F992, TVA proposée 20 %, recherche NEGOSE et confirmation NEG distinctes. Les questions ne modifient pas les champs. Les anciennes références F234 sont conservées dans l’historique comme obsolètes.',
        '', 'Le test de navigation a détecté puis permis de corriger une course entre création asynchrone de conversation et ouverture de l’historique : un compteur de vue empêche désormais l’ancien traitement de remplacer la conversation sélectionnée. Rejeu PASS. Ce test utilise uniquement un délai réseau artificiel de 600 ms pour reproduire la course, avec vraies réponses API/SQL ; ses temps sont exclus du benchmark.',
        '', 'Tests automatisés : voir chat-performance-final-tests.xml et chat-performance-security-tests.log. Contrôles supplémentaires : cache, absence de cache des doublons/erreurs, limites des batches, aucune clause perdue, une seule extraction, keep_alive, protection CSRF, absence d’accès propriétaire croisé et révision périmée. HTTP 423 reste actif et les écritures Sage restent désactivées.',
        '', '## Optimisations écartées et limites',
        '', 'Un premier prompt système raccourci a échoué sur la conservation des dix articles puis sur les fournisseurs inconnus/ambigus. Ces essais sont archivés dans chat-performance-after-first-attempt.json et chat-performance-compact-prompt-rejected.json ; leurs chiffres ne sont pas utilisés comme résultats finaux. Le prompt métier éprouvé et les types nullables sont conservés.',
        '', 'La cible 3–8 secondes est atteinte pour les formulations simples reconnues directement, pas garantie pour chaque formulation libre. Qwen 7B tourne sur CPU sur cette VM : chargement et génération restent les goulots. Aucun modèle plus léger téléchargé ni quantification changée sans preuve de qualité. Le maintien 30 minutes consomme de la RAM ; les mesures VM sont dans chat-performance-vm.json. Aucun P95, test de charge multi-opérateur ou durée de peinture avant n’est revendiqué.',
        '', '## Fichiers et reproduction',
        '', '- backend/app/services/chat_model.py, chat_fast_extract.py, chat_tools.py, chat_performance.py, business_store.py et conversation_chat.py.',
        '- backend/app/api/chat.py ; frontend/src/ChatApp.jsx.',
        '- scripts/chat_sql_worker.ps1 et chat_sql_queries.ps1 : workers SELECT uniquement.',
        '- scripts/benchmark_chat_performance.py --label after --stream : benchmark réel, décharge le modèle avant les cas froids.',
        '- frontend/tests/chat-performance-browser.mjs : parcours Edge réel ; scripts/replay_chat_performance.py : rejeu métier.',
        '- scripts/evaluate_conversation_chat.py --production-routing --skip-reference --variants 2 --output chat-performance-final-routing-quality.json.',
        '- RUN_STEP2_INTEGRATION=1 puis backend/.venv/Scripts/python.exe -m pytest tests -q : tests locaux et contrôles de régression.',
        '', 'Aucune création d’article Sage n’a été effectuée pendant cette optimisation.']
(LOG/'ETAPE-5-PERFORMANCES-CHATBOT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Report generated from saved evidence.')
