# Mémoire active Bendango

Dernière mise à jour : 2026-10-09.

## Sources et fonctionnement

Cette mémoire résume les faits utiles à la continuité. L'historique antérieur reste
dans `TASKMEMORY.md`, dont la dernière note de roadmap est datée du 2026-10-02.
Le code, les tests et les observations récentes priment sur les descriptions historiques.
Ne jamais conserver de secrets ou de données personnelles dans ce journal.

## 2026-10-07 — installation et changement de branche

- Dépôt cloné dans le sous-dossier `bendango/` de l'espace de travail.
- pyenv installé pour le compte utilisateur ; environnement `bendango` créé
  avec Python système 3.12.3 et lié à `.venv` via `pyenv link version`.
- `main` a présenté 11 échecs de tests ; ce résultat est historique et ne décrit
  pas la branche actuelle.
- Branche la plus récente par date de commit récupérée : `clean/bendango-v2`,
  commit `3aeba33` du 2026-10-02. Aucun push effectué dans cette session.
- La base livrée sur `main` contenait des doublons bloquant les migrations.
  Elle a été conservée dans `.venv/db-original.sqlite3` ; une base locale neuve
  a été créée. Une sauvegarde avant passage v2 existe dans `.venv/db-before-v2.sqlite3`.
- Modifications suivies de runtime sur `main` conservées dans un stash nommé
  `Local runtime before clean/bendango-v2`. Ne pas le réappliquer aveuglément sur v2.
- Migrations jusqu'à `0020` appliquées, fichiers statiques collectés.
- Dernière suite exécutée : 252 tests, aucun échec, 1 ignoré ; durée environ 41 s.
- Serveur local et workers de découverte/collecte démarrés ; page d'accueil HTTP 200.
  Leur fonctionnement doit être revérifié après une interruption de session.
- Celery 5.6.3 installé avec Redis et ajouté à `requirements.txt` ; intégration non réalisée.

## 2026-10-07 — analyse

- Redis installé sur la machine et répondant `PONG` ; application encore configurée
  sans `REDIS_URL`, donc cache local au processus.
- Pas de changement de schéma détecté et pas de dépendances installées incompatibles.
- `requirements.txt` omet les imports obligatoires `ddgs` et `pydantic`.
- Vérifications isolées : fichier texte renommé `.jpg` accepté ; URL locale
  transmise au transport simulé. Aucun appel réel à une destination interne.
- Contrôle de déploiement avec `DEBUG=False` et clé temporaire valide : `mail.E001`
  persiste à cause du backend email console.
- Aucun appel Bedrock réel validé. La dernière recherche consultée avait quatre
  tâches en échec, dont une HTTP 403 et une erreur d'extraction ; pas d'offre exploitable.
- Les unités systemd livrées ciblent un autre chemin que l'installation actuelle.
- Les défauts ont été documentés ; aucun correctif applicatif réalisé lors de l'analyse.

## 2026-10-08 — documentation vivante

- Demande utilisateur : créer les documents dans `doc_ia` et les consulter/mettre
  à jour à chaque évolution du code. Six noms ont été donnés malgré la mention de cinq.
- Décision : créer les six fichiers demandés. `PROD.md` couvre produit et préparation
  à la production pour expliciter son rôle.
- Ajout d'`AGENTS.md` au dépôt et d'un pointeur à la racine de l'espace de travail.
- TASKS.md constitue le suivi actif ; TASKMEMORY.md reste conservé comme historique.
- Vérification documentaire : présence des six fichiers et des consignes, liens
  locaux et cohérence avec les fichiers inspectés. Aucun test applicatif relancé,
  car cette intervention ne modifie que la documentation.
- Documents consultés/réconciliés : PROD, ARCHITECTURE, RULES, DESIGN, TASKS, MEMORY.

## 2026-10-08 — relecture approfondie et enrichissement

- Périmètre demandé : réviser le code pour compléter les documents ; intervention
  limitée à la documentation, sans corriger ni modifier le comportement applicatif.
