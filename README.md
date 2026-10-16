# Mon carnet rando - Pierre

Application personnelle de randonnée, autonome et compatible GitHub Pages. Le catalogue est construit à partir du catalogue régional, des cinq catalogues départementaux repérés et de registres officiels complémentaires. Son état exact est visible dans « Couverture par département » et dans `assets/catalogue.json` : ces compteurs décrivent la version réellement construite. Les références sans GPX, les incohérences de distance et les doublons restent identifiés. La couverture exhaustive de toute la Normandie n’est pas établie.

Les 48 circuits précédents sont conservés : 28 cartes viennent du fichier fourni **Plan Balisage GTM.PDF**, document de travail de la FFRandonnée Manche du 10 février 2022, complétés par 20 circuits et GPX officiels consultés le 15 octobre 2026.

## Ce qui fonctionne

- Filtre par département (Calvados, Eure, Manche, Orne, Seine-Maritime), par distance et par montée cumulée (D+ jusqu’à 150 m, de 150 à 300 m, au-delà et valeurs inconnues).
- Recherche par nom, commune, département et numéro, sans tenir compte des accents.
- Filtres jusqu’à 6 km, plus de 6 à 10 km, plus de 10 km ; plusieurs tris.
- Favoris et repérage des circuits déjà parcourus.
- Fiches et cartes agrandissables ; les circuits supplémentaires ont une vraie carte IGN avec leur tracé, visible dès la liste et téléchargeable hors ligne. Une carte Leaflet avec fond OpenStreetMap en ligne permet aussi d’explorer les alentours.
- D+ et D− appariés et profils altimétriques pour les circuits dont le relief est calculable, avec source et estimation indiquées ; les données absentes restent explicitement non renseignées. Durée et niveau visibles sur les cartes lorsque fournis par les organismes.
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

Node 22 ou plus récent, après construction du catalogue (Python 3.12 et Pillow 12.3.0) :

```bash
python -m pip install Pillow==12.3.0
python scripts/build-catalogue.py
python -m unittest discover -s tests -p '*_test.py'
npm test
npm run check
```

Pour un développement local classique, servir le dossier avec un serveur HTTP local. Ouvrir directement `index.html` en `file://` ne suffit pas, car l’application utilise des modules JavaScript. Le service worker demande HTTPS ou localhost.

## Sources et limites des cartes

