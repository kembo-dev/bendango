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

## 2026-10-09 — profils LLM dynamiques

- Demande : fichier de configuration dynamique, modèle local ou API avec clé.
- Ajout de `config/llm.toml` et de son chargeur sans cache ; surcharge privée
  `llm.local.toml` ignorée par Git, sélection via CLI ou `LLM_PROFILE`.
- Profils Ollama local, Studio compatible OpenAI, API avec clé, Bedrock et legacy.
  La sélection livrée reste legacy pour conserver l'installation existante.
  Les clés sont référencées par variables d'environnement, jamais écrites dans TOML.
- Adaptateurs HTTP/Bedrock communs à la recherche et à `scrape_url` : validation
  JSON/Pydantic, limites configurables, logs sans contenu de réponse ni clé,
  aucun repli automatique vers une autre API. Les nouvelles tâches mémorisent
  `profil::modèle` ; les anciennes tâches sans préfixe suivent la sélection active.
- Ajout des dépendances déjà requises `ddgs` et `pydantic` ; versions installées
  compatibles et `pip check` réussi. Installation vierge non validée.
- Validation : suite SQLite de 271 tests réussie (1 intégration ignorée), puis
  20 tests ciblés réussis après ajout du cas de référence malformée et correction
  des préférences TOML indentées. Aucun appel réel aux fournisseurs.
- PostgreSQL connecté ; `makemigrations --check --dry-run` sans changement.
  `llm_config --check` legacy valide sans réseau. Serveur web et worker de collecte
  existants relancés ; accueil HTTP 200. Worker de découverte absent, non lancé
  dans cette validation ; deux recherches anciennes en attente observées.
- Six documents réexaminés : PROD, ARCHITECTURE, RULES, TASKS, MEMORY et readme
  actualisés. DESIGN reste cohérent : aucune modification d'interface et modèle
  toujours masqué sur le détail des recherches.
- Livraison sur `clean/bendango-v2` suivant l'autorisation permanente de push ;
  consulter l'historique Git pour le résultat. Tests PostgreSQL et qualité réelle
  de chaque fournisseur restent hors de cette validation.

## 2026-10-09 — extraction LLM facultative

- Demande acceptée : mode auto par défaut, disabled/required, secours facultatif
  et refus d'un secours payant sans autorisation explicite dans la configuration.
- `[policy]` partagé ou privé relu à chaque appel. Auto autorise les recherches sans
  modèle ni clé API ; JSON-LD/métadonnées/HTML sont prioritaires. Les tâches créées
  sans complément mémorisent une référence réservée et restent sans LLM après
  configuration ultérieure. Disabled interdit tous les adaptateurs.
- Required exige un complément utilisable et renvoie une erreur contrôlée si
  nécessaire ; l'extraction locale réussie et les offres déjà vérifiées restent
  valables. Pas de prix créé quand les données sont insuffisantes.
- Secours nommé essayé une seule fois, sans boucle sur le profil courant ; tout
  endpoint hors localhost/127.0.0.1/::1 exige `allow_paid_fallback=true`.
- Diagnostic CLI/logs réservé aux opérateurs, messages publics génériques. Résultats
  et détail de recherche signalent les pages échouées et une collecte possiblement
  incomplète ; le modèle reste masqué. `scrape_url` suit la politique commune.
- Validation : suite complète 296 tests SQLite réussie (1 intégration ignorée,
  environ 41 s), incluant 24 régressions de politique/recherche/affichage. Appels
  SDK et HTTP simulés pour les tests LLM ; aucun appel fournisseur réel effectué.
  Check Django et cohérence des migrations réussis ; build Tailwind et collectstatic
  réussis. Le profil actuel legacy/Bedrock est conservé, sans secours configuré.
- Serveur web et worker de collecte existants rechargés, aucune collecte active
  lors du redémarrage. Worker de découverte non lancé pour cette validation.
- Les six documents sont réconciliés et mis à jour, ainsi que readme. Aucun
  changement de schéma, de dépendance ou d'identifiant privé. Publication sur
  clean/bendango-v2 suivant l'autorisation permanente ; résultat dans Git.

## 2026-10-09 — administration client Pro

- Demande : donner à `/pro/` une véritable présentation administrative du client,
  plus créative. Skill ECC frontend-design-direction appliqué : outil de gestion
  quotidien, dense et lisible, menu ardoise sombre et accents émeraude/bleu/ambre.