- Relu : modèles catalogue/prix/business/boost, classements, devises, caches,
  droits des routes, orchestration des workers, API et polling, templates et
  correspondance avec les tests existants.
- Ajouté : règles produit, états persistés/dérivés, contrat API, chemins d'accès,
  reprise/concurrence des workers, seuils de cache et qualité, effets de `save()`,
  contraintes de configuration, exploitation et matrice de tests ciblés.
- Défaut reproduit sans écriture en base ni réseau : `_run_state` renvoie
  `completed` pour un run simulé `failed` ayant une date `completed_at`.
- Devises : `normalize_to_usd(100, 'MAD')` renvoie `None`, USD renvoie `100.00`.
  Le recours au prix brut dans les comparaisons rend les mélanges non normalisés risqués.
- Relecture du template : polling toutes les 1 500 ms ; badge vert terminal
  générique et reprises silencieuses en cas d'erreur. Validation visuelle non réalisée.
- Configuration : plusieurs réglages lus depuis settings ne sont pas raccordés
  aux variables d'environnement ; ne pas supposer qu'une ligne `.env` les active.
- Vérifications exécutées : `manage.py check` sans erreur ;
  `makemigrations --check --dry-run` sans changement ; `pip check` sans incompatibilité.
  Les résultats ne prouvent pas une installation vide reproductible.
- La suite complète de 252 tests n'a pas été relancée dans cette intervention
  documentaire ; son dernier résultat du 2026-10-07 reste la référence historique.
- Les nouveaux défauts et critères de correction sont ajoutés à TASKS.md et restent
  ouverts. Aucun défaut signalé n'est présenté comme corrigé.
- Les six documents ont été enrichis et réconciliés ; liens vers les modules,
  présence des fichiers et absence d'erreurs d'espacement vérifiées avant livraison.

## 2026-10-08 — préparation de PostgreSQL

- Demande : créer une base PostgreSQL et connecter l'application.
- PostgreSQL 16 installé ; `pg_isready` indique un serveur disponible sur
  `127.0.0.1:5432`. La connexion locale du compte courant échoue : rôle absent.
- `sudo -n true` refuse l'accès sans mot de passe ; aucun refus d'auto-review.
  Aucun rôle ni base applicative créé, `.env` reste inchangé et SQLite actif.
- Script livré : `scripts/setup_postgres.py`, exécutable avec `.venv/bin/python`
  dans un terminal pour permettre la saisie sudo. Création, validation, migrations
  et activation de `.env` y sont préparées ; aucune donnée SQLite importée automatiquement.
- Sauvegarde créée : `.venv/db-postgres-preparation-20261008.sqlite3`, mode 0600.
- Vérifications : syntaxe Python par AST, pilote psycopg 3.3.6 disponible,
  fichier d'identifiants de `.venv` ignoré par Git. Script non exécuté de bout en bout.
- Documents réconciliés : PROD, ARCHITECTURE, RULES, TASKS, MEMORY mis à jour ;
  DESIGN consulté et inchangé, aucune évolution visible encore effective.
- Suite restante : exécution administrateur, contrôle de connexion, redémarrage
  des processus, vérification HTTP et mise à jour de l'état documentaire.

## 2026-10-08 — refonte Tailwind

- Demande : travailler le design avec Tailwind. Direction claire, ardoise et
  émeraude ; accueil centré sur le produit recherché et filtres organisés.
- Ajout du thème/composants `assets/css/app.css`, build CLI Tailwind 4.3.3,
  manifeste frontend et CSS compilé livré dans `tracker/static/tracker/css/app.css`.
- Les 14 templates héritent d'une navigation/pied de page communs ; suppression
  du CDN Bootstrap et des styles embarqués. Formulaires harmonisés, labels associés,
  lien au contenu, focus visible et mouvement réduit. Contrats métier conservés.
