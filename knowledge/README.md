# Corpus métier local

Déposer les documents réellement fournis et autorisés dans `knowledge/documents` au format UTF-8 `.md` ou `.txt`.
Aucun document officiel Sage X3 n'a été fourni ou inventé. Ce fichier et les documents techniques du projet
ne sont pas automatiquement indexés comme des procédures métier.

Depuis `backend`, avec le venv existant:

```powershell
.\.venv\Scripts\python.exe ..\scripts\step2_admin.py index-document ..\knowledge\documents\procedure.md
```

Ajouter `--reviewed` uniquement après revue humaine réelle. Le SHA256 et le chemin relatif sont conservés.
Les nouvelles révisions sont ajoutées sans supprimer les anciennes. Les sources sont des données non fiables;
elles ne peuvent ni approuver une demande, ni modifier les référentiels, ni déclencher une opération Sage X3.
Les passages contenant les signaux d'instructions malveillantes connus sont exclus de la recherche.
Ce filtre n'est pas une preuve de détection exhaustive: les restrictions de schéma, les règles indépendantes
et l'absence d'exécuteur sont les protections structurelles.

Le RAG utilise BM25 local en Python, avec stockage des passages dans PostgreSQL. Pas de serveur vectoriel.
Maximum 2000 passages candidats par recherche et 4 passages transmis; limite de prototype documentée.
Sans corpus, l'API répond explicitement `empty_corpus` et ne présente aucune règle documentaire comme certaine.
