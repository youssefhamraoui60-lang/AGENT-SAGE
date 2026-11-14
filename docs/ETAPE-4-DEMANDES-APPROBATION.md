# Six demandes d’approbation distinctes — aucune accordée

Ces fiches sont des documents de revue, pas des approbations enregistrées. **Ne pas approuver maintenant** : transport, compte et droits restent à valider. Les UUID ci-dessous identifient les brouillons historiques ; après changement de connexion, identité ou règles, refaire une préparation et confirmer son nouvel UUID/digest.

Prérequis et risques des changements techniques : [plan d’actions](ETAPE-4-ACTIONS-AVANT-ECRITURE.md). Les opérations seront exécutées exclusivement par FastAPI, jamais par un envoi direct de ces XML. Le XML ci-dessous est le contenu objet, pas une enveloppe contenant des identifiants.

L’approbation spécifique future porte sur UUID, empreinte, cible TEST, valeurs et état avant relu ; durée maximale 15 minutes, consommation unique côté serveur. Aucun accord technique ou texte général ne vaut pour les six opérations.

## C-ITM — Création ITM

Cible : **V12 / TEST**, publication **WS_ARTICLE**, clés `{"ITMREF": "TAI261017948E"}`.
Exécution future : `POST /api/v1/sage/articles` ; une seule tentative SOAP `save`.
Brouillon historique : `5b73b1eb-a8b1-4461-a729-db47568ba1d8` ; état `prepared` ; SHA256 `e9bd5d63909972358dc6ae0e32441269ecb94319f5371eabc4448bede753e085`.

Avant constaté : fiche absente (SOAP read 0, « Fiche inexistante »). À revérifier juste avant exécution.

| Champ | Valeur proposée |
|---|---|
| ITM0_1.TCLCOD | "NEG" |
| ITM0_1.DES1AXX | "TEST API ITM - AUCUN ENVOI" |
| ITM0_1.ITMSTA | "1" |
| ITM2_1.STOMGTCOD | "2" |
| ITM2_3.LOTMGTCOD | "3" |
| ITM3_1.STU | "SAC" |
| ITM3_1.PUU | "SAC" |
| ITM3_1.PUUSTUCOE | "1" |
| ITM3_1.SAU | "SAC" |
| ITM3_1.SAUSTUCOE | "1" |
| ITM5_1.ACCCOD | "CPJ35" |

Revue nécessaire : NEG et numérotation manuelle ; statut et stock/lots, unités SAC et coefficients, code comptable CPJ35. Ce dernier provient de l’appel manuel réussi communiqué par l’utilisateur ; sa réutilisation reste à valider pour cette nouvelle fiche. Ne pas recréer TSTAI2610174D94B4.

XML historique, **NON ENVOYÉ** :

```xml
<PARAM>
  <GRP ID="ITM0_1">
    <FLD NAME="ITMREF">TAI261017948E</FLD>
    <FLD NAME="TCLCOD">NEG</FLD>
    <FLD NAME="DES1AXX">TEST API ITM - AUCUN ENVOI</FLD>
    <FLD NAME="ITMSTA">1</FLD>
  </GRP>
  <GRP ID="ITM2_1">
    <FLD NAME="STOMGTCOD">2</FLD>
  </GRP>
  <GRP ID="ITM2_3">
    <FLD NAME="LOTMGTCOD">3</FLD>
  </GRP>
  <GRP ID="ITM3_1">
    <FLD NAME="STU">SAC</FLD>
    <FLD NAME="PUU">SAC</FLD>
    <FLD NAME="PUUSTUCOE">1</FLD>
    <FLD NAME="SAU">SAC</FLD>
    <FLD NAME="SAUSTUCOE">1</FLD>
  </GRP>
  <GRP ID="ITM5_1">
    <FLD NAME="ACCCOD">CPJ35</FLD>
  </GRP>
</PARAM>
```

Demande à présenter après levée des prérequis : « Autorisez-vous **C-ITM uniquement**, une tentative via FastAPI dans TEST, pour les clés ci-dessus, conformément au nouvel UUID/digest et aux valeurs finales relues ? »

Résultats attendus après accord : statut/messages SOAP, read exact, comparaison des champs, résultat React et historique PostgreSQL. Une réponse ambiguë interdit toute répétition automatique. Aucun effacement autorisé.

## C-BPS — Création BPS

Cible : **V12 / TEST**, publication **WS_FOURNIS**, clés `{"BPSNUM": "TB261017948E"}`.
Exécution future : `POST /api/v1/sage/suppliers` ; une seule tentative SOAP `save`.
Brouillon historique : `3625fa48-530e-47e9-91ba-7bd76fbf7e2b` ; état `prepared` ; SHA256 `2aa8a15d9262c359cca448dfb90fb85845a1cc8c8b305b8ce2622d33efdcf331`.

