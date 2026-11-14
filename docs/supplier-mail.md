Le canal e-mail traite les demandes fournisseurs Gmail avec les validations et la relecture SQL de l’interface, sans confirmation manuelle dans ce canal.

Le canal des fournisseurs par e-mail est activé dans **OB production depuis le 12 novembre 2026**. La valeur par défaut du logiciel reste TEST. La bascule contrôlée se fait avec `scripts/activate_supplier_mail.py --folder OB` : droits SQL vérifiés, arrêt du worker seulement lorsqu’aucune demande n’est en cours, point de départ Gmail enregistré, mise à jour du .env et redémarrage. Un objet OB/SOB ne choisit jamais le dossier Sage.

Paramètres dans `.env` : `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `IMAP_HOST=imap.gmail.com`, `IMAP_PORT=993`, `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SUPPLIER_MAIL_FOLDER=TEST`, `SUPPLIER_MAIL_OWNER_ID`, `SUPPLIER_MAIL_POLL_SECONDS=30`. Une réponse SMTP automatique annonce le résultat dans le fil de la demande.

Depuis la racine du projet :

```powershell
backend/.venv/Scripts/python.exe scripts/supplier_mail_worker.py --check
backend/.venv/Scripts/python.exe scripts/supplier_mail_worker.py --once --folder TEST
powershell -NoProfile -File scripts/start-supplier-mail.ps1
```

Les e-mails de l’INBOX sont examinés, qu’ils soient lus ou non lus. La recherche serveur limite les objets à OB/SOB, puis le filtre exact impose aussi un terme fournisseur ou FRS. Exemples : `Fournisseur OB`, `FRS OB`, `Fournisseur SOB`. Les autres modules sont ignorés. Le worker conserve le statut lu/non lu.

Les transferts Outlook sont nettoyés des signatures et en-têtes de routage. Une demande explicite de création suivie d’une ligne de fournisseur avec des champs séparés par `/`, `//` ou `:` est transmise à l’agent sous forme de champs libellés, en conservant les valeurs, notamment les zéros initiaux de l’ICE et du téléphone. Les demandes de modification et les négations restent soumises au moteur existant.

Le texte brut et HTML sont acceptés. Les pièces jointes restent bloquées pour vérification. Les champs pris en charge sont ceux des actions existantes : l’adresse e-mail du fournisseur n’est pas prise en charge dans la requête SQL de création. Les doublons, données incomplètes, champs non enregistrables ou dépendances métier bloquent l’écriture. Les paramètres par défaut du modèle Sage F103 restent applicables.

Le journal `runtime/supplier-mail.sqlite3` conserve la cible, la conversation, le statut et le résultat. La clé combine boîte mail, cible et Message-ID (ou empreinte du message sans Message-ID). L’enregistrement précède l’analyse ; une erreur ou une interruption ne déclenche jamais une nouvelle tentative automatique. Vérifier la conversation liée et les données Sage avant une reprise manuelle. Ne pas effacer le journal pour rejouer une demande. TEST et OB ont des clés distinctes.

Le processus masqué conserve son PID dans `runtime/supplier-mail.pid`, sa sortie dans `logs/supplier-mail.stdout.log` et ses erreurs dans `logs/supplier-mail.stderr.log`. Le lancement manuel ne configure pas de démarrage après redémarrage Windows.

`scripts/test_supplier_mail_live.py` est un test synthétique distinct : il crée une fiche TEST MAIL dans TEST et modifie son téléphone. Son rapport se trouve dans `TEST/supplier-mail-live-results.json`. Les résultats des vrais e-mails figurent dans le journal du canal et les conversations liées.

Les réponses automatiques utilisent SMTP avec TLS (port 587 STARTTLS ou 465 TLS direct). Elles indiquent le dossier TEST/OB, les codes créés ou modifiés et vérifiés, le code existant en cas de doublon, ou l’action attendue en cas de blocage. Un résultat ambigu est explicitement signalé et n’est pas présenté comme une réussite.

Les réponses utilisent Répondre à tous : expéditeur (ou Reply-To), destinataires À et Cc du message reçu, sans doublons et en excluant la boîte du service. Les adresses citées dans un transfert ne sont pas ajoutées. Les Cci ne sont incluses que si un en-tête Bcc est effectivement disponible ; elles restent dans l’enveloppe SMTP et sont retirées des en-têtes transmis aux destinataires. Les Cci masquées par le serveur expéditeur ne peuvent pas être retrouvées. Les en-têtes In-Reply-To/References conservent le fil et les messages automatiques sont exclus pour éviter les boucles.

La table `replies` du journal conserve un envoi par demande et par cible. Les demandes déjà traitées, dont le doublon AUTOR AUTO, reçoivent aussi leur résultat lors du prochain passage, sans rejouer les actions Sage. Une tentative SMTP est enregistrée avant l’envoi : un envoi interrompu reste à vérifier et n’est pas réémis automatiquement. Le statut `sent` signifie que le serveur SMTP a accepté l’envoi ; il ne garantit pas la remise finale au destinataire.

Les confirmations de réussite commencent par Bonjour, indiquent la création ou la modification dans TEST/OB, puis affichent séparément Code fournisseur, Nom du fournisseur et ICE. Les valeurs proviennent de la relecture vérifiée ; un ICE absent est noté Non renseigné. La signature est Cordialement, Équipe SI. Le journal conserve les destinataires À/Cc/Cci et ne renvoie pas les réponses déjà expédiées.

La table `activations` conserve, par cible, la boîte, UIDVALIDITY et le premier UID admis. Une activation OB traite les nouveaux e-mails seulement : les messages déjà présents, notamment ceux créés dans TEST, ne sont pas rejoués. Une nouvelle invocation de la même activation conserve ce point de départ. Si la boîte ou UIDVALIDITY change, le traitement s’arrête pour vérification plutôt que de reprendre l’historique. Les demandes en cours empêchent la bascule.
