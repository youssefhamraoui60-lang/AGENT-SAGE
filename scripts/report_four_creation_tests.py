"""Generate the requested report strictly from observed evidence; no network calls."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sql=json.loads((ROOT/'logs/four-creation-sql-discovery.json').read_text(encoding='utf-8-sig'))
prep=json.loads((ROOT/'logs/four-creation-preparations.json').read_text())
soap=json.loads((ROOT/'logs/four-creation-soap-discovery.json').read_text())
lines=['# Tests de création Sage X3 V12 — TEST', '',f"Préparation du {prep['checked_at']} (UTC), 19 octobre 2026. **Aucune création exécutée, aucune approbation accordée.** SQL et SOAP en lecture, préparations locales PostgreSQL seulement. Aucun changement de sécurité ni suppression.",
       '', '## Tableau des résultats réels', '',
       '| Type | Code réellement créé | Code proposé | Dossier / site | Service SOAP | Résultat SOAP création | Résultat SQL | Statut | Blocage |',
       '|---|---|---|---|---|---|---|---|---|',
       '| Article | Aucun | AITEST001 | TEST | WS_ARTICLE / ITM | Non envoyé | Absent ITMMASTER | Bloqué | Sécurité et accord humain |',
       '| Article-site | Aucun | AITEST001 / 201 | TEST / 201 | WS_AR_SITE / ITF | Non envoyé | Aucun ITMFACILIT pour cet article | Bloqué | Parent absent, droits site et sécurité à valider |',
       '| Fournisseur | Aucun | F_AITEST01 | TEST | WS_FOURNIS / BPS | Non envoyé | Absent BPSUPPLIER et BPARTNER | Bloqué | Sécurité et accord humain |',
       '| Client | Aucun | C_AITEST01 | TEST | Aucun service BPC trouvé dans AWEBSERVIC | Non envoyé | Absent BPCUSTOMER et BPARTNER | Bloqué | Publication/mapping et parcours API client indisponibles |',
       '', '« Bloqué » n’est pas une tentative échouée : aucun save n’a été envoyé. Il n’existe donc ni réponse SOAP complète de création, ni code retour de création, ni confirmation SQL après création. Aucun succès n’est annoncé.',
       '', '## Diagnostic SQL réel', '',
       '- Connexion de la VM agent vers sage/SAGEX3:1433, x3v12 avec agent_sage_x3, mode de chiffrement optionnel TMS demandé précédemment. Aucune prétention de transport TLS vérifié. Aucun changement de certificat ou paramètre de connexion dans cette intervention.',
       '- SELECT paramétrés, TOP/délais bornés, données métier du seul schéma TEST ; métadonnées de tables explicitement nommées. Aucune requête SQL libre et aucun INSERT/UPDATE/DELETE. Les données de clients/fournisseurs réels (adresses, comptes bancaires, contacts) ne sont pas extraites.',
       '- Tables trouvées : '+', '.join(sorted({c['table_name'] for c in sql['columns']}))+'.',
       '- Clés uniques observées : ITMMASTER.ITMREF_0 ; ITMFACILIT.ITMREF_0+STOFCY_0 ; BPSUPPLIER.BPSNUM_0 ; BPCUSTOMER.BPCNUM_0 ; BPARTNER.BPRNUM_0. Les indexes ROWID et autres indexes existent aussi.',
       '- Aucune FK SQL déclarée retournée pour ces quatre tables. Cela ne prouve pas l’absence de relations applicatives : les contrôles objets Sage restent déterminants.',
       '- Relations logiques à respecter : ITMFACILIT.ITMREF_0 → ITMMASTER.ITMREF_0, STOFCY_0 → FACILITY.FCY_0 ; BPSNUM_0/BPCNUM_0 → BPARTNER.BPRNUM_0 ; catégories vers ITMCATEG/BPSCATEG/BPCCATEG ; unités vers TABUNIT. Les nouvelles clés partenaires ont également été recherchées dans BPARTNER pour prévenir une collision partagée.',
       '- Sur les quatre objets SQL : SELECT=1, INSERT=0, UPDATE=0, DELETE=0. Ces vérifications SQL ne prouvent aucun droit SOAP.',
       '', '## Configuration TEST observée', '',
       '| Configuration | Valeurs SQL réelles |', '|---|---|']
for key in ['article_category','site','unit','supplier_categories','customer_categories']:
    lines.append('| '+key+' | '+json.dumps(sql[key],ensure_ascii=False)+' |')
lines += ['', 'Le site 201 existe, société 20, pays MA, indicateurs vente/achat/stock 2. Il est proposé comme site TEST ; le droit métier de création ITF sur ce site **n’est pas certifié** par son existence ni par une ancienne lecture.',
          '', 'La catégorie NEG au niveau dossier a STU/PUU/SAU=UN, coefficients 1, STOMGTCOD=2, LOTMGTCOD=1 et ABCCLS=1. ACCCOD est vide : le brouillon ne copie donc pas aveuglément le code comptable CPJ35 d’un ancien article. Le compte comptable et les éventuelles autres obligations doivent être revus avant écriture.',
          '', 'Aucun compteur explicite non vide dans les catégories examinées ; aucun compteur n’a été avancé ni réservé. Les champs ITMCREMOD/CREMOD concernent le mode de création/validation, pas une preuve d’acceptation de toutes les références manuelles. Les codes respectent les longueurs SOAP publiées (ITM 20, BPS 15), mais les règles de saisie/specifics restent à valider. Pour BPC, pas de longueur SOAP publiée vérifiable faute de publication.',
          '', 'La documentation Sage précise qu’une catégorie article peut fournir les défauts et qu’un compteur renseigné peut imposer une référence automatique : [catégorie article](https://online-help.sagex3.com/erp/12/fr-fr/Content/FCT/GESITG.htm). Les catégories de tiers et leurs valeurs initiales demandent aussi revue : [fournisseurs](https://online-help.sagex3.com/erp/12/fr-fr/Content/FCT/GESBSG.htm), [clients](https://online-help.sagex3.com/erp/12/fr-fr/Content/FCT/GESBCG.htm).',
          '', '## Publications et droits SOAP', '',
          'TEST.AWEBSERVIC contient, pour les objets ITM/ITF/BPS/BPC recherchés, exactement WS_ARTICLE/ITM, WS_AR_SITE/ITF et WS_FOURNIS/BPS. Les trois getDescription réels confirment V12/TEST et CREATE publié ; l’identité retournée reste administrateur. WS_CLIENT et WS_CUSTOMER testés en getDescription répondent sage_business_error. Cela ne démontre pas la disponibilité d’un autre nom client : aucune publication BPC correspondante n’est trouvée dans le périmètre SQL examiné.',
          '', 'La présence de CREATE décrit les possibilités publiées, pas les droits d’un compte technique approuvé. L’administration métier doit valider l’identité effective, profils/options, restrictions TEST/site 201 et champs conditionnels. Aucun compte, profil, publication ou pool modifié.',
          '', 'L’URL http://192.168.9.200:8080/ fournie n’est pas assimilée au SOAP. Les connecteurs utilisent l’endpoint déjà validé http://192.168.9.200:8124/soap-generic/syracuse/collaboration/syracuse/CAdxWebServiceXmlCC.',
          '', '## Données et XML préparés sans écriture']
for resource,r in prep['resources'].items():
    lines += ['',f'### {resource}', '']
    if resource=='customers':
        lines += ['Données proposées uniquement :', '', '```json',json.dumps({'keys':r['keys'],'values':r['data_proposed']},indent=2,ensure_ascii=False),'```', '',
                  '**Aucun XML client prétendument exécutable n’est inventé.** La publication BPC, son mapping, ses champs obligatoires et ses autorisations doivent d’abord être établis. Le parcours FastAPI actuel n’exécute que les trois ressources existantes. Toute publication/modification serveur nécessite autorisation séparée.']
        continue
    op=r['operation'];lines += [f"Publication {r['publication']}, UUID `{op['id']}`, digest `{op['digest']}`, état `{op['status']}`. PostgreSQL conserve les valeurs et l’état avant.", '',
                             '```json',json.dumps(r['request'],indent=2,ensure_ascii=False),'```', '', '```xml',op['object_xml'].rstrip(),'```', '',
                             f"Enveloppe save sérialisée via Zeep create_message contre le WSDL réel, non envoyée : examples/four-creation-tests/{resource}-NOT-SENT.xml."]
lines += ['', 'Les trois préparations FastAPI ont retourné HTTP 200 ; l’état métier ITF est blocked/PARENT_ARTICLE_NOT_FOUND. Les autres états prepared signifient seulement brouillon structurel valide, pas prêt à exécuter en sécurité. Les règles obligatoires conditionnelles ne sont pas toutes déterminables depuis les seuls champs SQL ou la description SOAP.',
          '', 'Après création ITM autorisée, lire SQL ITMFACILIT et SOAP ITF : si Sage a généré la fiche 201 automatiquement, ne pas envoyer un second save. Si elle est absente, refaire une préparation, valider site/données puis demander un accord distinct.',
          '', '## Cas d’erreur réellement testés, non destructifs', '', '```json',json.dumps(prep['negative_tests'],indent=2),'```', '',
          'Article existant CPJ35 : préparation bloquée DUPLICATE_EXISTS, aucun changement de la fiche. Champ non publié et code mal formé : HTTP 422. Approbations volontairement confirm=false : refus HTTP 423 avant délivrance de jeton. ITF parent absent : préparation bloquée. Aucun cas d’erreur n’envoie save ni ne modifie Sage.',
          '', '## Blocages actuels et prochaine validation', '',
          'Gate FastAPI : '+', '.join(prep['security']['blockers'])+'. L’accord antérieur au mode SQL TMS n’autorise aucune désactivation des protections SOAP. Aucun drapeau ni preuve de droits fictive créé.',
          '', 'Avant une demande de création exécutable : établir un transport SOAP conforme au gate, un compte technique TEST non administrateur et les justificatifs de droits/règles. Pour le client, obtenir une publication BPC autorisée et valider le parcours API supplémentaire. Tous changements serveur restent soumis à accord préalable.',
          '', 'Après ces conditions : actualiser l’absence SQL/SOAP, présenter à nouveau données/XML/UUID/digest final, obtenir une autorisation spécifique pour chaque objet, une seule tentative via FastAPI. Réponse ambiguë : pas de retry ; lecture et investigation seulement.',
          '', 'Conservation des futures réponses SOAP complètes ajoutée dans backend/app/services/sage_gateway.py : corps borné archivé avant décodage dans runtime/soap-write-responses/{UUID}.xml, sans en-têtes HTTP, ouverture exclusive sans écrasement et SHA256. Le résultat décodé et la relecture restent dans PostgreSQL ; chemin/hash sont rattachés au résultat quand le décodage réussit. En cas de réponse SOAP invalide, le fichier UUID reste disponible pour investigation, sans retry. Ces fichiers sont hors interface publique et hors dépôt ; les inclure dans les sauvegardes privées de preuves. Aucun corps de réponse de vraie création n’existe actuellement.',
          '', 'Tests automatisés après cette modification : **144 réussis**, un avertissement existant Starlette/httpx ; preuve four-creation-regression.xml/.log. Les deux nouveaux tests vérifient conservation intégrale, hash, refus d’écrasement, UUID mal formé et taille excessive. Les tests d’écriture SOAP existants utilisent une simulation, jamais le serveur Sage.',
          '', 'Après chaque création réellement autorisée : read SOAP + SELECT SQL paramétré, comparaison des champs/langue/clés/relations puis affichage React et historique. Pas de succès sur un seul HTTP 200. Pas de suppression automatique.',
          '', '## Vérification manuelle future', '',
          '- TEST → GESITM → AITEST001.',
          '- TEST → GESITF → AITEST001 / 201.',
          '- TEST → GESBPS → F_AITEST01.',
          '- TEST → GESBPC → C_AITEST01.',
          '', 'Les quatre clés sont actuellement absentes ; ces chemins ne constituent pas une confirmation de création. Aucune modification ni suppression d’un autre enregistrement.',
          '', '## Preuves et scripts', '',
          '- four-creation-sql-discovery.json : schémas/colonnes/clés/configurations/permissions/absence, uniquement SELECT.',
          '- four-creation-soap-discovery.json : descriptions et sondes client ; XML des descriptions dans runtime/four-*-description.xml.',
          '- four-creation-preparations.json : requêtes, XML, UUID/digests, contrôles et résultats des tests négatifs.',
          '- Scripts : diagnose_four_creation_sql.ps1, discover_four_soap.py, prepare_four_creation_tests.py, report_four_creation_tests.py.',
          '', f"Bilan réel : **{prep['real_approvals']} approbation, {prep['real_write_attempts']} tentative d’écriture SOAP, 0 création SQL/SOAP.** La mission reste bloquée avant exécution, sans résultat simulé présenté comme réel."]
methods=json.loads((ROOT/'logs/native-creation-methods.json').read_text(encoding='utf-8'))
lines += ['', '## Complément : méthodes métier et raisons sociales', '',
          'À la demande de l’utilisateur, les libellés fictifs sont FOURNISSEUR TEST IA et CLIENT TEST IA. Cette délégation ne constitue aucune autorisation d’écriture.', '',
          f"Sondes de méthodes exécutées le {methods['checked_at']} : uniquement métadonnées et getDescription, aucune écriture.", '',
          '| Méthode | Constat réel | Condition manquante |',
          '|---|---|---|',
          '| SOAP save | Trois publications ITM, ITF, BPS décrites | Transport vérifié, compte technique, preuves métier et accords distincts |',
          '| Import métier natif | Modèles BPC, BPS, ITM et ITMA trouvés dans TEST.AOBJEXT | Revue des lignes, obligations, droits et mode création seule |',
          '| Import automatisé AOWSIMPORT | getDescription : statut 0, Service web inexistant | Canal autorisé non disponible ; aucune invocation run effectuée |',
          '| REST | Catalogue HTTP 400 ; prototypes ITM et BPC HTTP 500 | Capacité d’écriture non établie ; aucun POST essayé |', '',
          'Les modèles BPC/BPS/ITM/ITMA sont rattachés aux objets métier. OPTUPD_0=2 impose une revue du risque de mise à jour avant tout usage ; aucun fichier import exécutable n’est généré. Les indicateurs de lignes ne suffisent pas à certifier toutes les obligations conditionnelles. Aucun modèle objet ITF trouvé dans la sélection examinée.', '',
          'La documentation distingue les imports objet, qui exécutent les contrôles métier, des imports de tables : [modèles d’import](https://online-help.sagex3.com/erp/12/en-us/Content/FCT/GESAOE.htm). Le canal SOAP d’import exige son service publié : [AOWSIMPORT](https://online-help.sagex3.com/erp/12/en-us/Content/V7DEV/api-guide_api-soap-import-export.html). Son existence dans la documentation ne prouve pas sa disponibilité ici.', '',
          'Plan et quatre fiches d’accord séparées : [ETAPE-4-METHODES-CREATION-ET-ACCORDS.md](../docs/ETAPE-4-METHODES-CREATION-ET-ACCORDS.md). Ces fiches sont des préparations, sans approbation enregistrée. Toute adaptation serveur ou publication nécessite une autorisation technique préalable.', '',
          'Preuve complémentaire : native-creation-methods.json ; script probe_native_creation_methods.py. Les 144 tests cités plus haut concernent la dernière régression du code applicatif ; ils ne constituent pas des créations réelles ni une nouvelle exécution dans ce complément.']
lines=[line.replace('| Bloqué |','| BLOQUÉ |') for line in lines]
(ROOT/'logs/TEST-CREATION-SAGE-X3.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Report created: logs/TEST-CREATION-SAGE-X3.md; real creations=0.')