- Ajout de pro_base/navigation/icon et extraction du bouton de thème en partial.
  Le cadre couvre dashboard, offres, produits, formulaires et demande de boost.
- Tableau de bord : offres en ligne, catalogue, boosts en cours, checklist de
  profil ; table des six dernières offres, demandes de boost, recherches et
  actions à traiter. Les chiffres sont réels et isolés par business/utilisateur.
  Pas de statistiques de ventes ou revenus inexistantes.
- Édition entreprise dans `?section=profile`, soumission et redirection existantes
  préservées, erreurs visibles. Aucun nouveau privilège, route ou modèle.
- Validation : 44 tests comptes/catalogue/offres/boosts/médias réussis, six nouveaux
  tests de compteurs, profils masqués, boosts expirés et isolation réussis, puis
  suite complète 302 tests SQLite réussie (1 intégration ignorée, environ 43 s).
  Build Tailwind, collectstatic et check Django réussis.
- Vérifications navigateur sur rendu de démonstration, sans écrire dans la base
  applicative : desktop 1440 px et mobile 390 px, clair/sombre, navigation mobile
  et profil. Débordement initial du texte sr-only dans le tableau corrigé par un
  conteneur positionné ; document mobile ensuite limité à sa largeur. Capture
  de démonstration conservée hors dépôt. Le navigateur réel demandait une connexion.
- Serveur web local rechargé ; workers et politique LLM inchangés. Six documents
  réconciliés et actualisés. Livraison sur clean/bendango-v2 suivant l'instruction
  permanente ; résultat vérifiable dans Git.

## Modèle des futures entrées

Pour chaque lot, ajouter une entrée datée avec : demande et périmètre ; comportement
modifié ; décisions et raisons ; fichiers concernés ; vérifications et résultats ;
limites et tâches restantes ; liste des documents mis à jour ou restés cohérents.
Ne pas recopier des logs complets ni annoncer un test non exécuté.

## 2026-10-09 — publication rapide ouverte à tous

- Demande : publier rapidement depuis le téléphone comme Vinted ; clarification
  reçue : tous les utilisateurs connectés. Trois étapes, caméra native/galerie,
  jusqu'à huit photos, sélection de couverture, aperçu et action basse fixe.
- Nouveau module publishing, formulaire mobile, routes publier/mes annonces/
  éditer/toggle ; isolation propriétaire, CSRF et aucun changement des droits Pro.
  Profil particulier créé seulement au premier POST valide ; pseudonyme public,
  statut non vérifié, aucune passerelle Retailer. Suspensions et révocations
  ne sont pas contournées. Approbation Pro convertit le profil sans perdre l'offre.
- Migration 0021 is_individual, défaut false pour l'existant ; filtre admin ajouté.
  Numéro WhatsApp requis et annoncé public ; photos obligatoires à la création,
  prix facultatif ; aucune saisie, photo ou donnée de contact persistée côté client.
- Pillow 12.3.0 installé et déclaré >=12,<13. Les uploads des deux parcours
  sont décodés, orientés, réduits à 2400 px et réencodés JPEG sans EXIF ; limites
  8 Mo/25 MP. HEIC/RAW non supportés, GIF figé. Fixtures médias remplacées par
  de vraies images ; titre/slug/permissions et formulaires complets Pro conservés.
- Validation : 316 tests SQLite réussis (1 intégration ignorée), dont 14
  nouveaux cas ; 40 tests ciblés intermédiaires et 31 tests comptes/publication
  après correction du type entreprise lors de l’approbation réussis ; check, pip check, migrations et build/collectstatic réussis.
  Migration PostgreSQL locale appliquée. Aucun appel LLM ni donnée de démo en
  base applicative. Tests initiaux corrigés : manifest assets à collecter avant
  tests et assertion de JS tenant compte du nom hashé.
- Navigateur sur serveur isolé SQLite 8002 : deux photos ajoutées, couverture
  changée, trois étapes parcourues, publication confirmée dans Mes annonces,
  édition ouverte. Aperçu clair et sombre contrôlé. La capacité viewport n'a
  pas appliqué la largeur 390 demandée (largeur effective 1265 px) : inspection
  visuelle sur téléphone réel et accès matériel à la caméra restent à valider.
  Capture de démonstration hors dépôt. Serveur de test arrêté après vérification.