Voir [SOURCES.md](SOURCES.md). Les 28 cartes GTM sont des images non géoréférencées, dont les tracés n’ont pas été redessinés. Les parcours supplémentaires emploient les coordonnées des GPX officiels, superposées sans simplification au fond Plan IGN en EPSG:3857. Leurs cartes WebP et miniatures sont intégrées au site publié ; les cartes du grand catalogue sont reconstruites au déploiement depuis les instantanés de traces du dépôt ; les GeoJSON servent aussi à la carte interactive. Le fond Plan IGN est diffusé sous Licence Ouverte 2.0, avec attribution et date visibles sur chaque image. Les emprises, URL WMS et empreintes de contrôle sont documentées dans assets/maps/*-ign.json. Les PDF externes ne sont pas réhébergés. Les zones blanches sous les cartes ont été retirées ; la carte, sa légende, les logos et les mentions d’origine sont conservés. Cette adaptation personnelle ne prétend à aucune affiliation avec les organismes figurant sur les cartes.

L’application ne donne pas un statut actuel d’ouverture des chemins. Les distances d’origine proviennent du document de 2022, à l’exception de la précision expliquée pour le circuit 27. Les nouvelles distances proviennent des fiches officielles citées dans SOURCES.md. Aucun dénivelé ou niveau de difficulté n’est inventé.

## Vérification de cette livraison

Les tests automatisés couvrent les filtres, les limites de distance, les données invalides, l’import avec conservation des sorties, les statistiques, le chronomètre et le service worker dans un sous-dossier GitHub Pages. Les contrôles de fichiers vérifient toutes les paires d’images, les traces GPX / GeoJSON et la provenance des profils, les chemins relatifs, les identifiants HTML et le manifeste.

Les tests du service worker utilisent une simulation Node ; ils ne remplacent pas un test de navigateur. L’installation sur un téléphone Android réel et la disponibilité après arrêt complet de son navigateur restent à exécuter sur la version publiée.

## Fond de carte et hors ligne

Leaflet 1.9.4 est embarqué dans assets/vendor/leaflet avec sa licence. Le fond © OpenStreetMap contributors est demandé seulement pendant la consultation interactive, avec attribution visible. Les tuiles externes sont exclues du service worker et du téléchargement hors ligne ; seul le cache HTTP normal du navigateur s’applique. Les cartes IGN complètes, profils du relief, GPX et GeoJSON locaux peuvent être gardés hors ligne. Sans réseau, la carte agrandissable conserve son fond IGN ; la carte interactive utilise aussi cette image géoréférencée autour du parcours. Seule l’exploration au-delà de cette emprise nécessite le fond en ligne.

La clé de stockage `pierre-rando:v1` et les identifiants des 48 circuits historiques sont conservés. Les exports JSON de l’ancienne version restent compatibles.

## Reconstruire les cartes IGN

`python scripts/build-maps.py` (Python 3 + Pillow) régénère les 20 cartes depuis le WMS public Plan IGN, sans télécharger de tuiles OpenStreetMap. Des identifiants peuvent limiter la reconstruction : `python scripts/build-maps.py 35`. Le fond et le tracé utilisent la même projection, la même emprise et le même ratio dans la carte et la miniature. Chaque fichier JSON de provenance contient la date, la licence, l’URL de la requête WMS, les dimensions et les empreintes des images et du GeoJSON. Après une reconstruction avec une autre emprise, reporter les bornes `bounds` dans `mapBounds` de data.js. `npm run check` vérifie ces liens et que chaque point du parcours reste dans la carte.

## Dénivelés et profils

La version antérieure comptait 31 circuits avec une paire D+/D− et un profil. Les compteurs actuels figurent dans le rapport de couverture. Pour 30 circuits, `python scripts/build-elevations.py` interroge le service public IGN `elevationLine.json` et la ressource `ign_rge_alti_wld` : échantillonnage visé tous les 25 mètres, mode simple. Les montées et descentes sont cumulées séparément, sans relier les segments disjoints, puis arrondies au multiple de 5 m le plus proche. Les courbes conservent les altitudes retournées et les distances calculées sur le GPX.

Pour le circuit 41 (Goury), le relief IGN est incomplet sur la trace littorale : les altitudes complètes du GPX officiel sont utilisées et identifiées comme telles. La paire D+/D− vient entièrement de cette même source. Les anciens chiffres annoncés par les organismes restent stockés et visibles dans les fiches ; ils ne sont pas mélangés aux D+/D− estimés.

11 GPX GTM actuels ont été rattachés aux circuits anciens après vérification du nom, de la commune, de la distance de la fiche et de la longueur du GPX. Les autres circuits anciens restent sans profil, notamment lorsque la fiche actuelle annonce une autre distance. Les 28 cartes de 2022 restent les mêmes.

Les JSON `assets/profiles/{id}.json` conservent la provenance, l’empreinte SHA-256 de la géométrie, la méthode, l’échantillonnage, les cumuls bruts, la courbe et son résumé. Les données sont embarquées et ne demandent aucun appel IGN pendant l’utilisation du carnet. Le bouton hors ligne inclut désormais ces profils. Les favoris, sauvegardes, sorties et chronomètres gardent leur format précédent.

## Inventaire régional et reprise de l’enrichissement

`catalogue/inventaire-regional.json` contient les 985 fiches réelles des dix lots du catalogue pédestre public de Normandie Tourisme. Le total de 986 emplacements inclut une bannière promotionnelle. Répartition : Calvados 265, Eure 107, Manche 168, Orne 118, Seine-Maritime 325 et deux itinéraires interdépartementaux. 810 fiches publient un GPX dans la liste ; les 175 autres fiches ont aussi été consultées individuellement sans trouver de GPX. Les 43 distances non renseignées restent absentes dans l’inventaire ; une distance calculée sur une trace validée est explicitement présentée comme telle dans le carnet.

Les instantanés `catalogue/snapshots/*.json.gz` conservent les coordonnées, altitudes réellement présentes, liens, empreintes des GPX et résultats des contrôles. Ils évitent de dépendre de centaines de téléchargements à chaque publication. `scripts/build-catalogue.py` construit les circuits supplémentaires, leurs cartes IGN, miniatures, GeoJSON, GPX et profils. Le GPX du carnet est une résérialisation des segments officiels, avec les coordonnées des instantanés, à sept décimales pour les GPX collectés et sans liaison fictive entre segments ; le GPX original reste lié séparément. Le point de départ de ces circuits est le premier point du GPX, pas un parking vérifié. Maps utilise ses coordonnées exactes.

Les cartes et profils construits sont mis en cache dans `.generated-catalogue` et dans GitHub Actions. Ils sont publiés avec le site sans alourdir l’historique Git par des centaines d’images. Les données personnelles restent locales et les identifiants des anciens circuits ne changent pas. Les nouveaux identifiants sont réservés dans `catalogue/route-ids.json`. La construction suspend la publication si plus de 5 % des fonds de carte échouent.

Le relief IGN est préféré pour les nouvelles importations. Si ce modèle n’est pas exploitable mais que le GPX contient toutes ses altitudes, un profil entièrement issu du GPX est utilisé avec sa source indiquée. Si aucune de ces sources n’est exploitable, le relief reste inconnu. Aucune descente n’est déduite automatiquement de la montée.

La liste affiche 24 cartes à la fois ; recherche, filtres et tris portent toujours sur tous les circuits. Le hors-ligne peut être téléchargé par département et interrompu après la carte en cours. Les références encore incomplètes restent consultables dans le suivi, sans recevoir une fausse carte.

`catalogue/comparaison-seine-maritime.json` documente le premier rapprochement nominal des 291 lignes du PDESI intitulé janvier 2025. La géométrie complète a ensuite été collectée : 267 lignes sont marquées pédestres, les 24 autres pratiques sont exclues. Les cinq catalogues départementaux repérés ont été recensés. Les offices locaux, les autres registres, les GR et variantes restent à croiser ; ce chantier n’est pas annoncé comme exhaustif. Le briefing de reprise de 300 mots est conservé dans `BRIEFING.md`.

### Croisement des cinq catalogues départementaux

Les catalogues pédestres repérés ont été recensés : Calvados Tourisme 168 fiches, Attitude Manche 186, Eurêka 97, Orne Tourisme / Geotrek 158 et PDESI Seine-Maritime 267 géométries marquées pédestres. Le fichier SIG de Seine-Maritime contient 291 lignes au total, dont 24 d’autres pratiques exclues du carnet. La pagination de l’Eure produisait des doublons entre pages : un deuxième passage a permis de récupérer les 97 identifiants uniques.

Les identifiants SIT communs sont rapprochés avant import. Les sources à identifiants distincts (Geotrek et PDESI) sont ensuite comparées géométriquement. La comparaison bidirectionnelle échantillonne les lignes tous les 4 mètres, accepte un écart observé maximal de 2 mètres et exige des longueurs compatibles à 1 % ; des passages parallèles à 10 mètres et des raccourcis restent distincts dans les tests. Les sources et motifs de rapprochement restent dans le rapport.

`catalogue/inventaire-complementaire.json` contient 446 références supplémentaires et les GPX récupérés pour neuf fiches régionales auparavant incomplètes. Les 1 431 références ne sont pas autant de circuits distincts. Les circuits du PDESI sont datés de janvier 2025 et leur distance est calculée sur la géométrie publiée. Leur GPX est un export du carnet ; le GeoJSON original est lié séparément. Les fiches Orne utilisent, lorsqu’ils sont fournis, le départ, le stationnement, la durée et les dénivelés annoncés par Orne Tourisme.

La couverture exhaustive de tous les chemins normands reste non démontrée. Les fichiers manquants, variantes incohérentes, itinéraires interdépartementaux à vérifier et registres non accessibles restent visibles ou documentés. Un registre qualité Calvados ne répondait pas (HTTP 502) lors de cette collecte.

### Compléments PNR et vérification en navigateur

Le constructeur charge tous les fichiers `catalogue/inventaire-*.json` ; les identifiants source doivent être uniques et chaque nouvel identifiant de circuit est réservé dans `catalogue/route-ids.json`. Les registres Perche (131 références pédestres normandes) et Marais Cotentin-Bessin (35 références pédestres publiées) portent le suivi à **1 597 références** avant déduplication. Les 22 réparations de format GPX n’ajoutent pas de références. Les 48 fiches historiques ne sont pas remplacées. Voir SOURCES.md pour les méthodes, éditions anciennes et fichiers refusés.

La publication exécute désormais un vrai Chromium : 360, 390 et 430 px, une carte par département, profils, destinations Maps, téléchargements GPX, export/import via l’interface, état synthétique au format historique et coupure réseau après téléchargement. Un cas GeoJSON vérifie le libellé d’export GPX. Les captures et `report.json` sont conservés dans l’artifact Actions « essais-navigateur-mobile ». Une étape ajoutée au workflow n’est pas un résultat de test : consulter son succès et le rapport de la construction concernée. Le téléphone Android réel et l’installation PWA restent des contrôles distincts.
