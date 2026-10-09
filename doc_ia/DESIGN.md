# Interface et expérience Bendango

Dernière mise à jour : 2026-10-09.

## Base visuelle actuelle

Templates Django avec Tailwind CSS 4.3.3 compilé localement ; interface en français.
Les pages publiques et comptes héritent de `tracker/base.html` avec navigation
et pied de page communs. Les pages Pro utilisent `tracker/pro_base.html`, qui
hérite de cette base et remplace le cadre par une navigation administrative.
Le lien d'accès direct au contenu et le thème sont conservés.
Les styles partagés se trouvent dans `assets/css/app.css`, la feuille générée dans
`tracker/static/tracker/css/app.css`. Aucun CDN CSS ni compilation dans le navigateur.

Direction visuelle : fond pierre clair, panneaux blancs, texte ardoise, accent
émeraude `#047857` et survol `#065f46`. Typographie système, titres hiérarchisés,
bordures fines, angles arrondis et ombres légères. Les composants `button`, `panel`,
`tag`, `notice`, `metric`, `data-table` et les formulaires partagent ces règles.
Les badges d'avertissement et d'erreur conservent leurs couleurs sémantiques.

L'accueil présente « Le bon choix commence ici. », puis le formulaire : produit
au premier plan, marché/ville, filtres de type/business/source et restriction
optionnelle à un site. Le quota visiteur reste annoncé. Les champs s'empilent sur
mobile ; les tableaux peuvent défiler horizontalement dans leur conteneur.
Les labels sont associés aux champs, le focus est visible et les animations
respectent la préférence de mouvement réduit. Une certification d'accessibilité
complète reste hors du périmètre de cette refonte.

## Administration du client

`/pro/` est un espace de gestion du business approuvé : menu latéral ardoise sombre,
marque Bendango Pro, identité du business et accès à vue d'ensemble, offres,
catalogue, boosts et profil. Sur mobile, la navigation est un menu repliable natif,
utilisable sans JavaScript. Les pages d'édition gardent ce cadre commun.

La vue d'ensemble présente quatre indicateurs réels : offres publiques actives
(seulement si le business est visible), catalogue, boosts en cours, complétude du
profil. Les six dernières offres sont dans un tableau avec prix, type, statut et
accès Modifier. Les demandes de boosts, recherches récentes et priorités à traiter
restent distinctes. Aucun chiffre de ventes ou de revenus n'est simulé.

Le profil se modifie dans `/pro/?section=profile` : formulaire à deux colonnes sur
desktop, une sur mobile, erreurs et champs obligatoires visibles. Le score de
complétude porte sur six éléments (nom, présentation, logo, ville, adresse, contact) ;
il n'est pas un score de vérification. Les offres privées/désactivées et une page
business masquée ont des libellés distincts.

Validé : aperçu fictif desktop 1440 px et mobile 390 px, clair/sombre, ouverture du
menu mobile et navigation au profil. Aucun débordement du document mobile ; le
tableau défile dans son conteneur. Les données de démonstration ne sont pas dans
la base applicative. Sauvegarde et droits validés par les tests Django.

## Thème sombre

Le bouton lune/soleil dans la navigation est disponible sur les 14 pages et au
clavier. Son état `aria-pressed` indique si le thème sombre est actif et son titre
annonce le prochain thème. Sans JavaScript, le bouton reste masqué.
Le thème suit le système tant qu'aucun choix manuel n'est enregistré. La bascule
mémorise le choix localement et le conserve après rechargement/navigation.

Palette sombre : fond ardoise 950, panneaux/champs ardoise 900, textes clairs,
accents émeraude lumineux. Les notifications, badges, tableaux, cartes et focus
possèdent leurs variantes sombres ; les photos conservent leur apparence.
Validé le 2026-10-09 : bascule aller/retour, touche Entrée, persistance après
rechargement/navigation, accueil sombre et connexion mobile sans débordement.

## Parcours à préserver

- Accueil : découverte paginée des offres et sujets de recherche communautaires.
- Recherche : produit/service/offre, site optionnel, marché, ville, type, source
  et catégorie de business.
- Visiteur : indication d'une recherche gratuite par session, puis invitation
  à créer un compte ou se connecter.
- Recherche asynchrone : état, progression, sources traitées et couverture marchande.
  Le navigateur interroge l'API de statut puis recharge à la fin.
- Résultats : source, prix et devise, disponibilité, marchand et indices de fiabilité.
- Détail de recherche : le nom du modèle IA est masqué dans les informations.
- Collecte partielle : si une tâche échoue, accueil des résultats et détail affichent
  « Certaines pages n’ont pas pu être vérifiées. Les résultats peuvent être incomplets. »
  Les offres déjà trouvées restent visibles. Un complément requis indisponible
  affiche un message générique ; les détails de modèle ou clé restent opérateur.