- Les six documents doc_ia sont réconciliés et actualisés ; serveur applicatif
  rechargé après migration et assets. Publication sur clean/bendango-v2 selon
  l'autorisation permanente, résultat vérifiable dans Git.

## 2026-10-09 — galerie publique animée

- Demande : animer la galerie de l'offre Esika. Photo principale et grille
  remplacées par carrousel unique : scroll-snap, transition douce, miniatures,
  flèches, compteur et clavier. Balayage natif, clair/sombre et repli sans JS.
- Diaporama facultatif de 5 s avec pause ; arrêt par navigation manuelle/toucher,
  suspension au survol/focus/hors écran/onglet caché. Reduced-motion interdit
  le diaporama et garde les commandes manuelles immédiates. Aucun autoplay imposé.
- Vue publique : couverture en premier, médias vides ignorés, URL de secours
  préservée ; contrôles absents avec zéro/une photo. Aucun schéma/droit modifié.
- Validation : 17 tests ciblés médias/offres réussis, dont trois nouveaux cas ;
  build Tailwind, collectstatic, check Django et diff --check réussis. Navigateur
  sur l'offre demandée : deux images chargées, flèche, miniature, clavier et
  diaporama 1/2 vers 2/2 en 5,7 s, pause confirmée. Compteur NaN découvert sur
  un conteneur temporairement sans largeur et corrigé par gardes de dimensions.
  Script final distinct chargé après redémarrage pour éviter le cache du prototype.
  Capture hors dépôt ; aucun contact enregistré dans la documentation.
- Vérification visuelle desktop ; balayage matériel et préférence reduced-motion
  sur téléphone restent à contrôler. Serveur local rechargé ; workers inchangés.
- DESIGN, ARCHITECTURE, TASKS et MEMORY actualisés ; PROD et RULES consultés,
  cohérents sans modification nécessaire. Commit/push suivant la consigne permanente.

## 2026-10-09 — dimensions et renditions des photos

- Demande : appliquer cadre carré, 1600 px maximum, miniatures 320 × 320 et
  compression WebP 85 sans déformation/agrandissement. Nouveau module commun,
  traitement au formulaire puis stockage de la miniature sans réencoder le grand
  fichier. Orientation, transparence et absence de métadonnées vérifiées.
- Migration 0022 ajoute deux fichiers de rendition à OfferMedia. Nouvelles
  publications déjà préparées ; anciennes sources conservées avec optimized_file
  distinct. Galerie et URL publique utilisent la version optimisée ; suppression
  propriétaire traite aussi les variantes. Images externes non téléchargées.
- Commande optimize_offer_images avec défaut dry-run, --apply et --offer-id ;
  idempotence et conservation des octets de source testées. Migration PostgreSQL
  locale appliquée et deux médias optimisés, zéro erreur, sources conservées.
- Validation : 31 tests ciblés réussis ; suite complète 328 tests SQLite réussie
  (1 intégration ignorée, 52 s), neuf nouveaux cas. Build, collectstatic, check,
  makemigrations --check, pip check et diff --check réussis. Aucun appel LLM réel.
- Navigateur sur Esika : cadre 640 × 640, images WebP 64 × 64 affichées à 64 × 64,
  miniatures 320 × 320 chargées, compteur 2/2 après changement. Ces petites sources
  ne peuvent pas produire de détails supplémentaires. Somme des deux sources
  4820 octets, photos optimisées 2928 octets, miniatures 3340 octets : les fichiers
  principaux sont réduits de 39 %, mais les deux renditions cumulées sont plus lourdes
  pour ces très petites sources. Ne pas annoncer une économie totale sur ce cas.
- Serveur local rechargé, capture hors dépôt, workers inchangés. Les six documents
  doc_ia ont été consultés, réconciliés et mis à jour dans ce lot. Livraison Git
  suivant la consigne permanente ; résultat vérifiable dans l'historique.

## 2026-10-09 — Devises administrables en base

- Demande : configurer les devises dans la base pour le parcours `/publish/`.
- Currency et son administration : code unique, nom, symbole, disponibilité et
  ordre. Dix devises des marchés existants initialisées par migrations 0023/0024,
  appliquées à PostgreSQL local ; aucune modification des anciens prix/codes.
- Listes dynamiques communes à publication mobile, offres Pro et catalogue ;
  codes normalisés et vérifiés côté serveur. Ordre en base pour le repli si la
  devise initiale du pays est indisponible. Sans devise active, création bloquée
  et explication affichée. Modification du catalogue effective sans redémarrage.