- Build local et collectstatic réussis ; `manage.py check` sans erreur ; suite
  de 252 tests SQLite réussie (1 test d'intégration ignoré, environ 41 secondes).
  Les premières exécutions ont révélé un manifeste statique absent, puis le texte
  de salutation perdu : collecte des assets et salutation commune corrigent ces
  régressions. Le dernier passage complet est réussi.
- PostgreSQL actif observé : connexion OK, zéro migration restante. La suite
  PostgreSQL ne démarre pas car le rôle ne possède pas CREATEDB ; aucune permission
  élargie. La bascule elle-même n'a pas été réalisée dans ce lot de design.
- Contrôles navigateur : accueil vide desktop 1440 px et mobile 390 px, connexion
  mobile, restriction de site affichable. Accueil mobile sans débordement horizontal.
  Les vues avec données et parcours clavier complets restent à contrôler.
- Serveur de développement redémarré sur 127.0.0.1:8000 ; workers existants non
  redémarrés dans cette intervention. Aucun appel LLM, publication, commit ou push.
- Les six documents ont été consultés et mis à jour ; README décrit le build.

## 2026-10-09 — thème sombre

- Demande : ajouter le thème dark à l'interface Tailwind existante.
- Variante `dark` contrôlée par la classe racine, palette sombre des composants
  et utilitaires des 14 templates, contrôles natifs via `color-scheme`.
- `theme.js` applique la préférence avant la feuille CSS, suit le système sans
  choix manuel, mémorise `light`/`dark` dans `bendango-theme`, synchronise les
  onglets et tolère le stockage indisponible. Bouton lune/soleil accessible au clavier.
- Compilation Tailwind, collectstatic et `manage.py check` réussis ; syntaxe JS
  contrôlée. 22 tests comptes/accueil réussis sur SQLite, environ 9 secondes.
  La suite complète n'a pas été relancée pour cette modification visuelle.
- Vérifications navigateur : bascule sombre puis claire par Entrée, retour au
  sombre, conservation après rechargement et navigation vers connexion ; rendu
  mobile 390 px sans débordement horizontal. Aperçu final sombre conservé.
- Les six documents ont été réconciliés. ARCHITECTURE corrige aussi son ancien
  état PostgreSQL contradictoire avec le constat de fin du 2026-10-08.
- Aucun changement de schéma, dépendance ou logique métier ; aucun appel LLM.

## 2026-10-09 — simplification du détail de recherche

- Demande : supprimer « Modèle IA » et son nom de l'interface de détail.
- Retrait du bloc dans `tracker/templates/tracker/search_run_detail.html` pour
  toutes les recherches ; aucune modification du modèle utilisé ni des données.
- Vérification : rendu du template sans le libellé et sans le nom du modèle,
  contrôle Django et diff sans erreur. Aucun nouveau test ajouté pour ce retrait visuel.
- Six documents consultés ; DESIGN, TASKS et MEMORY actualisés. PROD, ARCHITECTURE
  et RULES restent cohérents, sans changement de comportement interne.

## 2026-10-09 — livraison Git après chaque modification

- Instruction utilisateur : commit et push après chaque lot de modifications
  validé. Autorisation conservée dans AGENTS.md et RULES.md, sans force push.
- Premier lot à publier : travaux accumulés de cette session (Celery, documentation
  vivante, script PostgreSQL, interface Tailwind, thème sombre et détail simplifié).
- Contrôles disponibles : suite complète 252 tests réussie avant le thème sombre
  (1 ignoré), puis 22 tests comptes/accueil réussis ; rendu du détail sans modèle IA,
  check Django et diff sans erreur. Les secrets et fichiers de runtime sont ignorés.
- Les six documents ont été réexaminés ; RULES, TASKS, MEMORY et AGENTS actualisés ;
  PROD, ARCHITECTURE et DESIGN restent cohérents. Le résultat de publication est
  vérifiable dans l'historique Git et la branche distante.

## Modèle des futures entrées

Pour chaque lot, ajouter une entrée datée avec : demande et périmètre ; comportement
modifié ; décisions et raisons ; fichiers concernés ; vérifications et résultats ;
limites et tâches restantes ; liste des documents mis à jour ou restés cohérents.
Ne pas recopier des logs complets ni annoncer un test non exécuté.
