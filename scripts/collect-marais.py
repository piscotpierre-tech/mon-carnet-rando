"""Collect only the 35 pedestrian walks published by DESMARAIS DU PARC.

The ArcGIS register also contains unpublished variants and other practices.
Keep those exclusions explicit. Source coordinates are retained as candidates,
never promoted to a verified parking. Original GPXs are preserved byte for byte.
"""
import concurrent.futures
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import re
import shutil
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
source = importlib.import_module('collect-normandie')
prepare = importlib.import_module('prepare-catalogue')
comparison = importlib.import_module('trace-comparison')
ENDPOINT = 'https://services5.arcgis.com/2wtm4KHYRBa9T8Yt/arcgis/rest/services/APIRANDO_CIRCUITS/FeatureServer/0/query'
OFFICIAL = 'https://parc-cotentin-bessin.fr/desmarais-du-parc-toutes-les-balades-pres-de-chez-vous'
APP = 'http://pnrmcb.maps.arcgis.com/apps/webappviewer/index.html?id=3b8cef41bbb840eab30ded104d0188f6'
FIELDS = ['FID', 'ID', 'NOMCIRCUIT', 'ID_CIRCUIT', 'ID_ARBO', 'TYPE', 'COM_DEPART',
          'C_DEP', 'AGO_APPLI', 'AGO_PDF', 'AGO_GPX', 'AGO_COORD', 'PARKING',
          'DIFFICULTE', 'BALISAGE', 'MAJ', 'SOURCE', 'DIST_KM', 'DUREE_H', 'XW84', 'YW84']
QUERY = ENDPOINT + '?' + urllib.parse.urlencode({
    'where': '1=1', 'outFields': ','.join(FIELDS), 'returnGeometry': 'false', 'f': 'json',
})
DOCUMENT_CACHE = source.CACHE / 'marais-documents'
DOCUMENT_CACHE.mkdir(exist_ok=True)
ORIGINALS = ROOT / 'catalogue/sources/marais'


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def number(value):
    match = re.fullmatch(r'\s*(\d+(?:[.,]\d+)?)\s*km\s*', value or '', re.I)
    return float(match[1].replace(',', '.')) if match else None


def duration(value):
    match = re.fullmatch(r'\s*(\d+)h(?:\s*(\d+))?\s*', value or '')
    return int(match[1]) * 60 + int(match[2] or 0) if match else None


def pdf_metadata(url):
    if not url:
        return {'sourcePdfStatus': 'sans-pdf-publie'}
    path = DOCUMENT_CACHE / (hashlib.sha256(url.encode()).hexdigest() + '.pdf')
    try:
        if path.exists():
            raw = path.read_bytes()
        else:
            request = urllib.request.Request(url, headers={'User-Agent': 'MonCarnetRando/1.0'})
            with urllib.request.urlopen(request, timeout=40) as response:
                raw = response.read()
            assert raw.startswith(b'%PDF-'), 'Le téléchargement n’est pas un PDF'
            path.write_bytes(raw)
        assert raw.startswith(b'%PDF-'), 'Le téléchargement n’est pas un PDF'
        return {'sourcePdfStatus': 'pdf-recupere', 'sourcePdfSha256': hashlib.sha256(raw).hexdigest(),
                'sourcePdfBytes': len(raw)}
    except Exception as error:
        return {'sourcePdfStatus': 'pdf-indisponible', 'sourcePdfIssue': str(error)}


def locate(record):
    """Resolve an actual point into an explicit official commune/department.

    A first GPX point is not asserted to be the source's parking. If the GPX
    fails, only an exact, unambiguous official commune name can supply a dept.
    """
    if record.get('segments'):
        coordinate = record['segments'][0][0][:2]
        params = {'lon': coordinate[0], 'lat': coordinate[1],
                  'fields': 'nom,code,codeDepartement,codesPostaux', 'format': 'json'}
        method = 'Premier point du GPX géolocalisé par l’API officielle des communes ; ce point n’est pas un parking vérifié.'
    else:
        coordinate = None
        params = {'nom': record['town'], 'fields': 'nom,code,codeDepartement', 'limit': 10}
        method = 'Nom de commune publié rapproché exactement de l’API officielle des communes.'
    url = 'https://geo.api.gouv.fr/communes?' + urllib.parse.urlencode(params)
    raw = source.get(url)
    rows = json.loads(raw)
    if coordinate is None:
        rows = [r for r in rows if prepare.normal(r['nom']) == prepare.normal(record['town'])]
    # The park's public pedestrian selection is confined to Manche/Calvados.
    rows = [r for r in rows if r.get('codeDepartement') in ['14', '50']]
    assert len(rows) == 1, 'Commune/département non établis de manière univoque'
    record.update(department=rows[0]['codeDepartement'], sourceAdministrativeLocation={
        'url': url, 'sha256': hashlib.sha256(raw.encode()).hexdigest(),
        'method': method, 'coordinate': coordinate, 'commune': rows[0],
    })


