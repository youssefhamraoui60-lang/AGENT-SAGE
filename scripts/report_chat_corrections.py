"""Report observed corrective tests, preserving distinctions between live and controlled data."""
import json,xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];L=ROOT/'logs'
def read(name):
 p=L/name
 return json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else {}
sql=read('chat-corrections-sql-diagnostic.json');replay=read('chat-corrections-replay.json');qwen=read('chat-corrections-qwen-evaluation.json');browser=read('chat-corrections-browser.json');runtime=read('chat-runtime-checks.json')
memory=read('chat-corrections-existing-memory.json')
livebrowser=read('chat-browser-tests.json')
suite=ET.parse(L/'chat-corrections-regression.xml').getroot()
counts={k:sum(int(s.get(k,'0')) for s in suite.iter('testsuite')) for k in ['tests','failures','errors','skipped']}
initial_cases=qwen.get('cases',[])
index={(c['number'],c['variant']):{**c,'evidence_file':'chat-corrections-qwen-evaluation.json'} for c in initial_cases}
for c in read('chat-corrections-qwen-repairs.json').get('cases',[]):index[c['number'],c['variant']]={**c,'evidence_file':'chat-corrections-qwen-repairs.json'}
cases=sorted(index.values(),key=lambda c:(c['number'],c['variant']))
(L/'chat-corrections-qwen-final.json').write_text(json.dumps({'kind':'LATEST_RESULT_PER_VARIANT_WITH_ORIGINAL_EVIDENCE_PRESERVED','cases':cases,'sage_writes':0},ensure_ascii=False,indent=2),encoding='utf-8')
complete=len(cases)==40 and all(x['status']=='PASS' for x in cases) and replay.get('status')=='PASS' and len(replay.get('turns',[]))==12 and browser.get('status')=='PASS' and memory.get('status')=='PASS' and runtime.get('status')=='PASS' and livebrowser.get('status')=='PASS' and livebrowser.get('checked_at','')>=sql.get('checked_at','') and not any(counts[k] for k in ['failures','errors','skipped'])
lines=['# Correctifs conversationnels et SQL — AGENT-SAGE-X3','',
 f"Rapport généré : {datetime.now(timezone.utc).isoformat()}. Recette corrective complète : **{'OUI' if complete else 'NON — contrôles incomplets ou en échec'}**.",'',
 'Interface locale : http://127.0.0.1:8000/sage/. Aucune écriture Sage, aucun service/certificat/compte Sage modifié. Les quatre blocages HTTP 423 restent conservés.','',
 '## Causes et corrections','',
 'Les 178 tests initiaux ne couvraient pas les questions transformées en valeurs, le message mixte réel avec fautes, ni plusieurs résultats SQL complets. La recette corrective ajoute des assertions sur les champs et les paramètres exacts, y compris des JSON Qwen volontairement erronés, plutôt que de se limiter au statut HTTP.','',
 '- EST : une expression régulière prenait le mot suivant site, puis le moteur appliquait indistinctement les valeurs extraites par Qwen. chat_turns.py classe maintenant déclaration, question, vérification, correction, confirmation et annulation. Les questions/vérifications ne modifient aucun champ métier, même avec un JSON Qwen erroné.',
 '- Corrections de site : la destination de « Change le site 131 vers 201 » prévaut sur le premier nombre. « Le site est 131 » est une déclaration explicite ; EST est un mot grammatical, pas une valeur.',
 '- Catégories : recherche antérieure limitée au code. Ajout de TCLDES_0, recherche tolérante aux accents et au préfixe NEGO, consultation des lignes générales et par STOFCY_0. Un intitulé trouvé propose un code à confirmer, sans changer AR. Une catégorie disponible seulement pour un autre site n’est plus annoncée absente de tout TEST.',
 '- Intitulés entre guillemets : une extraction trop permissive pouvait revenir sur le préfixe categ et produire ORIE si des espaces suivaient «. Frontière de mot obligatoire et espaces internes aux guillemets gérés ; tests sur le paramètre exact NEGOSE envoyé à SQL.',
 '- Fournisseur : F992 est conservé et recherché exactement ; une seconde recherche par nom est séparée. LEFT JOIN permet de distinguer un fournisseur existant d’une identité associée manquante. Une consultation indisponible n’est pas présentée comme une absence.',
 '- Références dérivées : les références F234 remplacées par F992 sont archivées explicitement comme obsolètes ; les références courantes sont recalculées. Les identifiants des deux brouillons et leurs codes restent stables.',
 '- Message mixte réel retrouvé : « pour la ctigorier c\'est NEGOSE vérifier si il y a déaja comme ce nome pour le fornisseur est F992 ». La clause de vérification conserve AR ; la déclaration indépendante renseigne F992. Les fautes ctigorier/fornisseur sont prises en charge sans autoriser Qwen à modifier les autres champs.',
 '- Comparables : leurs codes comptables sont vérifiés dans GACCCODE. Le niveau de taxe VACITM est suivi via TABVAC, puis les codes taxe et taux via TABVAT/TABRATVAT. Les observations gardent leur provenance et une confiance indicative ; elles ne sont pas appliquées comme des règles métier.',
 '- Réponses : synthèse en français des sites retournés, du fournisseur réellement trouvé, des comparables et des contradictions. JSON disponible uniquement dans des diagnostics repliés. Les brouillons affichent les anciennes références obsolètes.',
 '- Non-régression réelle supplémentaire : un besoin explicite d’un seul article reste un brouillon même si Qwen renvoie une consultation sans entité. La chaîne fiscale des comparables possède un test dédié avec de vraies formes de résultats, afin de ne pas limiter les tests à HTTP 200.','',
 '## Résultats SQL réellement observés','',
 '| Contrôle | Résultat |','|---|---|',
 '| TEST.FACILITY, recherche exacte 131 | Aucune ligne, sans jointure ni filtre de statut. La liste bornée de sites retourne 201, 202, 209, 301. |',
 '| Autres FACILITY accessibles | Recherches exactes du seul code 131 dans OB, TEST1 et X3 : aucune ligne. Cela ne prouve pas une absence dans un autre serveur ou un schéma non accessible. |',
 '| Article-site 131 | Aucune ligne retournée par le contrôle borné TEST.ITMFACILIT. Habilitations de création non certifiées par SQL. |',
 '| Catégories AR / NEG / NEGOSE | AR non retrouvée. NEG, intitulé Négoce, ligne générale STOFCY_0 vide. NEGOSE conduit à cette proposition par recherche proche, à confirmer. |',
 '| Clés ITMCATEG | Index uniques STOFCY_0 + TCLCOD_0 et TCLCOD_0 + STOFCY_0 réellement lus. |',
 '| Fournisseur F992 | Existe ; raison sociale CORYAD. Aucun fournisseur Modern trouvé par la recherche limitée du nom. Association au nom demandé non validée. |',
 '| E-XPS_8 | NEG ; M2 ; code comptable POLYSTYREN ; niveau de taxe T20. |',
 '| XPS_FO2500_40 | NEG ; SAC ; code comptable 61110001 ; niveau T20. |',
 '| XPS_SL_40 | NEG ; M2 ; code comptable 61110001 ; niveau T20. |',
 '| GACCCODE type article | POLYSTYREN : Polystyrène, plan MAR. 61110001 : Colle, plan général/MAR. Les chiffres ne prouvent pas un compte général. |',
 '| Fiscalité | TABVAC MAR_T20 : niveau T20, régime MAR, code taxe T20. Le taux lu pour T20 est 20 %. Applicabilité à un nouveau produit non déduite de ce seul résultat. |','',
 'Les requêtes et leurs paramètres, les colonnes et les résultats sont conservés dans chat-corrections-sql-diagnostic.json. Les comptes et droits SQL n’ont pas été modifiés. Aucun DML vers x3v12.','',
 '## Tests exécutés','',
 f"- Suite automatisée : {counts['tests']} tests, {counts['failures']} échec, {counts['errors']} erreur, {counts['skipped']} ignoré. Inclut PostgreSQL local isolé par schéma de test ; aucun DML dans Sage.",
 f"- Campagne Qwen : {sum(c['status']=='PASS' for c in cases)}/{len(cases)} variantes PASS. Modèle réel dans chaque exercice ; cas négatifs alimentés par des réponses SQL contrôlées et explicitement distinguées. Le scénario 13 emploie de vrais SELECT TEST.",
 f"- Rejeu des extraits utilisateur : {replay.get('status','NON EXÉCUTÉ')}, {len(replay.get('turns',[]))}/12 tours ; Qwen réel et SELECT TEST réels. Chaque tour vérifie les deux identifiants, les champs attendus, les codes, les références, les résultats d’outils et les réponses.",
 f"- Navigateur : {browser.get('status','NON EXÉCUTÉ')}. Test du rendu avec les états réellement capturés pendant le rejeu, sans nouvel appel Qwen/SQL et sans prétendre réauthentifier un autre propriétaire. Session locale réelle, données GET de diagnostic injectées uniquement par Playwright. Contrôles : {', '.join(browser.get('checks',[]))}.",
 f"- Parcours navigateur avec appels réels FastAPI/Qwen/SQL : {livebrowser.get('status','NON EXÉCUTÉ')}, horodatage {livebrowser.get('checked_at','ancien résultat sans date — non retenu pour la recette corrective')}. Deux articles, réponse 131, rechargement et reprise d’historique. Preuve : chat-browser-tests.json.",
 '- Le premier passage a détecté des échecs ; ils sont conservés dans les journaux et seuls les scénarios touchés sont rejoués après correction. La table ci-dessous utilise la dernière exécution par variante, avec son fichier source dans chat-corrections-qwen-final.json. Les premières réponses fautives restent dans le fichier original. Une réussite avec un double SQL ne constitue pas une validation des données ERP.',
 'Échecs du premier passage : '+', '.join(f"exercice {c['number']}, variante {c['variant']+1} ({c.get('error','assertion non satisfaite')})" for c in initial_cases if c['status']!='PASS')+'.','',
 '| Exercice | Variante 1 | Variante 2 |','|---|---|---|']
