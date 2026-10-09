# Travaux Bendango

Dernière mise à jour : 2026-10-09.

Les tâches ouvertes ci-dessous proviennent de l'analyse ; elles ne constituent
pas une autorisation générale de modification, publication ou appel à un service payant.

## Prochaines tâches — feuille de route du 2026-10-09

Demande utilisateur : inscrire les manques identifiés pour les prochaines tâches.
Cette planification n’implémente pas les fonctionnalités et ne lance aucun service
payant. Traiter les lots dans l’ordre ci-dessous ; les critères techniques déjà
présents dans les sections de priorité restent la référence, sans les dupliquer.

### Lot 1 — Fiabilité et sécurité, prochaine tâche à réaliser

Les trois tâches sont déjà ouvertes dans « Priorité haute » :

1. Protéger les URL collectées contre les réseaux internes, y compris après
   résolution DNS et redirection.
2. Corriger la comparaison multi-devise lorsque le taux de conversion manque.
3. Préserver les états d’échec dans le suivi des recherches et l’interface.

Terminer ce lot lorsque les tests de régression et les parcours d’erreur sont
validés, sans exposer de prix comparables fictifs ni de faux succès.

### Lot 2 — Récupération de compte et confiance

- [ ] Ajouter le parcours « Mot de passe oublié ».
  Validation : lien depuis la connexion, email de réinitialisation, jeton expirant
  à usage unique, réponse ne révélant pas l’existence d’un compte et tests d’accès.
  Dépendance : backend email de production (tâche déjà ouverte).
- [ ] Vérifier les adresses email des comptes.
  Validation : lien expirant, renvoi limité, statut visible ; définir l’effet sur
  la publication et préserver l’accès des comptes existants pendant la transition.
- [ ] Permettre le signalement d’une annonce et son traitement administratif.
  Validation : motif, file de modération, décision tracée, retrait/rétablissement,
  protection contre l’abus ; seul le personnel autorisé décide de la modération.

### Lot 3 — Retour au marché et échanges

- [ ] Ajouter les favoris et une page personnelle pour les retrouver.
  Validation : ajouter/retirer sans doublon, isolation par compte, accès depuis
  les cartes et le détail ; gérer les annonces retirées ou devenues privées.
- [ ] Ajouter les recherches sauvegardées.
  Validation : conserver requête et filtres, relancer la recherche, renommer ou
  supprimer ; aucun utilisateur ne peut accéder aux sauvegardes d’un autre.
- [ ] Ajouter une messagerie entre acheteur et vendeur liée à l’annonce.
  Validation : ouvrir une conversation depuis une offre, lire/envoyer seulement
  comme participant, afficher les non-lus, bloquer/signaler et limiter les abus.
  Conserver les contacts WhatsApp/téléphone pendant la transition.
- [ ] Ajouter les brouillons de publication et le statut « vendu ».
  Validation : reprise d’un brouillon privé depuis le téléphone, publication
  explicite, modification réservée au propriétaire ; une annonce vendue affiche
  son statut et sort des offres disponibles sans perdre son historique.

### Lot 4 — Notifications et pilotage

- [ ] Notifier les nouveaux messages, les décisions Pro et les annonces
  correspondant aux recherches sauvegardées.
  Validation : centre de notifications, état lu/non lu, préférences et désactivation,
  absence de doublons et respect de la confidentialité. Définir les canaux email
  ou navigateur avant leur intégration ; dépend des lots 2 et 3.
- [ ] Mesurer les vues et clics de contact par annonce pour son propriétaire.
  Validation : compteurs réels, exclusion des rafraîchissements abusifs et accès
  isolé ; documenter la collecte et la durée de conservation.
- [ ] Définir puis ajouter les avis vendeurs avec preuve de l’échange.
  Validation : critère d’éligibilité explicite, anti-doublon, modération et réponse
  du vendeur ; ne pas afficher « achat vérifié » sans preuve d’une transaction.
  La méthode de vérification reste à décider avant implémentation.

### Lot 5 — Monétisation après stabilisation

- [ ] Ajouter le paiement des boosts.
  Validation : choisir fournisseur et devises, vérifier les notifications signées
  et l’idempotence, gérer échec/annulation et activer le boost une seule fois selon
  une règle d’approbation explicite. Tester en environnement de paiement de test.
  Les demandes et approbations existantes ne constituent pas un paiement effectué.
  Les paiements réels et engagements commerciaux nécessitent un périmètre explicite.

### Conditions transversales avant ouverture publique

Les tâches restent ouvertes dans « Priorité moyenne » et « Maintenance » :
installation reproductible, PostgreSQL et restauration des sauvegardes,
stockage des médias hors DEBUG, HTTPS, emails, configuration Redis, décision
Celery/workers, services systemd et CI. Prévoir aussi les contrôles d’abus et de
confidentialité déjà listés. Valider sur téléphone physique la publication,
les galeries et le zoom, les nouveaux parcours et leur utilisation au clavier.
L’intégration Celery doit préserver les tâches existantes si elle est retenue.

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

## Aperçus animés — 2026-10-09

- [x] Animer les photos des cartes : fondu, survol, flèches, compteur et points.
- [x] Conserver proportions/qualité, charger les photos supplémentaires à la demande,
  respecter la réduction des mouvements et les contrôles au clavier.
- [x] Vérifier les galeries multiples, uniques, vides, le repli et la limite de huit.
  Suite : 349 tests, dont une intégration ignorée ; parcours navigateur validé.
- [ ] Vérifier sur un téléphone physique les commandes tactiles et le rendu étroit.