- Espace Pro : tableaux de bord, édition de produits/offres, médias et demandes de boost.
- Pages publiques : business, offre et possibilités de contact.

## Règles d'expérience

- Préserver les filtres lors des redirections et actualisations.
- Distinguer recherche en cours, aucun résultat, résultat partiel et échec.
- Afficher explicitement la devise ; ne pas comparer des montants non normalisés.
- Réserver les badges de vérification aux états réellement établis par le code.
- Distinguer visibilité sponsorisée et qualité de l'offre lorsque le boost intervient.
- Ne pas afficher l'identité des utilisateurs ni les UUID de leurs recherches
  dans le fil public de découverte.
- Garder formulaires utilisables au clavier, labels associés, erreurs lisibles,
  contrastes suffisants et états accessibles. Ce sont des critères à vérifier,
  pas une certification d'accessibilité déjà obtenue.

## Sémantique des résultats et des badges

- `Bendango`, `Web marchand` et découverte sociale représentent trois origines.
- Un business vérifié et un marchand externe vérifié sont des notions distinctes.
- Le score de qualité marchand associe confiance, extraction et pertinence ;
  ne pas le présenter comme une probabilité certifiée.
- La recommandation met la qualité avant le prix. Afficher distinctement le
  prix minimum, le prix recommandé et la devise des statistiques.
- Les offres boostées reçoivent une indication sponsorisée. Cette visibilité
  ne doit pas être assimilée à une meilleure qualité ni à un prix inférieur.
- Les photos jointes ont priorité sur l'URL d'image de secours : image principale
  puis première image, sinon `primary_image_url` (`Offer.display_image_url`).
- Les actions médias permettent image principale, suppression et déplacement
  dans l'ordre ; elles appartiennent au business connecté et nécessitent POST.

## États de recherche et limites de l'affichage

| Situation métier | Affichage attendu à conserver ou corriger |
| --- | --- |
| En file / découverte / collecte | Attente explicite, compteurs et suivi |
| Couverture partielle | Résultats disponibles avec couverture réelle |
| Fin sans offre marchande, avec sources sociales | Sources utiles distinctes d'offres vérifiées |
| Échec | Message d'échec explicite, sans badge de succès |
| Quota anonyme utilisé | Action de recherche désactivée, liens inscription/connexion |

Le script de `scrape.html` attend 700 ms puis interroge l'API toutes les 1 500 ms.
À `data.completed`, il affiche temporairement un badge vert « Terminée » puis
recharge après 500 ms, y compris si le traitement a échoué. Les erreurs de polling
sont ignorées et retentées sans limite ni message spécifique. Ces comportements
actuels sont des points à corriger, pas la définition souhaitée des états.

La barre de progression mesure les marchands trouvés par rapport à l'objectif,
pas le pourcentage de pages traitées ni une estimation du temps restant.
Le filtre de ville favorise les offres locales ; ne pas le décrire comme une
exclusion stricte de toute offre située ailleurs.

## Contrôles visuels à prévoir

Tester au minimum accueil vide/rempli, recherche active/partielle/échouée,
offre sponsorisée, média manquant et quota anonyme atteint ; vérifier clavier,
mobile, conservation des filtres et annonces accessibles des changements d'état.
Contrôles réalisés pour cette refonte : accueil vide sur desktop (1440 px) et
mobile (390 px), connexion mobile, ouverture du champ de site optionnel. Les états
avec données, échec et quota atteint restent à vérifier visuellement ; les tests
Django couvrent leurs parcours mais ne remplacent pas ces contrôles navigateur.

## Améliorations ouvertes

Les uploads sont maintenant validés et réencodés. Les erreurs réseau et d'extraction
doivent rester compréhensibles pour l'utilisateur. Toute modification des cartes,
du classement, des badges ou du suivi doit être contrôlée sur desktop et mobile.

## Mise à jour

Documenter ici les changements visibles, états, textes structurants, composants,
parcours et contraintes d'accessibilité ; référencer leurs validations dans MEMORY.md.

## Publication depuis le téléphone

Bouton « + Publier » public (connexion nécessaire), « Mes annonces » pour les
comptes connectés et raccourci « Publication mobile » dans la navigation Pro.
`quick_publish.html` garde un cadre compact et une action fixée en bas avec
safe-area. Avec JavaScript, trois étapes : photos, détails, contact/publication.
Sans JavaScript, tous les champs et le bouton d'envoi restent disponibles.

