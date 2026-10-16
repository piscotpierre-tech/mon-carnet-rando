# Vérification de la publication du 16 octobre 2026

[Application publiée](https://piscotpierre-tech.github.io/mon-carnet-rando/). Version construite : `b927c0f`. [Exécution Actions](https://github.com/piscotpierre-tech/mon-carnet-rando/actions/runs/38925991292). Exécution réussie. Les fichiers publics ont été contrôlés le 16 octobre 2026 à 15 h 48 UTC, puis l’accueil et la nouvelle carte ont été vérifiés dans le navigateur.

## Compteurs réellement publiés

**1329 parcours publiés : 48 historiques et 1281 ajouts ; 1617 références inventoriées, dont 1422 rattachées et 195 à compléter ou clarifier.**

1312 parcours possèdent un GPX local, dont 207 exports depuis un GeoJSON officiel. Les 17 sans GPX local sont des historiques conservés. 1303 parcours ont un profil et une paire D+/D− : 1293 issus du relief IGN et 10 des altitudes du GPX officiel. Les 26 D+ et 26 D− inconnus restent non renseignés, vérifiés avec le véritable calcul d’affichage `routeElevation`. Les références sont des fiches sources ; plusieurs peuvent correspondre au même parcours. Le nombre de circuits du carnet inclut les 48 historiques. Il ne prouve pas que tous les chemins officiels de Normandie sont réunis, ni que tous les rapprochements nominaux sont résolus.

| Département | Parcours publiés | Profils et D+/D− | Références rattachées / repérées | À compléter |
| --- | ---: | ---: | ---: | ---: |
| Calvados (14) | 245 | 244 | 245 / 273 | 28 |
| Eure (27) | 45 | 45 | 44 / 108 | 64 |
| Manche (50) | 228 | 208 | 211 / 215 | 4 |
| Orne (61) | 354 | 354 | 404 / 407 | 3 |
| Seine-Maritime (76) | 457 | 452 | 518 / 612 | 94 |
| Département non confirmé | — | — | 0 / 2 | 2 |

| État des références | Nombre |
| --- | ---: |
| Intégrée comme ajout | 1281 |
| Déjà présente parmi les historiques | 14 |
| Doublon géométrique exact | 51 |
| Équivalence géométrique approchée | 76 |
| Sans GPX publié | 176 |
| Distance à vérifier | 13 |
| Fichier de trace inexploitable | 4 |
| Département à vérifier | 2 |

L’inventaire comporte 985 références régionales, 446 complémentaires départementales, 131 du Perche, 35 des Marais Cotentin-Bessin et 20 de Caux Seine, soit 1617 références après rapprochement des identifiants SIT communs et avant comparaison des géométries. Les 48 historiques sont conservés séparément. Deux références restent sans département attribué avec certitude.

## Compatibilité des données

Les 48 identifiants historiques et la clé `pierre-rando:v1` sont conservés. Les 1121 identifiants de la première publication étendue restent résolus : 1117 identifiants inchangés et quatre alias, aucun perdu. Les quatre rattachements sont 2323→1622, 2298→1610, 2282→1620 et 2302→1611. Les 1328 identifiants de la publication intermédiaire restent tous inchangés et disponibles. Les listes de référence sont archivées dans [COMPATIBILITE.md](COMPATIBILITE.md). La table publiée contient 141 alias valides au total.

Le véritable validateur JavaScript a relu des sauvegardes synthétiques contenant chaque identifiant précédemment publié : favoris, sorties, notes, dates, kilomètres, durées, notes de satisfaction et chronomètre restent cohérents. Les alias ciblent des fiches réellement présentes. Les données personnelles restent stockées sur l’appareil ; les tests du navigateur emploient des états synthétiques dans des contextes isolés.

## Contrôles exécutés

- 30 tests JavaScript et 27 tests Python sur la construction complète ; aucun test réservé au catalogue complet ignoré dans Actions.
- Contrôle de chaque circuit construit : identifiants uniques, carte et miniature, coordonnées, GPX, GeoJSON, fond IGN, provenance, profil et cohérence des cumuls D+/D− lorsqu’ils existent. Chemins relatifs vérifiés dans `/mon-carnet-rando/`.
- Chromium aux largeurs 360, 390 et 430 pixels : une fiche et une carte par département, profils, destinations Google Maps, absence de débordement horizontal, export/import de sauvegarde et conservation du chronomètre historique.
- Téléchargements GPX comparés octet par octet avec les fichiers des circuits. Un export issu du GeoJSON est explicitement identifié et conserve le lien vers le GeoJSON original.
- Hors ligne à 390 pixels : rechargement fourni par le service worker, aucune requête reçue par le serveur pendant ce rechargement, sonde réseau fraîche bloquée, fiche, profil, carte IGN, fond IGN interactif et GPX utilisables. Le téléchargement GPX utilise des octets locaux via un Blob pour éviter la navigation native vers le fichier.
- Vérification HTTP des ressources publiées sur les cinq départements et sur le nouveau circuit 2067 ; vérification visuelle du site public et des captures mobiles.

Chromium réinitialise son indication `navigator.onLine` après un rechargement contrôlé, alors que la sonde réseau est déjà bloquée et le serveur n’a reçu aucune requête. Le scénario réapplique une transition réseau réelle avant de vérifier le bandeau ; il ne modifie pas `navigator.onLine` et n’injecte aucun événement de connexion. L’installation PWA, l’arrêt complet du navigateur et le mode avion sur un téléphone physique restent des contrôles distincts à effectuer.

Les captures et le rapport du navigateur sont conservés sept jours dans [l’artifact Actions essais-navigateur-mobile](https://github.com/piscotpierre-tech/mon-carnet-rando/actions/runs/38925991292/artifacts/12056792327). Son empreinte ZIP SHA-256 est `3f773a0b1369da09716f207a22a7b48fe13584a5aa4389402ef21a632edd0f46`. Le contrôle statique couvre 2658 images et 1303 profils, soit 517,50 Mo pour les cartes et miniatures.

## Corrections et preuves de sources

Vingt-deux GPX officiels ont été récupérés sans modification des coordonnées : neuf fichiers avec octets NUL après la fermeture XML, dix avec balises HTML `br` non fermées dans les descriptions et trois en Latin-1 non déclaré. Les empreintes des originaux et des fichiers validés restent distinctes ; l’overlay ne remplace pas les instantanés initiaux.

La portion « GR21 sur chemin du Camp de César », source `CD76-PDESI-2025-13592`, contient cinq points valides sur 355,316 mètres. Le producteur la marque explicitement pédestre. Un seuil interne de plus de cinq points la rejetait ; la collecte, la relecture GPX et le contrôle des fichiers acceptent maintenant le minimum géométrique de deux points par segment, en conservant les contrôles de coordonnées et de longueur. La récupération provient du cache source dont l’empreinte correspond à l’instantané initial. Le circuit 2067 conserve les coordonnées, une distance calculée et le libellé de portion ; son GPX est un export du GeoJSON officiel.

Les cartes du grand catalogue ont un fond Plan IGN réel. Les 28 cartes historiques de 2022 sont préservées comme images du document GTM. Le premier point d’un tracé n’est pas présenté comme un parking vérifié. Les valeurs d’altitude, départs ou projections inconnus ne sont pas déduits arbitrairement.

## Travail restant

La couverture exhaustive de la Normandie reste non démontrée. Priorités :

1. Reprendre les 176 références sans GPX par organisme : Calvados 22, Eure 62, Seine-Maritime 92.
2. Vérifier les 13 distances incohérentes avec les producteurs et les éditions. Trois GPX Marais réunissent plusieurs parcours ; aucun segment n’a été choisi arbitrairement.
3. Traiter explicitement deux KML, obtenir le CRS déclaré du fichier des Marais de l’Aure et retrouver le GPX Marais en HTTP 404.
4. Reprendre les registres circuits qualité Calvados et Normandie-Maine (HTTP 502 lors des contrôles) ainsi que FFRandonnée Normandie (HTTP 403). Leurs totaux actuels sont inconnus.
5. Examiner les 41 rapprochements nominaux du Perche, les offices restants, les GR, Boucles de Seine et les six circuits patrimoniaux Caux à qualifier. Un nom proche ne prouve pas un doublon.

Sources et méthodes détaillées : [SOURCES.md](SOURCES.md). Reprise : [BRIEFING.md](BRIEFING.md).

## Empreintes des fichiers publics contrôlés

| Fichier | SHA-256 |
| --- | --- |
| `catalogue-routes.js` | `d39ec1029bb390b6cae1ec2332bed511a971c60248a3a1773d3860eb295b6591` |
| `assets/catalogue.json` | `1ba09580e090617aedf034423190dfca4506efee8ffd32d99f1b15d1c40310a8` |

Témoins HTTP contrôlés : circuits 1001, 1298, 1373, 1541, 1659 et 2067 ; cinq fichiers par circuit (carte, miniature, GeoJSON, GPX, profil), tous HTTP 200 avec contenu validé. Le catalogue complet est contrôlé avant publication ; ce sondage public porte sur 30 fichiers.