Avant constaté : fiche absente (SOAP read 0, « Fiche inexistante »). À revérifier juste avant exécution.

| Champ | Valeur proposée |
|---|---|
| BPRS_1.BPRNAM | ["FOURNISSEUR FICTIF TEST API", ""] |
| BPRS_1.BPRSHO | "TESTAPI" |
| BPS0_1.BSGCOD | "FR" |
| BPRS_1.CRY | "MA" |

Revue nécessaire : catégorie/pays, numérotation et champs conditionnels (adresse, conditions, fiscalité). Les données société BPRS sont partagées avec le Tiers : contrôler aussi l’impact sur sa fiche. Aucun vrai fournisseur existant n’est ciblé.

XML historique, **NON ENVOYÉ** :

```xml
<PARAM>
  <GRP ID="BPS0_1">
    <FLD NAME="BPSNUM">TB261017948E</FLD>
    <FLD NAME="BSGCOD">FR</FLD>
  </GRP>
  <GRP ID="BPRS_1">
    <LST NAME="BPRNAM" SIZE="2">
      <ITM>FOURNISSEUR FICTIF TEST API</ITM>
      <ITM></ITM>
    </LST>
    <FLD NAME="BPRSHO">TESTAPI</FLD>
    <FLD NAME="CRY">MA</FLD>
  </GRP>
</PARAM>
```

Demande à présenter après levée des prérequis : « Autorisez-vous **C-BPS uniquement**, une tentative via FastAPI dans TEST, pour les clés ci-dessus, conformément au nouvel UUID/digest et aux valeurs finales relues ? »

Résultats attendus après accord : statut/messages SOAP, read exact, comparaison des champs, résultat React et historique PostgreSQL. Une réponse ambiguë interdit toute répétition automatique. Aucun effacement autorisé.

## C-ITF — Création ITF

Cible : **V12 / TEST**, publication **WS_AR_SITE**, clés `{"ITMREF": "TAI261017948E", "STOFCY": "201"}`.
Exécution future : `POST /api/v1/sage/article-sites` ; une seule tentative SOAP `save`.
Brouillon historique : `4eee956e-88d0-4043-88f7-f1a65d14bb06` ; état `blocked` ; SHA256 `045c8034f7c95f528ff552e6c6f18894ca2ff545817445353cf52324b6edca42`.

Avant constaté : fiche absente (SOAP read 0, « Fiche inexistante »). À revérifier juste avant exécution.

| Champ | Valeur proposée |
|---|---|
| ITF1_2.ABCCLS | "1" |

Dépendance : article parent existant et relu, site 201 autorisé. Après création ITM, relire ITF : si la fiche a été créée automatiquement, annuler la demande C-ITF et ne pas envoyer save. Pour M-ITF, vérifier que la nouvelle classe ABC diffère de la classe réellement enregistrée ; sinon préparer un changement différent et le présenter à nouveau.

XML historique, **NON ENVOYÉ** :

```xml
<PARAM>
  <GRP ID="ITF0_1">
    <FLD NAME="ITMREF">TAI261017948E</FLD>
    <FLD NAME="STOFCY">201</FLD>
  </GRP>
  <GRP ID="ITF1_2">
    <FLD NAME="ABCCLS">1</FLD>
  </GRP>
</PARAM>
```

Demande à présenter après levée des prérequis : « Autorisez-vous **C-ITF uniquement**, une tentative via FastAPI dans TEST, pour les clés ci-dessus, conformément au nouvel UUID/digest et aux valeurs finales relues ? »

Résultats attendus après accord : statut/messages SOAP, read exact, comparaison des champs, résultat React et historique PostgreSQL. Une réponse ambiguë interdit toute répétition automatique. Aucun effacement autorisé.

## M-ITM — Modification ITM

Cible : **V12 / TEST**, publication **WS_ARTICLE**, clés `{"ITMREF": "TAI261017948E"}`.
Exécution future : `PATCH /api/v1/sage/articles/TAI261017948E` ; une seule tentative SOAP `modify`.
Brouillon historique : `96a98f8b-58e8-4508-a959-6ddbdd965e64` ; état `blocked` ; SHA256 `7f3b99d140097dfaacc005458eb869bfcb667bd360694268e27ad6749371951f`.

**Avant réel indisponible : fiche absente. Ce brouillon est bloqué et ne peut pas être approuvé.** Après création, lire la fiche, préparer à nouveau et afficher chaque valeur avant/après. Les valeurs suivantes sont des intentions de modification, pas un diff déjà validé.

| Champ | Valeur proposée |
|---|---|
| ITM0_1.DES1AXX | "TEST API ITM - MODIFICATION" |

XML historique, **NON ENVOYÉ** :

