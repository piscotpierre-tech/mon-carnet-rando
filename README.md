# Mon carnet rando - Pierre

Application personnelle de randonnée, autonome et compatible GitHub Pages. Les 28 cartes viennent du fichier fourni **Plan Balisage GTM.PDF**, document de travail de la FFRandonnée Manche du 10 février 2022.

## Ce qui fonctionne

- Recherche par nom, commune et numéro, sans tenir compte des accents.
- Filtres jusqu’à 6 km, plus de 6 à 10 km, plus de 10 km ; plusieurs tris.
- Favoris et repérage des circuits déjà parcourus.
- Fiches et cartes agrandissables, déplacement de la carte après zoom.
- Recherche du lieu de départ dans Google Maps, sauf départs ambigus.
- Chronomètre avec pause, reprise et conservation au rechargement.
- Journal : date, kilomètres réels, durée, note et souvenir ; modification et suppression.
- Statistiques de sorties, kilomètres réels et circuits distincts.
- Export JSON et import validé, en ajoutant les données sans remplacer les sorties locales de même identifiant.
- Téléchargement des cartes, fonctionnement hors ligne via service worker et installation PWA lorsque le navigateur le propose.

Les données personnelles restent dans le navigateur. Aucun compte, serveur de données, suivi publicitaire ou synchronisation.

## Mettre sur GitHub Pages

1. Créer un dépôt dédié, par exemple `mon-carnet-rando`, dans le compte GitHub de Pierre.
2. Ajouter **le contenu de ce dossier à la racine du dépôt**, y compris `.github/workflows/pages.yml`, puis pousser sur `main`.
3. Dans **Settings > Pages > Build and deployment**, sélectionner **GitHub Actions** comme source.
4. Lancer le workflow « Publier le carnet sur GitHub Pages » dans Actions si nécessaire.
5. Attendre son succès puis ouvrir l’URL retournée par l’étape de publication.

Le workflow vérifie les fonctions et les chemins avant de publier les fichiers publics. Il ne copie ni les tests, ni les scripts, ni les fichiers Git dans le site publié. Les chemins sont relatifs : l’application fonctionne aussi dans `/mon-carnet-rando/`.

La disponibilité de Pages sur un dépôt privé dépend de l’offre GitHub. Si tu choisis un dépôt public, les cartes et le code du dépôt sont publics. Tes sorties restent dans ton navigateur et ne sont pas envoyées sur GitHub.

Documentation de la configuration : https://docs.github.com/fr/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages

## Utiliser sur le téléphone

Ouvrir l’URL publiée dans le navigateur. Dans Mon carnet, télécharger les cartes avant de partir. Le navigateur doit autoriser le stockage ; le système peut ensuite libérer cet espace. Vérifier l’état hors ligne avant une sortie sans réseau.

Le chronomètre se base sur l’horloge du téléphone, pas sur une tâche qui doit rester active en arrière-plan. Les changements manuels d’heure peuvent modifier la durée. Aucun suivi GPS, navigation en direct ou mesure automatique de distance n’est fourni.

Exporter régulièrement les données depuis Mon carnet. Une suppression des données du navigateur ou une navigation privée peut faire perdre les enregistrements locaux.

## Vérifier et développer

Node 22 ou plus récent, sans installation de dépendances :

```bash
npm test
npm run check
```

Pour un développement local classique, servir le dossier avec un serveur HTTP local. Ouvrir directement `index.html` en `file://` ne suffit pas, car l’application utilise des modules JavaScript. Le service worker demande HTTPS ou localhost.

## Sources et limites des cartes

Voir [SOURCES.md](SOURCES.md). Les cartes ne sont pas des traces géoréférencées. Leurs tracés n’ont pas été redessinés. Les zones blanches sous les cartes ont été retirées ; la carte, sa légende, les logos et les mentions d’origine sont conservés. Cette adaptation personnelle ne prétend à aucune affiliation avec les organismes figurant sur les cartes.

L’application ne donne pas un statut actuel d’ouverture des chemins. Les distances proviennent du document de 2022, à l’exception de la précision expliquée pour le circuit 27. Aucun dénivelé ou niveau de difficulté n’est inventé.

## Vérification de cette livraison

Les tests automatisés couvrent les filtres, les limites de distance, les données invalides, l’import avec conservation des sorties, les statistiques, le chronomètre et le service worker dans un sous-dossier GitHub Pages. Les contrôles de fichiers vérifient les 28 paires d’images, les chemins relatifs, les identifiants HTML et le manifeste.

Les tests du service worker utilisent une simulation Node ; ils ne remplacent pas un test de navigateur. La vérification visuelle réelle à 360/390/430 pixels, l’installation sur Android et la disponibilité après arrêt complet du navigateur restent à exécuter sur la version publiée.
