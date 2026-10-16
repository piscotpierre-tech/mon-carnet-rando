# Mon carnet rando - Pierre

Application personnelle de randonnée, autonome et compatible GitHub Pages. 48 circuits couvrent les cinq départements normands : 28 cartes viennent du fichier fourni **Plan Balisage GTM.PDF**, document de travail de la FFRandonnée Manche du 10 février 2022, complétés par 20 circuits et GPX officiels consultés le 15 octobre 2026.

## Ce qui fonctionne

- Filtre par département (Calvados, Eure, Manche, Orne, Seine-Maritime), par distance et par montée cumulée (D+ jusqu’à 150 m, de 150 à 300 m, au-delà et valeurs inconnues).
- Recherche par nom, commune, département et numéro, sans tenir compte des accents.
- Filtres jusqu’à 6 km, plus de 6 à 10 km, plus de 10 km ; plusieurs tris.
- Favoris et repérage des circuits déjà parcourus.
- Fiches et cartes agrandissables ; les 20 nouveaux circuits ont une vraie carte IGN avec leur tracé, visible dès la liste et téléchargeable hors ligne. Une carte Leaflet avec fond OpenStreetMap en ligne permet aussi d’explorer les alentours.
- D+ et D− appariés et profils altimétriques pour 31 circuits, avec source et estimation indiquées ; 17 circuits restent explicitement non renseignés. Durée et niveau visibles sur les cartes lorsque fournis par les organismes.
- Accès direct à Google Maps depuis chaque carte et chaque fiche : itinéraire en voiture vers le départ décrit, ou simple recherche de la commune si le départ est ambigu. Liens vers les PDF officiels et téléchargement GPX.
- Tri du moins au plus de montée (ou l’inverse), avec les dénivelés inconnus toujours à la fin.
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

Voir [SOURCES.md](SOURCES.md). Les 28 cartes GTM sont des images non géoréférencées, dont les tracés n’ont pas été redessinés. Les 20 nouveaux parcours emploient les coordonnées des GPX officiels, superposées sans simplification au fond Plan IGN en EPSG:3857. Leurs cartes WebP et miniatures sont intégrées au dépôt ; les GeoJSON servent aussi à la carte interactive. Le fond Plan IGN est diffusé sous Licence Ouverte 2.0, avec attribution et date visibles sur chaque image. Les emprises, URL WMS et empreintes de contrôle sont documentées dans assets/maps/*-ign.json. Les PDF externes ne sont pas réhébergés. Les zones blanches sous les cartes ont été retirées ; la carte, sa légende, les logos et les mentions d’origine sont conservés. Cette adaptation personnelle ne prétend à aucune affiliation avec les organismes figurant sur les cartes.

L’application ne donne pas un statut actuel d’ouverture des chemins. Les distances d’origine proviennent du document de 2022, à l’exception de la précision expliquée pour le circuit 27. Les nouvelles distances proviennent des fiches officielles citées dans SOURCES.md. Aucun dénivelé ou niveau de difficulté n’est inventé.

## Vérification de cette livraison

Les tests automatisés couvrent les filtres, les limites de distance, les données invalides, l’import avec conservation des sorties, les statistiques, le chronomètre et le service worker dans un sous-dossier GitHub Pages. Les contrôles de fichiers vérifient les 48 paires d’images et 20 traces GPX / GeoJSON, les chemins relatifs, les identifiants HTML et le manifeste.

Les tests du service worker utilisent une simulation Node ; ils ne remplacent pas un test de navigateur. L’installation sur un téléphone Android réel et la disponibilité après arrêt complet de son navigateur restent à exécuter sur la version publiée.

## Fond de carte et hors ligne

Leaflet 1.9.4 est embarqué dans assets/vendor/leaflet avec sa licence. Le fond © OpenStreetMap contributors est demandé seulement pendant la consultation interactive, avec attribution visible. Les tuiles externes sont exclues du service worker et du téléchargement hors ligne ; seul le cache HTTP normal du navigateur s’applique. Les cartes IGN complètes, profils du relief, GPX et GeoJSON locaux peuvent être gardés hors ligne. Sans réseau, la carte agrandissable conserve son fond IGN ; la carte interactive utilise aussi cette image géoréférencée autour du parcours. Seule l’exploration au-delà de cette emprise nécessite le fond en ligne.

La clé de stockage et les identifiants des 28 anciens circuits sont conservés. Les exports JSON de l’ancienne version restent compatibles.

## Reconstruire les cartes IGN

`python scripts/build-maps.py` (Python 3 + Pillow) régénère les 20 cartes depuis le WMS public Plan IGN, sans télécharger de tuiles OpenStreetMap. Des identifiants peuvent limiter la reconstruction : `python scripts/build-maps.py 35`. Le fond et le tracé utilisent la même projection, la même emprise et le même ratio dans la carte et la miniature. Chaque fichier JSON de provenance contient la date, la licence, l’URL de la requête WMS, les dimensions et les empreintes des images et du GeoJSON. Après une reconstruction avec une autre emprise, reporter les bornes `bounds` dans `mapBounds` de data.js. `npm run check` vérifie ces liens et que chaque point du parcours reste dans la carte.

## Dénivelés et profils

31 circuits ont une paire D+/D− et un profil. Pour 30 circuits, `python scripts/build-elevations.py` interroge le service public IGN `elevationLine.json` et la ressource `ign_rge_alti_wld` : échantillonnage visé tous les 25 mètres, mode simple. Les montées et descentes sont cumulées séparément, sans relier les segments disjoints, puis arrondies au multiple de 5 m le plus proche. Les courbes conservent les altitudes retournées et les distances calculées sur le GPX.

Pour le circuit 41 (Goury), le relief IGN est incomplet sur la trace littorale : les altitudes complètes du GPX officiel sont utilisées et identifiées comme telles. La paire D+/D− vient entièrement de cette même source. Les anciens chiffres annoncés par les organismes restent stockés et visibles dans les fiches ; ils ne sont pas mélangés aux D+/D− estimés.

11 GPX GTM actuels ont été rattachés aux circuits anciens après vérification du nom, de la commune, de la distance de la fiche et de la longueur du GPX. Les autres circuits anciens restent sans profil, notamment lorsque la fiche actuelle annonce une autre distance. Les 28 cartes de 2022 restent les mêmes.

Les JSON `assets/profiles/{id}.json` conservent la provenance, l’empreinte SHA-256 de la géométrie, la méthode, l’échantillonnage, les cumuls bruts, la courbe et son résumé. Les données sont embarquées et ne demandent aucun appel IGN pendant l’utilisation du carnet. Le bouton hors ligne inclut désormais ces profils. Les favoris, sauvegardes, sorties et chronomètres gardent leur format précédent.