- Édition : la vue transmet seulement la devise de l’objet possédé. Cette devise
  reste conservable si désactivée ou historique, sans autoriser d’autres codes
  désactivés. Les conversions et leurs limites existantes restent inchangées.
- Validation : dix nouveaux tests ; 24 tests ciblés réussis ; suite complète
  de 338 tests SQLite validée (1 intégration ignorée). Check Django, cohérence
  des migrations, build CSS, collectstatic et diff --check réussis. PostgreSQL :
  dix devises actives constatées. Aucun appel LLM réel.
- Navigateur sur instance SQLite fictive séparée : dix options lisibles, choix
  CDF et aperçu 25.00 CDF vérifiés sans soumettre de modification. Capture hors
  dépôt : devises-publication.png. Pas de test matériel sur téléphone dans ce lot.
- Les six documents doc_ia ont été consultés et réconciliés dans ce lot. Livraison
  Git selon la consigne permanente ; résultat vérifiable dans l’historique.

## 2026-10-09 — Zoom des galeries

- Demande : pouvoir zoomer dans la galerie de l’offre moto Esika. Vue agrandie
  facultative ajoutée à toutes les galeries, même avec une seule photo ; lien
  direct vers le fichier en absence de JavaScript/support dialog.
- Nouveau offer-gallery-zoom.js : modale native, 100–400 %, +/−/reset, molette,
  déplacement Pointer Events et pincement à deux contacts. Navigation entre
  photos synchronisée par événements avec le slider ; diaporama arrêté.
- Focus enfermé par le dialog natif, fermé par Échap ou bouton ; focus rendu à
  l’ouvreur et overflow du body restauré. Erreur de chargement explicite. Pas
  de changement en base, fichier source ou dépendance. Agrandissement volontaire
  seulement : les images de faible résolution ne gagnent pas de détails.
- Validation : 17 tests offres/médias réussis, régressions existantes enrichies
  pour zéro/une/plusieurs photos ; syntaxe des deux scripts JS, check Django,
  build Tailwind, collectstatic et diff --check réussis. Suite complète non
  répétée pour ce lot frontend ; dernier passage complet : 338 tests (1 ignoré).
- Navigateur : moto 447 × 447 affichée à 894 × 894 au zoom 200 %, limite 400 %
  et bouton + désactivé, déplacement à 300 % constaté sur les offsets de scroll,
  reset et Échap avec focus/scroll restaurés. Galerie de deux photos : arrêt
  du diaporama, passage à 2/2, synchronisation et ouverture par Entrée vérifiés.
  Capture hors dépôt : zoom-galerie-moto.png. Pincement matériel et contrôle
  visuel sur téléphone réel restent à réaliser ; ne pas les annoncer validés.
- Six documents consultés, réconciliés et actualisés. Serveur local rechargé,
  workers inchangés. Commit/push selon la consigne permanente, résultat dans Git.

## 2026-10-09 — Origine et statut des publications

- Demande : savoir sur l’accueil si une publication vient d’un Pro validé,
  non validé ou d’un particulier. Statut calculé depuis BusinessProfile courant ;
  is_individual prend priorité, puis is_verified. Aucun changement de droits,
  de visibilité, de données ou de schéma. La validation concerne le compte.
- Badge partagé accueil/détail avec libellé, icône, palette clair/sombre et
  description. Source Bendango neutre et sponsoring séparé ; pas de statut de
  vendeur ni nouvelle identité divulguée sur les recherches communautaires.
- Validation : quatre nouveaux tests (trois états/detail, particulier avec
  ancien indicateur vérifié, révocation, recherches sans statut) ; 49 tests
  accueil/comptes/publication/offres réussis. Check Django, cohérence migrations,
  build CSS, collectstatic et diff --check réussis. Aucun appel LLM réel.
- Navigateur : les trois badges sont présents sur une base fictive séparée ;
  capture origine-publications.png hors dépôt. Accueil réel rechargé : deux
  offres du Pro validé et un sujet de recherche correctement distingués. Base
  réelle non modifiée. Serveur fictif arrêté ; workers inchangés.
- Six documents consultés et réconciliés ; PROD, ARCHITECTURE, DESIGN, TASKS et
  MEMORY actualisés. RULES reste cohérent. Commit/push selon la consigne permanente.
