# TESTAGENT004 : actions restantes

Aucun SAVE envoyé. Aucun certificat, droit ERP ou paramètre actif de déverrouillage
modifié. Le secret admin est déjà chargé par le processus FastAPI (preuve dans
logs/admin-loaded-readiness.json).

## Intervention PKI indispensable

Le backend exige une chaîne stricte et la révocation de toute la chaîne.
`SAGE_SOAP_CRL_BUNDLE` désigne
`C:/AGENT-SAGE-X3/certs/approved-production/crls.pem`, actuellement absent.
L'ancien bundle CA explicite ne doit pas être supposé correspondre au certificat
maintenant présenté par Syracuse. La copie publique précédemment vérifiée ne
contenait aucun CDP/OCSP utilisable ; Schannel échouait lui aussi sur la révocation.
Un succès HttpClient sans contrôle explicite de révocation ne résout pas ce point.

Faire intervenir le responsable PKI :

1. Pour la chaîne HTTPS réellement affectée à sage:8443, fournir les certificats
   publics complets et leurs empreintes authentifiées, ainsi que les CRL signées
   actuelles de chaque émetteur nécessaire (feuille et intermédiaires).
2. Si cette autorité ne publie aucune révocation exploitable, réémettre uniquement
   le certificat HTTPS de sage avec SAN DNS:sage, EKU serverAuth, SKI/AKI cohérents,
   sous une chaîne approuvée disposant de CDP/CRL opérationnels. Affectation à la
   ligne 8443 existante par l'exploitation, avec fenêtre et retour arrière si un
   rechargement Syracuse est nécessaire. Ne pas modifier les certificats internes.
3. Sur 208, installer uniquement les fichiers publics approuvés dans le répertoire
   prévu : ca-chain.pem et crls.pem. Aligner SAGE_SOAP_CA_BUNDLE sur ca-chain.pem et
   garder SAGE_SOAP_CRL_BUNDLE sur crls.pem. Vérifier signatures, fraîcheur, chaîne,
   nom et absence de révocation. Prévoir le renouvellement des CRL avant nextUpdate.
   Aucune clé privée sur 208, aucune CRL de laboratoire, aucun contournement TLS.
4. Redémarrer le backend pour charger la configuration, puis tester ses routes
   `/api/v1/sage/articles/schema`, `/api/v1/sage/articles/TESTSOAP003` et
   `/api/v1/sage/articles/TESTAGENT004`. Ne pas envoyer SAVE si la lecture échoue.

## Déverrouillage préparé, inactif

Le modèle `config/testagent004-policy.INACTIVE.json` n'est pas sélectionné dans
l'environnement et est volontairement expiré/non validé. Il ne donne aucun droit.
Le code accepte une exception admin temporaire uniquement pour V12/TEST,
POOL_AI_TEST, https://sage:8443 et la création de TESTAGENT004. La durée restante
maximale est de 24 heures. Toutes les autres permissions sont refusées.

Après les lectures SOAP réelles, compléter les preuves de droits, l'identité
effective du pool et le référentiel métier JSON attendu par sage_article_rules.py :
NEG, statut 1, unités UN/conversions, fiscalité et éventuelles associations.
Une valeur fiscale trouvée sur un exemple ne suffit pas à certifier son applicabilité.
Les preuves doivent porter leurs véritables SHA-256 ; ne pas cocher des attestations
non établies. Les empreintes de publication sont celles de getDescription réel.

L'activation de cette politique et du moteur d'écriture reste une action future,
après confirmation utilisateur. Le backend applique ensuite le périmètre exact lors
de l'approbation, de l'exécution et à l'entrée du transport, tout en conservant le
jeton humain expirant, sa consommation atomique et l'interdiction de retry SAVE.
Les routes de modification et de création fournisseur/article-site restent 423.
L'absence de TESTAGENT004 devra être revérifiée juste avant la création.
