# Travaux Bendango

Dernière mise à jour : 2026-10-09.

Les tâches ouvertes ci-dessous proviennent de l'analyse ; elles ne constituent
pas une autorisation générale de modification, publication ou appel à un service payant.

## Réalisé dans cette session

- [x] Cloner le dépôt et sélectionner `clean/bendango-v2` au commit `3aeba33`.
- [x] Créer l'environnement `bendango`, installer les dépendances locales.
- [x] Appliquer les migrations jusqu'à `0020` et lancer l'application localement.
- [x] Installer Celery avec support Redis et l'ajouter à `requirements.txt`.
- [x] Vérifier Redis : `PONG` observé le 2026-10-07.
- [x] Analyser architecture, configuration et problèmes prioritaires.
- [x] Créer les six documents `doc_ia` et les consignes `AGENTS.md` le 2026-10-08.
- [x] Relire modèles, classements, workers, routes et templates ; enrichir les six
  documents avec les contrats et règles métier le 2026-10-08.

- [x] Refondre les 14 templates avec Tailwind CSS et une base commune.
  Validation : compilation locale, collectstatic, check Django, 252 tests SQLite
  réussis (1 ignoré), accueil desktop/mobile et connexion mobile inspectés.

- [x] Ajouter un thème sombre partagé avec préférence système et choix mémorisé.
  Validation du 2026-10-09 : build/collectstatic/check, 22 tests comptes/accueil
  réussis sur SQLite, bascule clavier, rechargement, navigation et rendu mobile.

- [x] Retirer le libellé et le nom du modèle IA du détail des recherches (2026-10-09).

- [x] Enregistrer la consigne de commit et push après chaque lot validé dans
  AGENTS.md et RULES.md (2026-10-09).

- [x] Ajouter `config/llm.toml`, une surcharge locale privée, cinq profils et une
  commande de sélection/validation sans appel réseau. Adaptateurs Ollama,
  Chat Completions et Bedrock ; références de profil conservées dans les files.
  Validation : suite complète 271 tests (1 ignoré), puis tests ciblés complémentaires.
- [x] Déclarer `ddgs` et `pydantic` dans `requirements.txt` ; `pip check` réussi.
  L'installation dans un environnement vide reste à vérifier.

- [x] Rendre le LLM facultatif avec `policy.mode=auto`, modes disabled/required,
  secours explicite et garde pour les endpoints distants. Préserver les tâches
  sans LLM, afficher les résultats potentiellement incomplets, diagnostic opérateur.
  Validation : 296 tests SQLite réussis (1 ignoré), contrôles Django/migrations,
  compilation Tailwind et collecte des assets. Aucun appel LLM réel.

- [x] Transformer l'espace Pro en administration client : cadre commun, navigation,
  tableau de bord réel, priorités et profil séparé. Six tests de compteurs/isolation,
  302 tests SQLite réussis (1 ignoré), build/collectstatic et contrôles visuels
  desktop/mobile clair/sombre sur données fictives.

- [x] Ouvrir la publication mobile à tous les comptes connectés : parcours en
  trois étapes, photos/caméra/aperçu et gestion individuelle des annonces.
  Validation : 14 nouveaux tests, suite complète 316 tests SQLite réussie
  (1 intégration ignorée), publication/édition testées sur base fictive séparée.
  Migration 0021 appliquée à PostgreSQL local ; aucun droit Pro/staff accordé.

- [x] Animer la galerie publique des offres : carrousel, miniatures, flèches,
  clavier, balayage natif et diaporama facultatif avec pause. Validation : 17
  tests médias/offres réussis, dont 3 régressions couverture/fallback/absence
  d'image ; contrôles navigateur réalisés sur l'offre Esika et cycle 5 s observé.

- [x] Standardiser les photos : cadre carré, WebP 85 jusqu'à 1600 px, miniatures
  320 × 320 et absence d'agrandissement. Migration 0022 et traitement des deux
  photos existantes sans écrasement des sources. Validation : 31 tests ciblés,
  328 tests SQLite réussis (1 ignoré), neuf nouveaux cas et contrôle navigateur.

- [x] Gérer les devises de publication en base et dans Django admin : dix devises
  initiales, activation/ordre, listes partagées mobile/Pro/catalogue et conservation
  des anciennes devises en édition. Validation détaillée dans MEMORY.md.

- [x] Ajouter une vue agrandie aux galeries : zoom 100–400 %, déplacement,
  navigation et commandes clavier, arrêt du diaporama et restauration du focus.
  Validation : 17 tests offres/médias et contrôles navigateur sur une/deux photos.
  Pincement et ergonomie sur téléphone matériel restent à contrôler.

- [x] Identifier l’origine des publications sur l’accueil et le détail : Pro validé,
  Pro non validé ou Particulier ; statut courant, distinct du sponsoring.
  Validation : quatre nouveaux cas, 49 tests ciblés et trois badges inspectés
  dans le navigateur sur données fictives séparées.

