"""Audit the PNR du Perche's public walking catalogue against saved geometries.

Only French published walking records with an explicit Normandy INSEE commune
are retained. This is a portal cross-check, never a claim of regional coverage.
No official text or photographs are copied. Outputs default to a temporary audit
directory and do not modify the existing inventories or historical route IDs.
"""
import argparse
import concurrent.futures
import datetime
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
prepare = importlib.import_module('prepare-catalogue')
comparison = importlib.import_module('trace-comparison')
API = 'https://geotrek-perche.makina-corpus.net/api/v2/'
PORTAL = 'https://rando-perche.fr/'
DEPARTMENTS = {'14': 'Calvados', '27': 'Eure', '50': 'Manche', '61': 'Orne', '76': 'Seine-Maritime'}
FIELDS = ','.join([
    'id', 'name', 'practice', 'published', 'city_codes', 'departure_city_code',
    'departure_geom', 'departure', 'arrival', 'advised_parking', 'parking_location',
    'ascent', 'descent', 'length_2d', 'duration', 'gpx', 'url', 'geometry',
    'update_datetime', 'children', 'parents', 'external_id',
])


def normalize(value):
    text = unicodedata.normalize('NFKD', value or '').encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '', text)


def canonical(segments):
    """Same six-decimal exact path normalization as build-catalogue.py."""
    parts = []
    for segment in segments:
        points = [(round(p[0], 6), round(p[1], 6)) for p in segment]
        points = [p for i, p in enumerate(points) if not i or p != points[i - 1]]
        if len(points) > 2 and points[0] == points[-1]:
            points.pop()
            def rotation(values):
                smallest = min(values)
                return min(tuple(values[i:] + values[:i]) for i, p in enumerate(values) if p == smallest)
            key = min(rotation(points), rotation(points[::-1]))
        else:
            key = min(tuple(points), tuple(points[::-1]))
        parts.append(key)
    return hashlib.sha256(repr(sorted(parts)).encode()).hexdigest()


def get_json(url, raw_dir):
    target = raw_dir / (hashlib.sha256(url.encode()).hexdigest() + '.json')
    if target.exists():
        raw = target.read_bytes()
    else:
        error = None
        for _ in range(3):
            try:
                request = urllib.request.Request(url, headers={'User-Agent': 'MonCarnetRando/1.0'})
                with urllib.request.urlopen(request, timeout=40) as response:
                    raw = response.read()
                target.write_bytes(raw)
                break
            except Exception as exc:
                error = exc
        else:
            raise error
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def paginated(endpoint, fields, raw_dir):
    url = API + endpoint + '/?' + urllib.parse.urlencode({'format': 'json', 'page_size': '1000', 'fields': fields})
    first_url = url
    records = []
    pages = []
    expected = None
    while url:
        data, digest = get_json(url, raw_dir)
        if expected is None:
            expected = data['count']
        assert data['count'] == expected, 'The portal count changed during collection'
        records.extend(data['results'])
        pages.append({'url': url, 'sha256': digest, 'rows': len(data['results'])})
        url = data['next']
    assert len(records) == expected and len({r['id'] for r in records}) == expected
    return records, expected, first_url, pages