```xml
<PARAM>
  <GRP ID="ITM0_1">
    <FLD NAME="ITMREF">TAI261017948E</FLD>
    <FLD NAME="DES1AXX">TEST API ITM - MODIFICATION</FLD>
  </GRP>
</PARAM>
```

Demande à présenter après levée des prérequis : « Autorisez-vous **M-ITM uniquement**, une tentative via FastAPI dans TEST, pour les clés ci-dessus, conformément au nouvel UUID/digest et aux valeurs finales relues ? »

Résultats attendus après accord : statut/messages SOAP, read exact, comparaison des champs, résultat React et historique PostgreSQL. Une réponse ambiguë interdit toute répétition automatique. Aucun effacement autorisé.

## M-BPS — Modification BPS

Cible : **V12 / TEST**, publication **WS_FOURNIS**, clés `{"BPSNUM": "TB261017948E"}`.
Exécution future : `PATCH /api/v1/sage/suppliers/TB261017948E` ; une seule tentative SOAP `modify`.
Brouillon historique : `14d59298-8ece-447a-b01d-61259f2f97a0` ; état `blocked` ; SHA256 `2a101b65fe33444f989e98f4fd8bcd410237ec5ad6a5cc995012697ab778a3be`.

**Avant réel indisponible : fiche absente. Ce brouillon est bloqué et ne peut pas être approuvé.** Après création, lire la fiche, préparer à nouveau et afficher chaque valeur avant/après. Les valeurs suivantes sont des intentions de modification, pas un diff déjà validé.

| Champ | Valeur proposée |
|---|---|
| BPRS_1.BPRSHO | "TSTAPIMOD" |

Revue nécessaire : catégorie/pays, numérotation et champs conditionnels (adresse, conditions, fiscalité). Les données société BPRS sont partagées avec le Tiers : contrôler aussi l’impact sur sa fiche. Aucun vrai fournisseur existant n’est ciblé.

XML historique, **NON ENVOYÉ** :

```xml
<PARAM>
  <GRP ID="BPS0_1">
    <FLD NAME="BPSNUM">TB261017948E</FLD>
  </GRP>
  <GRP ID="BPRS_1">
    <FLD NAME="BPRSHO">TSTAPIMOD</FLD>
  </GRP>
</PARAM>
```

Demande à présenter après levée des prérequis : « Autorisez-vous **M-BPS uniquement**, une tentative via FastAPI dans TEST, pour les clés ci-dessus, conformément au nouvel UUID/digest et aux valeurs finales relues ? »

Résultats attendus après accord : statut/messages SOAP, read exact, comparaison des champs, résultat React et historique PostgreSQL. Une réponse ambiguë interdit toute répétition automatique. Aucun effacement autorisé.

## M-ITF — Modification ITF

Cible : **V12 / TEST**, publication **WS_AR_SITE**, clés `{"ITMREF": "TAI261017948E", "STOFCY": "201"}`.
Exécution future : `PATCH /api/v1/sage/article-sites/TAI261017948E/201` ; une seule tentative SOAP `modify`.
Brouillon historique : `a9140cf4-e3e1-4dad-b699-fb3a0764415b` ; état `blocked` ; SHA256 `5f12c547204a1ea2efe1cbf4beed1b5bcb78a5620967c5c78659f81916d20afb`.

**Avant réel indisponible : fiche absente. Ce brouillon est bloqué et ne peut pas être approuvé.** Après création, lire la fiche, préparer à nouveau et afficher chaque valeur avant/après. Les valeurs suivantes sont des intentions de modification, pas un diff déjà validé.

| Champ | Valeur proposée |
|---|---|
| ITF1_2.ABCCLS | "2" |

Dépendance : article parent existant et relu, site 201 autorisé. Après création ITM, relire ITF : si la fiche a été créée automatiquement, annuler la demande C-ITF et ne pas envoyer save. Pour M-ITF, vérifier que la nouvelle classe ABC diffère de la classe réellement enregistrée ; sinon préparer un changement différent et le présenter à nouveau.

XML historique, **NON ENVOYÉ** :

```xml
<PARAM>
  <GRP ID="ITF0_1">
    <FLD NAME="ITMREF">TAI261017948E</FLD>
    <FLD NAME="STOFCY">201</FLD>
  </GRP>
  <GRP ID="ITF1_2">
    <FLD NAME="ABCCLS">2</FLD>
  </GRP>
</PARAM>
```

Demande à présenter après levée des prérequis : « Autorisez-vous **M-ITF uniquement**, une tentative via FastAPI dans TEST, pour les clés ci-dessus, conformément au nouvel UUID/digest et aux valeurs finales relues ? »

Résultats attendus après accord : statut/messages SOAP, read exact, comparaison des champs, résultat React et historique PostgreSQL. Une réponse ambiguë interdit toute répétition automatique. Aucun effacement autorisé.
