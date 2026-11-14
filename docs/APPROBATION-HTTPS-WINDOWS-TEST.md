# Politique HTTPS TEST — proposition approuvée et appliquée le 27 octobre 2026

L'utilisateur a explicitement approuvé la proposition ci-dessous, puis autorisé une
unique création de TESTAGENT004. Modification appliquée au seul module PowerShell.
Résultat réel : SAVE=1, READ=1 ; voir logs/TESTAGENT004-authorized-powershell-result.json.
Les sections suivantes conservent le détail de la proposition initiale.

## Comparaison établie

`scripts/SageTestSoap.psm1` crée un HttpClientHandler Windows, refuse un callback
global personnalisé, interdit les redirections et impose explicitement :

```powershell
$handler.CheckCertificateRevocationList=$true
```

Le défaut du HttpClientHandler .NET de cet environnement a été relevé à False,
sans requête réseau. Le script local `test_admin_testsoap003.ps1` impose lui aussi
True : ce fichier ne permet donc pas d'identifier le réglage exact du PowerShell
interactif dont le succès a été rapporté. Le script exact de cette réussite reste
absent des éléments retrouvés ; aucune équivalence complète n'est attestée.

## Modification précise proposée, soumise à approbation

Dans SageTestSoap.psm1, retirer uniquement l'affectation explicite à True et
conserver le comportement par défaut de HttpClientHandler Windows. Documenter
et retourner la valeur effective dans les rapports au lieu de déclarer
systématiquement `WindowsRevocationRequired=True`. Adapter également le script
read_powershell_soap.ps1 pour rapporter la politique réellement utilisée.

Différence : la révocation ne sera plus exigée explicitement par ce client.
L'absence d'erreur TLS ne prouvera pas que le certificat n'est pas révoqué.
Le magasin de confiance Windows, la validation de la chaîne, des dates et du nom
du serveur restent appliqués. Aucun callback permissif, certificat accepté
arbitrairement, repli HTTP ou réglage TLS global ne sera introduit.

Périmètre : seul ce module autonome, destination figée https://sage:8443,
WS_ARTICLE, POOL_AI_TEST, cible métier confirmée V12/TEST par getDescription.
Les autres clients et leur politique de révocation ne changent pas.
L'approbation porte sur cette différence de sécurité, pas sur une création ERP.

## Après approbation seulement

1. Appliquer cette modification locale et les rapports correspondants.
2. Exécuter getDescription puis SOAP READ de TESTSOAP003 ; conserver statut et
   messages réels, sans revendiquer un résultat avant leur réception.
3. Préparer un nouvel article, contrôler son absence et présenter le XML/digest.
4. Attendre une autorisation spécifique pour cet article avant toute création.
   Conserver la confirmation humaine, le marqueur permanent, SAVE unique et READ.

État final : politique approuvée appliquée ; création unique autorisée exécutée et
relue. FastAPI n'a pas été utilisé ; ses écritures générales restent verrouillées.