for n in range(1,21):
 matches={c['variant']:c['status'] for c in cases if c['number']==n}
 lines.append(f"| {n} | {matches.get(0,'NON EXÉCUTÉ')} | {matches.get(1,'NON EXÉCUTÉ')} |")
lines+=['','## Conversation et état final','',
 'La transcription ETAPE-5-CORRECTIONS-TRANSCRIPTION.md reproduit les phrases fournies dans un ordre de test explicite. Le document utilisateur contenait des extraits et non un export intégral de la conversation originale ; aucun échange manquant n’est présenté comme une citation originale.','',
 '| Champ | Article A | Article B |','|---|---|---|']
drafts=replay.get('final_drafts',[])
for key in ['designation','code_article','reference_interne','categorie','unite','site','code_fournisseur','taux_tva']:
 vals=[str(a.get(key)) for a in drafts]
 lines.append('| '+key+' | '+(vals[0] if len(vals)>0 else 'Non terminé')+' | '+(vals[1] if len(vals)>1 else 'Non terminé')+' |')
lines+=['','Les deux références F234 sont marquées obsolètes. NEG est appliqué uniquement au message de confirmation, et la correction site 201 est suivie d’une déclaration explicite revenant à 131. Aucun code comptable ou code TVA n’est ajouté au brouillon par analogie.','',
 '## Réparation de la conversation utilisateur déjà enregistrée','',
 f"Résultat : {memory.get('status','NON EXÉCUTÉ')}. Conversation : {memory.get('conversation_id','non disponible')}. Site 131 restauré depuis le message utilisateur 362 ; dernier message 368 retraité et contrôles SQL relancés. Historique original conservé et message système de réparation enregistré.",
 'Dans cette conversation historique : deux brouillons, site 131, fournisseur F992, références F992-MFB-A-40 et F992-MFB-B-40. AR reste déclarée ; NEG — Négoce attend confirmation. Aucun taux ajouté silencieusement à cette conversation qui ne contenait pas encore de déclaration TVA. Le rejeu de douze tours ci-dessus comporte une déclaration explicite de TVA et une confirmation NEG.',
 'Preuve : chat-corrections-existing-memory.json. Recharger la conversation existante pour voir les valeurs corrigées.','',
 '## Fichiers modifiés et limites','',
 '- backend/app/services/chat_turns.py : actes conversationnels contrôlés ; conversation_chat.py : mémoire, application des corrections, propositions, confirmations et réponses sourcées.',
 '- backend/app/services/chat_model.py : schéma/prompts structurés ; chat_tools.py et scripts/chat_sql_tools.ps1 : paramètres et référentiels bornés.',
 '- frontend/src/ChatApp.jsx : références obsolètes, comparables et messages de contrôle en français.',
 '- backend/tests/test_conversation_chat.py : régressions ciblées ; scripts/diagnose_chat_corrections.ps1, replay_chat_corrections.py et frontend/tests/chat-corrections-browser.mjs : diagnostics et preuves reproductibles.',
 '- scripts/repair_chat_existing_conversation.py : réparation ciblée et auditée ; scripts/evaluate_conversation_chat.py et report_chat_corrections.py : évaluations et consolidation des preuves ; frontend/tests/conversation-chat-browser.mjs : horodatage du parcours réel.',
 '- docs/ETAPE-5-CHAT-UTILISATION.md : parcours corrigés ; ancien rapport initial annoté avec le lien vers ce correctif.',
 '- Rapports/tests : chat-corrections-regression.xml/.log, chat-corrections-qwen-evaluation.json, chat-corrections-qwen-run.log, chat-corrections-replay.json et chat-corrections-browser.json.','',
 '- Les règles conditionnelles de création et les habilitations applicatives ne sont pas prouvées par des SELECT. Site 131 reste déclaré et non validé ; F992 est trouvé mais ne correspond pas au nom demandé. Aucun remplacement automatique par un autre site ou fournisseur.',
 '- Les comptes comptables généraux et la fiscalité applicable au nouveau produit nécessitent encore une revue métier ; les exemples XPS et les taux ne valent pas autorisation.',
 '- Les codes et références sont provisoires et non réservés. Le modèle local peut encore mal extraire des formulations nouvelles ; l’état est protégé par la logique déterministe, et les cas non reconnus doivent être reformulés.',
 '- Interface limitée au navigateur local autorisé, pas d’authentification nominative LAN ajoutée. Temps de réponse du modèle CPU variable ; historique conservé pendant l’analyse.',
 '- Aucune création réelle, aucun assouplissement HTTP 423, aucune modification du serveur Sage.']
(L/'ETAPE-5-CORRECTIONS-CONVERSATION-SQL.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'corrective_acceptance_complete':complete,'backend':counts,'qwen_variants':len(cases),'qwen_passed':sum(c['status']=='PASS' for c in cases),'replay':replay.get('status'),'browser':browser.get('status'),'sage_writes':0}))