def existing_records(root):
    result = {}
    evidence = []
    for path in sorted((root / 'catalogue/snapshots').glob('*.json.gz')):
        if path.name == 'perche.json.gz':
            continue
        raw = path.read_bytes()
        rows = json.loads(gzip.decompress(raw))
        evidence.append({'path': str(path.relative_to(root)), 'sha256': hashlib.sha256(raw).hexdigest(), 'rows': len(rows)})
        for row in rows:
            result[row['sourceId']] = row
    return list(result.values()), evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path(tempfile.gettempdir()) / 'mon-carnet-perche')
    args = parser.parse_args()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    raw_dir = output / 'raw'
    raw_dir.mkdir(exist_ok=True)
    checked_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    practices, _, _, _ = paginated('trek_practice', 'id,name', raw_dir)
    walking_ids = {p['id'] for p in practices if p['name'].get('fr') in ['À pied', 'Pédestre']}
    assert walking_ids, 'No explicitly labelled walking practice'
    cities, _, _, _ = paginated('city', 'id,code,name', raw_dir)
    city_by_code = {str(c['code']): c['name'] for c in cities}
    treks, total_all, api_url, pages = paginated('trek', FIELDS, raw_dir)
    published_walks = [t for t in treks if t['practice'] in walking_ids and t['published'].get('fr')]
    selected = []
    excluded = []
    for trek in published_walks:
        codes = sorted(set(str(c) for c in trek.get('city_codes', [])))
        normandy = [c for c in codes if c[:2] in DEPARTMENTS]
        departure_code = str(trek.get('departure_city_code') or '')
        if not normandy:
            excluded.append({'id': trek['id'], 'name': trek['name']['fr'], 'cityCodes': codes,
                             'reason': 'Aucune commune normande explicitement publiée.'})
            continue
        assert trek.get('gpx'), f"No GPX published for trek {trek['id']}"
        slug = trek['gpx'].rsplit('/', 1)[-1].removesuffix('.gpx')
        department = departure_code[:2] if departure_code[:2] in DEPARTMENTS else normandy[0][:2]
        town = city_by_code.get(departure_code) or city_by_code.get(normandy[0])
        assert town, f"Unknown published commune code for trek {trek['id']}"
        record = {
            'sourceId': f"PERCHE-GEOTREK-{trek['id']}", 'name': trek['name']['fr'],
            'town': town, 'department': department, 'km': round(trek['length_2d'] / 1000, 1),
            'official': f"{PORTAL}trek/{trek['id']}-{slug}", 'gpxSource': trek['gpx'],
            'officialLocation': trek['departure_geom'],
            'sourceDeparture': trek.get('departure', {}).get('fr') or None,
            'sourceParking': trek.get('parking_location'),
            'sourceAdvisedParking': trek.get('advised_parking', {}).get('fr') or None,
            'sourceDurationMinutes': round(trek['duration'] * 60) if trek.get('duration') is not None else None,
            'sourceAscent': trek.get('ascent'),
            'sourceDescent': abs(trek['descent']) if trek.get('descent') is not None else None,
            'sourceApi': trek['url'], 'sourceApiPages': pages, 'sourceUpdatedAt': trek['update_datetime'],
            'sourceCityCodes': codes, 'sourceNormandyCityCodes': normandy,
            'sourceDepartureCityCode': departure_code,
            'scopeEvidence': {'method': 'INSEE communes explicitly supplied by the portal',
                              'normandyCommunes': [{'code': c, 'name': city_by_code.get(c)} for c in normandy],
                              'departureInNormandy': departure_code[:2] in DEPARTMENTS},
            'sourceChildren': trek['children'], 'sourceParents': trek['parents'],
        }
        # Geometry is checked from the portal's actual published GPX. No segment
        # is reconstructed from a route name or assumed from another portal.
        selected.append(record)

    print(f"Perche : {len(selected)} références pédestres normandes sur {len(published_walks)} pédestres publiées", flush=True)
    validated = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for index, row in enumerate(pool.map(prepare.validate, selected), 1):
            validated.append(row)
            print(f"Perche : GPX {index}/{len(selected)} · {row['sourceId']} · {row['status']}", flush=True)
    selected = validated

    known, known_evidence = existing_records(ROOT)
    known_by_url = {}
    known_by_hash = {}
    known_by_geometry = {}
    known_shapes = []
    for row in known:
        if row.get('gpxSource'):
            known_by_url.setdefault(row['gpxSource'], []).append(row)
        if row.get('gpxSha256'):
            known_by_hash.setdefault(row['gpxSha256'], []).append(row)
        if row.get('segments'):
            known_by_geometry.setdefault(canonical(row['segments']), []).append(row)
            known_shapes.append((row, comparison.describe(row['segments'])))
    audit_rows = []
    selected_by_geometry = {}
    selected_shapes = []
    for index, row in enumerate(selected, 1):
        matches = []
        exact = known_by_geometry.get(canonical(row['segments']), []) if row.get('segments') else []
        if exact:
            matches = [{'sourceId': r['sourceId'], 'method': 'exact-geometry-6-decimals'} for r in exact]
        elif row.get('segments'):
            shape = comparison.describe(row['segments'])
            matches = [{'sourceId': r['sourceId'], 'method': 'bidirectional-2m-length-1pct'}
                       for r, old_shape in known_shapes if comparison.equivalent(shape, old_shape)]
        internal = []
        if row.get('segments'):
            shape_key = canonical(row['segments'])
            exact_internal = selected_by_geometry.get(shape_key, [])
            internal = [{'sourceId': r['sourceId'], 'method': 'exact-geometry-6-decimals'} for r in exact_internal]
            shape = comparison.describe(row['segments'])
            if not internal:
                internal = [{'sourceId': r['sourceId'], 'method': 'bidirectional-2m-length-1pct'}
                            for r, old_shape in selected_shapes if comparison.equivalent(shape, old_shape)]
            selected_by_geometry.setdefault(shape_key, []).append(row)
            selected_shapes.append((row, shape))
        name = normalize(row['name'])
        names = [{'sourceId': old['sourceId'], 'name': old['name'], 'km': old.get('km')}
                 for old in known if len(name) > 10 and (name in normalize(old['name']) or normalize(old['name']) in name)]
        audit_rows.append({
            'sourceId': row['sourceId'], 'name': row['name'], 'status': row['status'],
            'geometryMatches': matches, 'internalGeometryMatches': internal, 'nominalHints': names,
            'sameGpxUrl': [r['sourceId'] for r in known_by_url.get(row.get('gpxSource'), [])],
            'sameGpxSha256': [r['sourceId'] for r in known_by_hash.get(row.get('gpxSha256'), [])],
            'newGeometryCandidate': row['status'] == 'trace-verifiee' and not matches and not internal,
        })
        print(f"Perche : comparaison {index}/{len(selected)} · {len(matches)} correspondances", flush=True)
    metadata = lambda row: {k: v for k, v in row.items() if k != 'segments'}
    sources = [{
        'source': PORTAL, 'department': '61', 'api': api_url, 'total': len(selected),
        'announcedTotal': len(selected), 'collectedAll': True,
        'allPracticePortalCount': total_all, 'publishedWalkingPortalCount': len(published_walks),
        'walkingPracticeIds': sorted(walking_ids), 'excludedNonNormandyCount': len(excluded),
        'note': 'Pédestre publié en français ; au moins une commune traversée explicitement normande. '
                'Les parcours transfrontaliers ne sont pas découpés. Comparaison des géométries séparée de cet inventaire. '
                'Aucune licence ouverte générale identifiée sur le portail ; seuls faits et liens GPX publics conservés.',
    }]
    inventory = {'checkedAt': checked_at, 'sources': sources, 'records': [metadata(r) for r in selected], 'overrides': []}
    (output / 'inventaire-perche.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n')
    (output / 'perche.json.gz').write_bytes(gzip.compress(json.dumps(selected, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0))
    summary = {'checkedAt': checked_at, 'knownSnapshotReferences': len(known), 'knownSnapshots': known_evidence, 'allPracticePortalCount': total_all,
               'publishedWalkingPortalCount': len(published_walks), 'normandyPublishedWalkingReferences': len(selected),
               'excludedNonNormandyCount': len(excluded),
               'validatedGpx': sum(r['status'] == 'trace-verifiee' for r in selected),
               'referencesMatchingGeometry': sum(bool(r['geometryMatches']) for r in audit_rows),
               'referencesMatchingEarlierPercheGeometry': sum(bool(r['internalGeometryMatches']) for r in audit_rows),
               'newGeometryCandidates': sum(r['newGeometryCandidate'] for r in audit_rows),
               'records': audit_rows, 'excluded': excluded}
    (output / 'audit-perche.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k not in ['records', 'excluded', 'knownSnapshots']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