Appareil photo natif via capture=environment, galerie multiple, miniatures,
suppression et choix de couverture avant création. La disponibilité de la caméra
reste celle du navigateur/téléphone. Aucun accès caméra n'est demandé au chargement.
Aperçu titre/prix/ville/photo, thème clair/sombre, retour entre étapes et erreurs
serveur sur la bonne étape. Les photos doivent être resélectionnées après une
soumission invalide ; aucun brouillon ni photo n'est conservé dans localStorage.
Le numéro WhatsApp est explicitement annoncé public. HEIC/RAW non pris en charge ;
utiliser JPEG/PNG/WebP/GIF. En édition, les photos existantes sont conservées,
les nouvelles ajoutées ; la couverture existante reste inchangée.

« Mes annonces » propose Voir, Modifier et Masquer/Réactiver ; la visibilité
réelle tient aussi compte de la page du vendeur. Les particuliers sont marqués
non vérifiés. Le cadre administratif Pro et ses formulaires complets sont conservés.

## Galerie publique animée (2026-10-09)

La photo principale et l'ancienne grille deviennent un carrousel unique sur le
haut de chaque offre : transition horizontale douce, miniatures sélectionnables,
compteur et flèches. Balayage natif sur téléphone, navigation au clavier
(gauche/droite, Home/End), textes alternatifs et annonce des changements manuels.
La couverture choisie est affichée en premier, puis les autres photos dans leur
ordre. Une photo unique reste sans commandes ; absence de photo sans bloc vide.

Le bouton « Diaporama » lance un cycle de cinq secondes, avec Pause. Il est
facultatif, arrêté par la navigation manuelle/le toucher, suspendu au survol,
au focus dans les photos, hors écran et onglet masqué. La préférence de réduction
des animations désactive le diaporama et rend les transitions immédiates.
Sans JavaScript, défilement horizontal et liens des miniatures restent disponibles.
Contrôles réels sur l'offre Esika : images chargées, flèches, miniature, clavier,
cycle automatique 1/2 → 2/2 et pause ; capture conservée hors dépôt. Le balayage
matériel et la réduction de mouvement sur téléphone restent à vérifier.

## Cadre et poids des photos

La galerie réserve un cadre carré, jusqu'à 640 × 640 px sur desktop, adapté à la
largeur mobile. La photo entière est centrée sur un fond neutre clair/sombre ;
proportions conservées, aucune déformation et aucun agrandissement au-delà des
pixels disponibles. Miniatures dédiées 320 × 320, recadrées au centre puis réduites
à la taille visuelle des boutons. Les sources plus petites restent centrées sans
agrandissement dans leur miniature. Les uploads produisent du WebP qualité 85
avec un côté maximal de 1600 px ; orientation corrigée, transparence conservée.

Les images externes gardent leur URL et le même cadre d'affichage. Les petites
photos ne gagnent pas de détails : sur l'offre Esika, les deux sources de 64 × 64
sont désormais affichées à cette taille, sans le flou de leur ancien agrandissement.

## Choix de devise à la publication

Le champ Devise devient une liste : code et nom explicite, par exemple
« CDF — Franc congolais ». Prix et devise occupent deux colonnes dès sm,
et sont empilés sur petit écran. L’aperçu utilise toujours le code sélectionné.
La liste suit l’activation et l’ordre de l’administration sans redémarrage.
Une devise historique indisponible est signalée comme conservée en édition.
Sans devise active, le formulaire annonce l’indisponibilité de publication.

## Zoom des photos (2026-10-09)

Cliquer une photo ou « Agrandir » ouvre une vue occupant l’écran, disponible
aussi pour une photo unique. Barre supérieure photo/compteur/Fermer ; commandes
inférieures +, − et remise à 100 %, puis précédent/suivant si plusieurs photos.
Zoom de 100 à 400 %, molette et pincement prévus ; déplacer par glisser quand
l’image déborde. Les zones de commande sont d’au moins 44 px, avec safe-area.
Les proportions sont conservées, la qualité reste limitée par la source.

Le diaporama s’arrête à l’ouverture. Changer de photo réinitialise le zoom et
synchronise la galerie. Échap ferme ; flèches changent de photo, +/− ajustent
le zoom, 0 le réinitialise. La modale conserve le focus et le rend à l’ouvreur.
En absence de JavaScript, les liens ouvrent le fichier image. Contrôles desktop
réalisés sur la moto et une galerie de deux photos ; pincement matériel et
rendu sur téléphone réel restent à vérifier.

## Origine des annonces

Sous le nom public de l’auteur, les cartes de l’accueil affichent un badge :
« Pro validé » (bouclier/coché, vert), « Pro non validé » (horloge, ambre) ou
« Particulier » (personne, neutre). Libellés explicites en plus des couleurs et
icônes décoratives ; tooltip précisant que la validation concerne le compte.
Le détail d’offre reprend le même badge. « Publié sur Bendango » devient neutre
et « Sponsorisé » reste un indicateur distinct. Les recherches communautaires
restent identifiées comme recherches, sans badge de vendeur. Le texte d’introduction
mentionne les professionnels et les particuliers.