def detail(attributes, dataset_hash):
    a = attributes
    fid = a['FID']
    record = {
        'sourceId': f'MARAIS-CD-{fid}', 'sourceFeatureId': fid, 'sourceObjectIdField': 'FID',
        'sourceCircuitCode': clean(a['ID_CIRCUIT']), 'sourceArboCode': clean(a['ID_ARBO']),
        'name': clean(a['NOMCIRCUIT']), 'town': clean(a['COM_DEPART']), 'department': None,
        'km': number(a['DIST_KM']), 'official': OFFICIAL,
        'gpxSource': clean(a['AGO_GPX']) or None, 'pdf': clean(a['AGO_PDF']) or None,
        'sourcePdf': clean(a['AGO_PDF']) or None, 'sourcePractice': a['TYPE'],
        'sourcePublished': a['AGO_APPLI'], 'sourceOrigin': clean(a['SOURCE']),
        'sourceUpdatedAt': clean(a['MAJ']).replace('_', '-'),
        'sourceEdition': 'PNR Marais du Cotentin et du Bessin · mise à jour source ' + clean(a['MAJ']).replace('_', '-'),
        'sourceDatasetUrl': QUERY, 'sourceDatasetSha256': dataset_hash,
        'sourceApi': ENDPOINT + '?' + urllib.parse.urlencode({
            'where': f'FID={fid}', 'outFields': ','.join(FIELDS), 'returnGeometry': 'false', 'f': 'json',
        }),
        'sourceApplication': APP,
        'sourceParkingDescription': clean(a['PARKING']) or None,
        'sourceDifficulty': clean(a['DIFFICULTE']) or None,
        'sourceMarking': clean(a['BALISAGE']) or None,
        'sourceDurationMinutes': duration(a['DUREE_H']),
        'sourceGoogleMaps': clean(a['AGO_COORD']) or None,
        'sourceXYLocation': [a['XW84'], a['YW84']],
        'sourceLocationNote': 'Coordonnées XW84/YW84 et destination Google Maps conservées séparément. Aucune n’est déclarée parking vérifié.',
    }
    record = prepare.validate(record)
    # Preserve even a distance-mismatched original, for transparent reinspection.
    if record.get('gpxSha256'):
        cached = prepare.CACHE / (hashlib.sha256(record['gpxSource'].encode()).hexdigest() + '.gpx')
        name = f"{record['sourceCircuitCode']}-{fid}.gpx"
        original = ORIGINALS / name
        shutil.copyfile(cached, original)
        record['sourceOriginalGpx'] = original.relative_to(ROOT).as_posix()
        assert hashlib.sha256(original.read_bytes()).hexdigest() == record['gpxSha256']
        xml = ET.fromstring(prepare.normalize_gpx(original.read_bytes())[0])
        record['sourceGpxTrackCount'] = sum(c.tag.split('}')[-1] in ['trk', 'rte'] for c in xml)
        if record['sourceGpxTrackCount'] > 1:
            record['sourceGpxIssue'] = 'Le GPX publié contient plusieurs traces ; elles sont conservées sans sélection arbitraire.'
    if record.get('segments'):
        record['officialLocation'] = record['segments'][0][0][:2]
        record['officialLocationPrecision'] = 'gpx'
        match = re.search(r'[?&]destination=(-?[\d.]+),(-?[\d.]+)', record['sourceGoogleMaps'] or '')
        candidates = {'XW84/YW84': record['sourceXYLocation']}
        if match:
            candidates['AGO_COORD'] = [float(match[2]), float(match[1])]
        record['sourceCoordinateOffsetsMetres'] = {
            key: round(prepare.distance(record['officialLocation'], point), 1)
            for key, point in candidates.items() if all(isinstance(v, (int, float)) for v in point)
        }
    try:
        locate(record)
    except Exception as error:
        record['administrativeLocationIssue'] = str(error)
        if record['status'] == 'trace-verifiee':
            record.update(status='commune-a-verifier', issue='Commune/département à confirmer par une source officielle.')
    record.update(pdf_metadata(record['sourcePdf']))
    return record


