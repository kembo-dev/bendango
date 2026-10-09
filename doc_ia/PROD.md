# Bendango — produit et production

Dernière mise à jour : 2026-10-09.

## Produit actuel

Bendango combine un comparateur de prix et une plateforme d'offres de business.
Les résultats réunissent les offres publiées sur Bendango, les offres collectées
sur les sites marchands et les sources de découverte externes, notamment sociales.
Une source de découverte n'est pas une offre marchande vérifiée.

- Recherche par nom ou URL ; filtre de site, marché, ville, type d'offre, source
  et catégorie de business.
- Marché par défaut : République démocratique du Congo (`CD`). Les autres marchés
  disponibles et leurs devises sont définis dans `tracker/markets.py`.
- Une recherche anonyme par session ; inscription et connexion pour poursuivre.
- Historique des recherches pour les utilisateurs connectés.
- Publication mobile ouverte à tous les comptes connectés : `/publish/`, photos,
  titre/prix, ville/pays et WhatsApp public. Les particuliers publient sans
  approbation Pro ; leur profil reste non vérifié. Gestion dans « Mes annonces ».
- Thèmes clair et sombre, préférence locale mémorisée par le navigateur.
- Administration client Pro après approbation : tableau de bord, navigation de
  gestion, offres, catalogue, photos, boosts et édition du profil entreprise.
  Les indicateurs reflètent les seules données du business et de son utilisateur.
- Pages publiques des business et des offres ; accueil marchand paginé,
  rayons, filtres de vendeur/pays/ville et recherches communautaires séparées.
  Les annonces de l’accueil et du détail indiquent leur origine : Pro validé,
  Pro non validé ou Particulier, selon le statut actuel du profil.
- Photos uploadées optimisées en WebP qualité 85, jusqu’à 1600 px, avec
  miniatures 320 × 320 et cadre carré sans déformation ni agrandissement automatique.
  Vue agrandie facultative avec zoom jusqu’à 400 %, déplacement et navigation.
- La demande de boost et son approbation existent ; ne pas les décrire comme un
  paiement en ligne opérationnel.

## Règles métier confirmées par le code

| Fonction | Comportement actuel | Source |
| --- | --- | --- |
| Recherche par nom | Crée un SearchRun puis redirige vers les résultats suivis par UUID | `tracker/views.py:scrape_view` |
| Recherche par URL | Collecte synchrone dans la requête web ; ne crée pas le même parcours SearchRun | `tracker/services.py:process_url_and_save` |
| Recommandation marchande | Stock disponible, puis qualité, puis prix ; ce n'est pas nécessairement le prix minimum | `tracker/ranking.py:offer_sort_key` |
| Prix minimum | Minimum parmi les offres en stock, ou toutes les offres si aucune en stock | `tracker/views.py:_decorate_results` |
| Comparaison | Une offre retenue par identité marchande après classement | `tracker/views.py:_best_listing_per_merchant` |
| Offre Pro produit | Publication reliée au catalogue Product/PriceListing par une passerelle | `tracker/views.py:_sync_offer_product_bridge` |
| Boost | Produits uniquement ; demande de 7, 14 ou 30 jours, décision administrative | `tracker/views.py:pro_offer_boost_request`, `tracker/models.py:OfferBoostRequest` |
| Compte Pro | L'approbation active un BusinessProfile vérifié ; le rejet peut révoquer le profil associé | `tracker/models.py:BusinessAccountRequest` |
| Découverte publique | Mélange publications et sujets communautaires, sans identité ni UUID des recherches | `tracker/views.py:_public_discovery_feed` |

Les offres Pro sont filtrées par marché, type et catégorie. La ville privilégie
les correspondances locales ; elle n'exclut pas toutes les autres villes.
Le classement Pro place un boost actif avant la proximité, la pertinence,
la disponibilité puis le montant. Il est distinct du classement marchand collecté.

## Limites produit à rendre explicites

- Les marchés proposés dépassent les devises convertibles : les taux par défaut
  couvrent USD, CDF, EUR, XOF et XAF uniquement. Aucun taux de change en temps réel.
- Les prix non normalisables peuvent retomber sur leur montant brut dans les
  comparaisons ; corriger ce comportement avant d'afficher une économie multi-devise.
- La recherche Pro examine au plus 250 offres récentes avant de retenir les
  correspondances ; les publications plus anciennes peuvent être absentes.
- La limite anonyme repose sur la session ; ce n'est pas un quota par personne
  ni une protection contre l'abus de création de sessions.
- Les états affichés peuvent masquer un échec terminal ; détail et correction
  à suivre dans TASKS.md, sans assimiler fin de traitement et résultat réussi.

## Exploitation locale et préproduction

- Branche analysée : `clean/bendango-v2`, commit de référence `3aeba33`.
- Python 3.12.3, Django 6.1.2, environnement pyenv `bendango` lié à `.venv`.
- PostgreSQL actif constaté le 2026-10-08 pendant la refonte : connexion Django
  réussie et aucune migration restante. SQLite antérieur conservé ; import de ses
  données non vérifié. Le rôle local ne peut pas créer une base de test.
- Interface Tailwind compilée et servie localement. Avant publication, compiler
  les classes modifiées et exécuter `collectstatic` pour le manifeste WhiteNoise.
- Redis répondait `PONG` lors de l'analyse du 2026-10-07, mais `REDIS_URL` n'était
  pas configuré dans l'application. Ce constat n'est pas une garantie de disponibilité.
- Celery 5.6.3 installé et déclaré ; aucune intégration applicative Celery.
- Serveur local lancé précédemment sur `http://127.0.0.1:8000/` avec deux workers
  maison. Vérifier les processus avant de supposer qu'ils tournent encore.
- Extraction LLM configurable par profils : Ollama local, serveur compatible OpenAI
  avec ou sans clé, Bedrock. Sélection dynamique via TOML et commande `llm_config`.
  Mode `auto` par défaut : la recherche fonctionne sans modèle ni clé, avec
  extraction structurée et HTML. Modes `disabled` et `required` disponibles ;
  secours distant seulement si explicitement autorisé. Les données invérifiables
  ne créent pas de prix ; les pages en échec déclenchent une indication de résultats
  potentiellement incomplets.
  Le profil `legacy` conserve le fournisseur existant ; les profils d'exemple API
  et Studio demandent un vrai nom de modèle. Aucun appel réel à un LLM validé ici.

## Conditions avant publication

Priorités et critères détaillés dans TASKS.md : contrôle des URL sortantes,
installation reproductible, configuration des
services, emails et infrastructure adaptée aux workers.

Le dernier contrôle simulant `DEBUG=False` et une clé valide signalait
`mail.E001` : le backend email console doit être remplacé pour la production.
Les médias utilisateurs nécessitent une stratégie de service dédiée ; WhiteNoise
sert les fichiers statiques, pas les uploads en production.

## Mise à jour

Modifier ce document lorsque changent le périmètre produit, les parcours métier,
les marchés, les services disponibles ou les conditions de lancement.

## Devises de publication configurables

Les devises proposées à `/publish/`, aux offres Pro et au catalogue sont stockées
en base (`Currency`) et administrables dans `/admin/tracker/currency/` : code,
nom, symbole, activation et ordre. Dix devises des marchés existants sont
initialisées par migration. La devise du pays est présélectionnée si elle est
active ; sinon la première devise active est utilisée. Les nouvelles publications
refusent les devises désactivées ou inconnues. Les anciens montants et codes
restent conservés, y compris lors d’une édition. Sans devise active, la création
est bloquée avec une explication. Ce catalogue ne fournit aucun taux de change.
