# Instructions Bendango

## Documentation vivante obligatoire

Avant toute modification du code, des dépendances, des migrations, de la
configuration, des templates ou du déploiement, lire les six documents :

- `doc_ia/PROD.md` : périmètre produit et état de préparation à la production.
- `doc_ia/ARCHITECTURE.md` : composants, données et flux.
- `doc_ia/RULES.md` : règles de développement et de vérification.
- `doc_ia/DESIGN.md` : interface et comportements visibles.
- `doc_ia/TASKS.md` : travaux, priorités et critères de validation.
- `doc_ia/MEMORY.md` : décisions, interventions et preuves de validation.

À chaque évolution, réexaminer les six documents et mettre à jour les informations
affectées dans le même lot de changements. Mettre systématiquement à jour TASKS.md
et MEMORY.md avec le résultat, les vérifications et les limites. Un document sans
impact fonctionnel ne doit pas recevoir de changement artificiel ; noter dans
MEMORY.md que les autres documents ont été consultés et restent cohérents.
Actualiser la date des documents réellement modifiés. Ne pas déclarer une tâche
terminée avant cette réconciliation documentaire.

Le code et les résultats observés font foi pour l'état actuel ; les instructions
explicites de l'utilisateur font foi pour le travail demandé. Si les documents
divergent, signaler la divergence et corriger les descriptions sans inventer de
fonctionnalité. Distinguer état actuel, proposition, réalisation et validation.

Préserver `TASKMEMORY.md` et `readme.md` comme références existantes. La mémoire
active est désormais `doc_ia/MEMORY.md` ; ne pas recopier l'historique entier.
Ne jamais enregistrer de secrets, identifiants, données personnelles ou contenu
de `.env` dans ces documents. Respecter les modifications locales existantes.

## Commandes locales

L'environnement est sélectionné par `.python-version` (`bendango`). Si pyenv
n'est pas chargé, utiliser `.venv/bin/python` explicitement.

- Contrôles : `.venv/bin/python manage.py check`
- Tests : `.venv/bin/python manage.py test --noinput`
- Cohérence des migrations : `.venv/bin/python manage.py makemigrations --check --dry-run`
- Installation : `.venv/bin/python -m pip install -r requirements.txt`

## Livraison Git autorisée par l'utilisateur

Instruction du 2026-10-09 : effectuer un commit et un push après chaque lot de
modifications validé. Inclure les mises à jour doc_ia dans le même commit.
Vérifier le diff, les contrôles adaptés et la branche distante avant publication.
Préserver la branche de travail existante ; ne jamais forcer un push ni inclure
les secrets, données locales ou fichiers de runtime. En cas de rejet du push,
rapporter le blocage et conserver le commit local. Un déploiement reste distinct.