def reconcile(records):
    """Supply audit hints only; the build remains responsible for deduplication."""
    previous = {}
    for path in sorted((ROOT / 'catalogue/snapshots').glob('*.json.gz')):
        if path.name == 'marais.json.gz':
            continue
        for record in json.loads(gzip.decompress(path.read_bytes())):
            if record.get('segments'):
                previous[record['sourceId']] = record
    shapes = [(sid, comparison.describe(record['segments'])) for sid, record in previous.items()]
    for record in records:
        if record['status'] != 'trace-verifiee':
            continue
        shape = comparison.describe(record['segments'])
        matches = [sid for sid, other in shapes if comparison.equivalent(shape, other)]
        record['geometryReconciliation'] = {
            'comparedSnapshotRecords': len(shapes), 'equivalentSourceIds': matches,
            'method': 'Comparaison bidirectionnelle à pas de 4 m, écart maximal 2 m et longueur compatible à 1 %. Indice préalable ; déduplication finale par le pipeline.',
        }
    return len(shapes)


def collect():
    raw = source.get(QUERY)
    dataset = json.loads(raw)
    assert not dataset.get('exceededTransferLimit'), 'Le serveur a tronqué la sélection'
    assert dataset.get('objectIdFieldName') == 'FID', 'Identifiant ArcGIS changé'
    features = [f['attributes'] for f in dataset['features']]
    assert len({a['FID'] for a in features}) == len(features)
    selected = [a for a in features if a['TYPE'] == 'A pied' and a['AGO_APPLI'] == 'OUI']
    assert len(features) == 144 and len(selected) == 35, 'Le registre a changé : réexaminer la sélection'
    dataset_hash = hashlib.sha256(raw.encode()).hexdigest()
    ORIGINALS.mkdir(parents=True, exist_ok=True)
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for i, record in enumerate(pool.map(lambda a: detail(a, dataset_hash), selected), 1):
            records.append(record)
            print(f"DESMARAIS {i}/{len(selected)} · {record['sourceId']} · {record['status']}", flush=True)
    compared = reconcile(records)
    sources = []
    for department in ['14', '50']:
        local = [r for r in records if r['department'] == department]
        sources.append({
            'department': department, 'source': OFFICIAL, 'api': QUERY, 'total': len(local),
            'announcedTotal': len(local), 'collectedAll': len(records) == len(selected),
            'registerTotal': len(features), 'registerPedestrianTotal': sum(a['TYPE'] == 'A pied' for a in features),
            'registerPublishedPedestrianTotal': len(selected),
            'validatedTraces': sum(r['status'] == 'trace-verifiee' for r in local),
            'sourceDatasetSha256': dataset_hash,
            'note': 'Sélection explicite TYPE=A pied et AGO_APPLI=OUI ; édition propre à chaque fiche (majoritairement décembre 2019). Variantes non publiées exclues. Coordonnées source non assimilées à des parkings vérifiés.',
        })
    inventory = {
        'checkedAt': source.DATE, 'sources': sources,
        'records': [{k: v for k, v in r.items() if k != 'segments'} for r in records], 'overrides': [],
        'selection': {'registerTotal': len(features), 'publishedPedestrianTotal': len(selected),
                      'excluded': [{'sourceFeatureId': a['FID'], 'name': a['NOMCIRCUIT'],
                                    'practice': a['TYPE'], 'published': a['AGO_APPLI'],
                                    'reason': 'Autre pratique' if a['TYPE'] != 'A pied' else 'Variante non publiée (AGO_APPLI différent de OUI)'}
                                   for a in features if a not in selected]},
        'geometryComparison': {'snapshotRecords': compared,
                               'validatedWithEquivalentExistingGeometry': sum(bool(r.get('geometryReconciliation', {}).get('equivalentSourceIds')) for r in records),
                               'note': 'Ce bilan ne mesure pas des ajouts nets : la construction applique encore ses contrôles et rapproche les 48 fiches historiques.'},
    }
    (ROOT / 'catalogue/inventaire-marais.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n')
    (ROOT / 'catalogue/snapshots/marais.json.gz').write_bytes(gzip.compress(json.dumps(records, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0))
    print(json.dumps({'references': len(records), 'validatedTraces': sum(r['status'] == 'trace-verifiee' for r in records),
                      'originalGpxPreserved': sum(bool(r.get('sourceOriginalGpx')) for r in records),
                      'pdfDownloaded': sum(r['sourcePdfStatus'] == 'pdf-recupere' for r in records),
                      **inventory['geometryComparison']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    collect()