- [x] Transformer l’accueil en place de marché : grille photo/prix/vendeur,
  rayons et filtres réels, recherche compacte et communauté séparée. Quatre
  nouveaux tests de navigation, 346 tests de suite (1 ignoré), puis 30 tests
  ciblés après compactage. Rendu téléphone réel restant à vérifier.

## Priorité haute

- [ ] Préserver l'état d'échec dans `_run_state` et le suivi navigateur.
  Preuve : un run simulé `failed` avec `completed_at` est exposé comme `completed`.
  Validation : tests d'échec daté, succès, fin partielle ; badge et message adaptés
  au statut réel, sans présenter un échec comme un succès.
- [ ] Sécuriser la comparaison multi-devise.
  Preuve : `normalize_to_usd(100, 'MAD')` renvoie `None`, tandis que les comparaisons
  utilisent alors le montant brut. Les marchés exposent aussi des devises sans taux.
  Validation : taux absents explicitement traités, aucune moyenne/économie incohérente,
  tests de devises mixtes et indication des taux utilisés.

- [ ] Protéger les accès HTTP sortants contre les destinations internes.
  Validation : tests des réseaux privés/locaux/réservés, résolution et redirections ;
  les pages marchandes publiques restent accessibles.
- [x] Valider et réencoder les uploads de formulaires avant stockage.
  Validation : texte renommé .jpg rejeté, véritables images réencodées sans EXIF,
  limites serveur 8 fichiers/8 Mo/25 MP. Pillow déclaré et installé.
- [ ] Rendre l'installation reproductible.
  Validation : dépendances obligatoires (`ddgs`, `pydantic`) déclarées ;
  installation et démarrage réussis dans un environnement vide.

## Priorité moyenne

- [ ] Finaliser la validation PostgreSQL locale (demande du 2026-10-08).
  Constat pendant la refonte : moteur PostgreSQL actif, connexion Django réussie,
  aucune migration restante et accueil HTTP 200 après redémarrage web.
  Restant : vérifier le redémarrage des workers après bascule et décider de
  l'import SQLite. Tests PostgreSQL bloqués par l'absence du droit CREATEDB ;
  suite validée séparément sur SQLite, sans élargir les droits applicatifs.
- [ ] Compléter les contrôles visuels Tailwind avec données représentatives.
  Validation : résultats actifs/partiels/échoués, quota atteint, offres publiques,
  sponsorisées et espace Pro sur desktop/mobile, puis parcours clavier complet.

- [ ] Raccorder et documenter les réglages métier annoncés dans `.env`.
  Validation : chaque réglage supporté modifie effectivement `django.conf.settings` ;
  les paramètres non supportés ne sont plus présentés comme actifs.
- [ ] Définir le service de médias hors DEBUG.
  Preuve : l'aide Django `static()` de `config/urls.py` ne suffit pas en production.
  Validation : image uploadée accessible via reverse proxy ou stockage prévu,
  avec configuration et contrôles de contenu adaptés.
- [ ] Améliorer les erreurs et l'arrêt du polling.
  Validation : erreurs réseau/accès persistantes annoncées, reprises bornées ou
  contrôlées, aucune boucle silencieuse indéfinie après une recherche inaccessible.
- [ ] Clarifier confidentialité des recherches anonymes et contrôle d'abus.
  Validation : politique d'accès par session/UUID explicite, quota et limites
  serveur testés ; éviter d'assimiler quota de session et quota par personne.

- [ ] Configurer Redis pour l'application et vérifier les échanges entre processus.
  Validation : cache Redis actif et test de partage entre web et workers.
- [ ] Décider puis documenter l'utilisation de Celery ou la conservation des workers.
  Validation : responsabilités, reprise, déduplication et transition explicitement définies.
- [ ] Adapter les chemins des trois unités systemd à l'installation réelle.
  Validation : service web et workers démarrent depuis le bon répertoire.
- [ ] Configurer un backend email de production.
  Validation : contrôle de déploiement sans `mail.E001` et envoi vérifié dans un
  environnement autorisé.
- [ ] Définir le déploiement PostgreSQL, médias, HTTPS et sauvegardes.
  Validation : configuration documentée et restauration de sauvegarde vérifiée.
- [ ] Valider séparément la connexion Bedrock et la qualité de recherche réelle.
  Validation : appel d'intégration autorisé et cas de recherche représentatifs.

## Maintenance

- [ ] Évaluer les limites de recherche Pro et les requêtes liées aux historiques.
  Validation : cas de plus de 250 offres et mesure du nombre de requêtes sur une
  page de résultats ; choisir pagination/indexation/préchargement selon les mesures.

- [ ] Ajouter une CI adaptée aux contrôles Django, migrations et tests.
- [ ] Réduire progressivement la taille de `tracker/views.py` sans changer les parcours.
- [ ] Vérifier les états d'échec et de résultat partiel sur mobile et au clavier.

## Règle de suivi

Après chaque évolution, ajuster les cases, critères et priorités ; ajouter la
preuve de réalisation dans MEMORY.md. Cocher uniquement ce qui est effectivement
réalisé et vérifié. Conserver les tâches bloquées ouvertes avec leur cause.
