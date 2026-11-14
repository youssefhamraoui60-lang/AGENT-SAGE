"""Prepare review documents from existing evidence; no API/Sage calls or approvals."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
live=json.loads((ROOT/'logs/step4-crud-live-tests.json').read_text(encoding='utf-8'))
lines=['# Six demandes d’approbation distinctes — aucune accordée', '',
       'Ces fiches sont des documents de revue, pas des approbations enregistrées. **Ne pas approuver maintenant** : transport, compte et droits restent à valider. Les UUID ci-dessous identifient les brouillons historiques ; après changement de connexion, identité ou règles, refaire une préparation et confirmer son nouvel UUID/digest.', '',
       'Prérequis et risques des changements techniques : [plan d’actions](ETAPE-4-ACTIONS-AVANT-ECRITURE.md). Les opérations seront exécutées exclusivement par FastAPI, jamais par un envoi direct de ces XML. Le XML ci-dessous est le contenu objet, pas une enveloppe contenant des identifiants.', '',
       'L’approbation spécifique future porte sur UUID, empreinte, cible TEST, valeurs et état avant relu ; durée maximale 15 minutes, consommation unique côté serveur. Aucun accord technique ou texte général ne vaut pour les six opérations.']
for action in ['create','update']:
    for resource,r in live['resources'].items():
        obj={'articles':'ITM','suppliers':'BPS','article-sites':'ITF'}[resource]
        op=r[action+'_preparation']['operation'];request=r[action+'_preparation']['request']
        tag=('C-' if action=='create' else 'M-')+obj
        endpoint='/api/v1/sage/'+resource
        if action=='update':endpoint+='/'+'/'.join(request['keys'].values())
        lines += ['',f"## {tag} — {'Création' if action=='create' else 'Modification'} {obj}", '',
                  f"Cible : **V12 / TEST**, publication **{r['publication']}**, clés `{json.dumps(request['keys'],ensure_ascii=False)}`.",
                  f"Exécution future : `{'POST' if action=='create' else 'PATCH'} {endpoint}` ; une seule tentative SOAP `{'save' if action=='create' else 'modify'}`.",
                  f"Brouillon historique : `{op['id']}` ; état `{op['status']}` ; SHA256 `{op['digest']}`."]
        if action=='create':
            lines += ['', 'Avant constaté : fiche absente (SOAP read 0, « Fiche inexistante »). À revérifier juste avant exécution.']
        else:
            lines += ['', '**Avant réel indisponible : fiche absente. Ce brouillon est bloqué et ne peut pas être approuvé.** Après création, lire la fiche, préparer à nouveau et afficher chaque valeur avant/après. Les valeurs suivantes sont des intentions de modification, pas un diff déjà validé.']
        lines += ['', '| Champ | Valeur proposée |', '|---|---|']
        for f in request['fields']:lines.append(f"| {f['group']}.{f['name']} | {json.dumps(f['value'],ensure_ascii=False)} |")
        if resource=='articles' and action=='create':
            lines += ['', 'Revue nécessaire : NEG et numérotation manuelle ; statut et stock/lots, unités SAC et coefficients, code comptable CPJ35. Ce dernier provient de l’appel manuel réussi communiqué par l’utilisateur ; sa réutilisation reste à valider pour cette nouvelle fiche. Ne pas recréer TSTAI2610174D94B4.']
        if resource=='suppliers':
            lines += ['', 'Revue nécessaire : catégorie/pays, numérotation et champs conditionnels (adresse, conditions, fiscalité). Les données société BPRS sont partagées avec le Tiers : contrôler aussi l’impact sur sa fiche. Aucun vrai fournisseur existant n’est ciblé.']
        if resource=='article-sites':
            lines += ['', 'Dépendance : article parent existant et relu, site 201 autorisé. Après création ITM, relire ITF : si la fiche a été créée automatiquement, annuler la demande C-ITF et ne pas envoyer save. Pour M-ITF, vérifier que la nouvelle classe ABC diffère de la classe réellement enregistrée ; sinon préparer un changement différent et le présenter à nouveau.']
        lines += ['', 'XML historique, **NON ENVOYÉ** :', '', '```xml',op['object_xml'].rstrip(),'```', '',
                  f"Demande à présenter après levée des prérequis : « Autorisez-vous **{tag} uniquement**, une tentative via FastAPI dans TEST, pour les clés ci-dessus, conformément au nouvel UUID/digest et aux valeurs finales relues ? »", '',
                  'Résultats attendus après accord : statut/messages SOAP, read exact, comparaison des champs, résultat React et historique PostgreSQL. Une réponse ambiguë interdit toute répétition automatique. Aucun effacement autorisé.']
(ROOT/'docs/ETAPE-4-DEMANDES-APPROBATION.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Prepared six separate review sheets. Approvals recorded: none. Sage calls: none.')
