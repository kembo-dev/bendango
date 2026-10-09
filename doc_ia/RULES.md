# Règles de développement Bendango

Dernière mise à jour : 2026-10-09.

## Documentation et changements

1. Lire les six fichiers de `doc_ia` avant de modifier le projet.
2. Conserver les modifications locales et les données ; sauvegarder avant toute
   migration ou remplacement risquant de les affecter.
3. Réaliser un changement ciblé, cohérent avec les modules existants.
4. Vérifier le comportement modifié ; ajouter des tests utiles pour les bugs,
   frontières d'accès, migrations et traitements sensibles.
5. Réexaminer les six documents. Mettre à jour ceux affectés, TASKS.md et MEMORY.md
   dans le même lot ; noter explicitement les documents restés cohérents.
6. Après validation et réconciliation documentaire, effectuer un commit et un
   push sur la branche de travail (instruction utilisateur du 2026-10-09). Ne pas
   forcer le push ; conserver le commit et signaler tout rejet.
7. Rapporter résultat, preuves, limites et travail restant. Ne pas confondre
   installation d'une dépendance et intégration d'une fonctionnalité.

## Conventions

- Python et Django ; modules et fonctions en `snake_case`, classes en `PascalCase`.
- Modèles dans `tracker/models.py`, évolutions du schéma par migrations.
- Logique métier dans les modules de service ; éviter d'alourdir `views.py`.
- Tests existants : `tracker/tests.py` et `tracker/test_*.py`, via Django.
- Les migrations déjà appliquées ne doivent pas être réécrites sans justification
  et stratégie explicite de compatibilité.
- Les dépendances importées obligatoirement doivent figurer dans le manifeste
  principal `requirements.txt`. Le fichier historique `requirement.txt` n'est
  pas la référence principale d'installation.

## Données, accès et sécurité

- Filtrer les opérations Pro par propriétaire ; conserver les protections CSRF.
- Ne jamais mettre secrets, mots de passe, tokens ou contenu de `.env` dans Git,
  les documents, les captures ou les sorties de commande.
- Objectif de correction : valider les destinations HTTP et les redirections,
  en rejetant les réseaux privés, locaux et réservés ; cette protection manque actuellement.
- Objectif de correction : valider le contenu réel des images ; le nom et le
  type MIME déclaré ne suffisent pas dans le code actuel.
- Garder distincts prix, devise, fiabilité, pertinence et statut de vérification.
- Ne pas présenter une source sociale comme une offre vérifiée.
- Ne pas déclencher de vrais appels LLM payants pour des tests unitaires ; réserver
  les tests d'intégration explicitement autorisés à une validation séparée.

## Configuration LLM

- Conserver les secrets dans `.env` ou l'environnement ; seuls leurs noms `*_env`
  vont dans TOML. Le fichier `config/llm.local.toml` est ignoré par Git ; pour un
  chemin `LLM_CONFIG_FILE` personnalisé, ignorer aussi sa surcharge privée.
- Préserver les références `profil::modèle` des travaux en file. Ne pas supprimer
  ou changer le fournisseur d'un profil tant que ces travaux en dépendent.
- Toute évolution du chargeur ou des adaptateurs doit vérifier le rechargement,
  la priorité des réglages, la sélection des tâches, la validation et la non
  divulgation de clés. Utiliser des réponses HTTP/SDK simulées.
- Sans configuration LLM, préserver la recherche en mode auto et les extractions
  locales. `disabled` interdit tout appel ; `required` doit échouer de manière
  contrôlée. Une tâche mémorisée sans LLM doit rester sans LLM.
- Le secours distant exige `allow_paid_fallback=true` et un profil explicite.
  Vérifier timeout, configuration absente, absence de clé, prix non inventés,
  repli local autorisé et repli payant refusé avec des adaptateurs simulés.
- Ne pas déclencher de repli implicite vers une API payante. Contrôler la présence
  de la clé avec `manage.py llm_config --check` avant une bascule.

## Invariants métier à préserver

- Une recherche en échec doit rester un échec dans le contrat API et l'interface,
  même si elle possède une date de fin ; incohérence existante à corriger.
- Distinguer une recherche terminée, une couverture atteinte et une offre trouvée.
- Maintenir la séparation des variantes incompatibles lors du regroupement canonique.
- Ne jamais calculer un prix minimum ou une économie entre montants bruts de devises
  différentes. Les taux actuels sont des constantes configurables, pas des cours réels.
