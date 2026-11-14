# Confirmation fournisseur dans le chat — 27 octobre 2026

La question fournisseur était produite depuis les propositions SQL et pending,
mais le parseur déterministe ne confirmait que awaiting_confirmation, utilisé pour
les catégories. Le code fournisseur proposé par le modèle était ensuite écarté par
la protection des références critiques. Résultat : « OUI LE F1025 » ne modifiait pas
code_fournisseur et la question restait en attente. Les questions déjà affichées
étaient masquées dans les réponses suivantes, donnant une boucle de récapitulatifs.

Correction : une réponse affirmative à une proposition fournisseur unique en attente
est reconnue sans dépendre d'une extraction du modèle. Le code nommé doit correspondre
à la proposition ; aucune valeur inventée, ambiguë ou issue d'une question n'est
acceptée. Les autres champs restent inchangés. Une confirmation de fournisseur
n'approuve pas une création ERP. La question non résolue demeure visible et la suite
du parcours est indiquée explicitement.

Le parcours d'écriture PowerShell reste limité aux codes TEST, catégorie NEG, unités
UN et site 201 explicite, sans association fournisseur ni réglage de stock explicite.
Ces limites sont maintenant affichées dans le récapitulatif et la carte du brouillon,
y compris pour une conversation déjà persistée. Le bouton de préparation est bloqué
pour ces cas. Le code EXT_POUDRE, le fournisseur et « Non géré » sont conservés,
jamais effacés pour contourner ces restrictions. Leur prise en charge nécessite une
extension distincte du mapping, pas davantage de confirmations « oui ».

Validation : 77 tests réussis, dont confirmations simples/nommées, refus d'un code
différent, ambiguïtés, conservation des champs, absence de SAVE et limites d'écriture.
Rapport : logs/supplier-confirmation-fix-tests.xml. Frontend reconstruit, backend
redémarré ; aucune nouvelle donnée Sage créée.