- Préserver la différence entre offre recommandée et offre la moins chère.
- La confiance automatique n'accorde pas le statut `verified` aux marchands.
- Un boost actif exige approbation et fenêtre de dates valide ; pas de boost
  pour les services dans le parcours existant. Les demandes en attente ou actives
  sont bloquées par la vue pour éviter un doublon de parcours.
- Les tâches de file doivent tolérer concurrence, reprise et arrêt ; ne pas
  remplacer les workers par Celery sans traiter les tâches déjà persistées.
- Lors d'une modification de `PriceListing`, préserver la validation et
  l'historique de `save()` ; tout contournement par `update()` doit être explicite.

## Validation par domaine

| Changement | Vérifications ciblées existantes |
| --- | --- |
| Comptes et approbation Pro | `tracker.test_accounts`, `tracker.test_pro_catalog` |
| Offres, médias et boosts | `tracker.test_offers`, `tracker.test_offer_media`, `tracker.test_offer_boosts` |
| Accueil et confidentialité | `tracker.test_home_discovery`, `tracker.test_recent_search_history` |
| Recherche unifiée et filtres | `tracker.test_unified_search`, `tracker.test_markets` |
| Profils et adaptateurs LLM | `tracker.test_llm_config`, `tracker.test_llm_policy` |
| File et finalisation | `tracker.test_job_queue`, `tracker.test_search_run_finalization`, `tracker.test_job_queue_priority` |
| Extraction et devises | `tracker.test_local_first_extraction`, `tracker.test_currency_safety`, `tracker.test_reliable_collection` |

Le test Bedrock est opt-in via `RUN_BEDROCK_INTEGRATION_TESTS` ; ne pas activer ce
réglage pour une simple vérification documentaire. Les tests existants ne couvrent
pas automatiquement les nouveaux défauts identifiés : ajouter les régressions nécessaires.

## Changement de moteur de base

Sauvegarder la base et la configuration avant la bascule. Valider connexion et
migrations sur la cible avant de modifier `.env`. Redémarrer web et workers après
la bascule pour éviter des écritures sur deux bases. Ne pas accorder superutilisateur
au rôle applicatif. Distinguer création d'une base neuve et migration des données.

## Commandes

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test --noinput
.venv/bin/python -m pip check
```

Exécuter les tests ciblés pendant le développement et la suite adaptée avant
livraison. Avant production, contrôler `check --deploy` avec la configuration
de production réelle ; documenter les erreurs restantes sans masquer les contrôles.
Les tests réussis ne prouvent pas la qualité des résultats sur le Web réel.

## Administration du business

- Réutiliser `pro_base.html` sur les écrans Pro ; maintenir navigation et thème
  sans dépendance JavaScript supplémentaire.
- Filtrer tout indicateur par business/utilisateur courant, respecter visibilité
  de la page et dates des boosts. Ne jamais inventer ventes, visiteurs ou revenus.
- Le libellé administrateur du business ne confère aucun droit Django staff.
  Conserver approbation Pro, isolation des propriétaires et CSRF.
- Vérifier les compteurs et frontières d'accès avec `tracker.test_pro_overview`.

## Interface Tailwind

- Réutiliser `tracker/base.html` et les composants de `assets/css/app.css`.
- Conserver les classes Tailwind complètes dans les templates et scripts : éviter
  la concaténation de fragments que le compilateur ne détecte pas.
- Après modification des classes ou du thème : `pnpm run build:css`, puis
  `.venv/bin/python manage.py collectstatic --noinput`. Livrer le CSS généré.
- Installation frontend : Node compatible Tailwind 4 et pnpm 11, puis
  `pnpm install --frozen-lockfile`. Le script de build de `@parcel/watcher` est
  autorisé explicitement dans `pnpm-workspace.yaml`.
- Vérifier desktop/mobile, navigation, labels, focus, formulaires et états
  conditionnels. Conserver URLs, CSRF, permissions et contrats JavaScript.
- Si le rôle PostgreSQL local ne peut créer une base de test, exécuter
  `DB_ENGINE=sqlite .venv/bin/python manage.py test --noinput`. Cela valide la
  suite sur SQLite et ne constitue pas une validation de la suite PostgreSQL.

- Pour les composants et utilitaires colorés, prévoir une variante `dark:` avec
  contrastes lisibles. Garder les badges sémantiques distincts en clair et sombre.
- Le thème reste une préférence du navigateur, sans donnée personnelle ni écriture
  en base. Vérifier bascule clavier, navigation, rechargement et petits écrans.
