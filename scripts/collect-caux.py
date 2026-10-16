"""Read only the official Caux Seine Randonnée category, at most 20 GPXs.

All outputs remain under --output-dir. No repository file is modified.
Public route facts and linked GPXs only; no descriptive texts or photos copied.
"""
import argparse
import concurrent.futures
import datetime
import gzip
import hashlib
import html
from html.parser import HTMLParser
import importlib
import json
from pathlib import Path
import re
import sys
import urllib.request

sys.dont_write_bytecode = True

PORTAL = 'https://randotrailencauxseine.fr'
LISTING = PORTAL + '/fr/activites'
HELPER_JS = PORTAL + '/assets/js/blocParcours.js'


def plain(value):
    return html.unescape(re.sub('<[^>]*>', ' ', value)).strip()


class Attrs(HTMLParser):
    def handle_starttag(self, tag, attrs):
        self.attrs = dict(attrs)


def attributes(value):
    parser = Attrs()
    parser.feed('<div ' + value + '>')
    return parser.attrs


def get(url, target, headers=None):
    if target.exists():
        raw = target.read_bytes()
    else:
        request = urllib.request.Request(url, headers={'User-Agent': 'MonCarnetRando/1.0', **(headers or {})})
        with urllib.request.urlopen(request, timeout=35) as response:
            raw = response.read()
        target.write_bytes(raw)
    return raw, hashlib.sha256(raw).hexdigest()


def parse_listing(text):
    category = text.split('<div id="container-rando"', 1)[1].split('<div id="container-', 1)[0]
    parts = re.split(r'<div id="trace_(\d+)" class="blocTrace"([^>]*)>', category)
    records = []
    for identifier, attr, body in zip(parts[1::3], parts[2::3], parts[3::3]):
        data = attributes(attr)
        name = plain(re.search(r'class="nomTrace[^>]*>(.*?)<br', body, re.S)[1])
        town = plain(re.search(r'class="traceLieu[^>]*>(.*?)</span>', body, re.S)[1])
        lo, hi = int(data['data-dureemin']), int(data['data-dureemax'])
        records.append({
            'sourceId': 'CAUX-SEINE-' + identifier, 'name': name, 'town': town,
            'department': None, 'km': float(data['data-distance']),
            'official': PORTAL + '/fr/parcours/' + identifier,
            'gpxSource': PORTAL + '/fr/gpx/' + identifier,
            'sourceAscent': int(data['data-devpos']), 'sourceDescent': int(data['data-devneg']),
            'sourceDurationMinutes': lo if lo > 0 and lo == hi else None,
            'sourceDurationRangeMinutes': [lo, hi] if lo > 0 and hi > 0 else None,
            'sourceCategory': 'Randonnée', 'sourceListing': LISTING,
            'scopeEvidence': {'method': 'Explicit official activity category',
                              'category': 'Randonnée', 'selector': '#container-rando',
                              'listingId': int(identifier)},
        })
    assert len(records) == 20 and len({r['sourceId'] for r in records}) == 20, 'Randonnée listing changed; inspect before collecting'
    counts = {}
    for match in re.finditer(r'<div id="container-([^\"]+)"[^>]*>(.*?)(?=<div id="container-|\Z)', text, re.S):
        counts[match[1]] = len(set(re.findall(r'<div id="trace_(\d+)" class="blocTrace"', match[2])))
    return records, counts


def details(row, raw_dir):
    row = dict(row)
    identifier = row['sourceId'].rsplit('-', 1)[1]
    try:
        raw, digest = get(row['official'], raw_dir / (identifier + '.html'))
        text = raw.decode('utf-8')
        row['sourcePageSha256'] = digest
        town = re.search(r'class="lineDetails[^>]*>.*?</i>\s*([^<]+)\s*\((\d{2})\)', text, re.S)
        assert town, 'No explicit town and department on the official detail page'
        row['town'] = html.unescape(town[1]).strip()
        row['department'] = town[2] if town[2] == '76' else None
        row['scopeEvidence']['officialTown'] = row['town']
        row['scopeEvidence']['officialDepartment'] = town[2]
        if town[2] != '76':
            row['sourceScopeConflict'] = f"La fiche indique {row['town']} ({town[2]}) ; affectation départementale suspendue."
        assert re.search(r'id="downloadGpx"', text), 'No official GPX download button'
        row['sourcePdfs'] = [{'url': html.unescape(url), 'label': plain(label)}
                             for url, label in re.findall(r'<a\b[^>]*href="([^\"]+\.pdf)"[^>]*>(.*?)</a>', text, re.I | re.S)]
        facts = {plain(key): plain(value) for key, value in re.findall(r'<li><span>(.*?)</span>(.*?)</li>', text, re.S)}
        row['sourceFacts'] = facts
        row['sourceMarking'] = facts.get('Balisage')
        row['sourceDeparture'] = None
        row['sourceParking'] = None
        # dataPi contains projected coordinates; never transform or guess a CRS.
        # Only a factual departure label may be kept, without claiming parking.
        pi = re.search(r'dataPi:("(?:\\.|[^"\\])*")', text)
        if pi:
            try:
                points = json.loads(json.loads(pi[1]))
            except json.JSONDecodeError:
                # Optional JavaScript UI data may use JS-only escapes. It is
                # unnecessary for a GPX and must never invalidate that source.
                points = []
            labels = []
            for point in points:
                if point.get('type') in ['deparrivee', 'depart']:
                    for key in ['nom', 'name', 'titre']:
                        if point.get(key):
                            labels.append(plain(str(point[key])))
                            break
            if len(labels) == 1:
                row['sourceDeparture'] = labels[0]
        return row
    except Exception as error:
        row.update(status='fiche-indisponible', issue=str(error), gpxSource=None)
        return row


def validate_gpx(row, prepare, new_helper_sha):
    """Follow only the publisher's explicit alternative and normal referer.

    The public download is served on espacestrail.run when its own detail page
    is the HTTP Referer, just as the official anchor click sends it. No cookies,
    account, authentication token or session is used.
    """
    row = dict(row)
    if not row.get('gpxSource'):
        return row
    source = row['gpxSource']
    identifier = row['sourceId'].rsplit('-', 1)[1]
    target = prepare.CACHE / (hashlib.sha256(source.encode()).hexdigest() + '.gpx')
    try:
        raw, digest = get(source, target)
        message = raw.decode('utf-8', errors='strict').strip() if raw.startswith(b'Rendez-vous sur ') else ''
        alternative = re.fullmatch(r'Rendez-vous sur (https://espacestrail\.run/fr/seinedetrail/parcours/(\d+)) pour accéder à ce fichier gpx', message)
        if alternative:
            assert alternative[2] == identifier, 'Alternative GPX belongs to another source ID'
            page = alternative[1]
            url = page.replace('/parcours/', '/gpx/')
            row.update(sourceOriginalGpxUrl=source, sourceOriginalGpxResponseSha256=digest,
                       sourceAlternativePage=page, gpxSource=url,
                       sourceDownloadReferer=page,
                       sourceGpxAccess='Téléchargement public ; Referer de la fiche officielle requis comme lors du clic navigateur ; sans compte ni cookie.')
            row['sourceGpxLinkEvidence'] = {
                'url': 'https://espacestrail.run/assets/js/blocParcours.js', 'sha256': new_helper_sha,
                'method': 'Official downloadGpx handler + alternative page explicitly supplied by the original GPX endpoint',
            }
            get(url, prepare.CACHE / (hashlib.sha256(url.encode()).hexdigest() + '.gpx'), {'Referer': page})
        result = prepare.validate(row)
        if result.get('segments'):
            result['officialLocation'] = result['segments'][0][0][:2]
            result['officialLocationPrecision'] = 'Premier point du GPX officiel ; stationnement non vérifié'
        return result
    except Exception as error:
        row.update(status='gpx-inexploitable', issue=str(error))
        return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=Path('/tmp/rando-caux'))
    args = parser.parse_args()
    root = args.repo.resolve()
    output = args.output_dir.resolve()
    assert not output.is_relative_to(root), 'Audit outputs must stay outside the repository'
    raw_dir = output / 'raw'
    raw_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root / 'scripts'))
    prepare = importlib.import_module('prepare-catalogue')
    perche = importlib.import_module('collect-perche')
    comparison = importlib.import_module('trace-comparison')
    prepare.CACHE = raw_dir / 'gpx'
    prepare.CACHE.mkdir(exist_ok=True)
    checked_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    listing, listing_sha = get(LISTING, raw_dir / 'activites.html')
    helper, helper_sha = get(HELPER_JS, raw_dir / 'blocParcours.js')
    assert b"CI.base_url_territoire+'/gpx/'+options.dataTrace.traceID" in helper, 'Official GPX download handler changed'
    new_helper, new_helper_sha = get('https://espacestrail.run/assets/js/blocParcours.js', raw_dir / 'espacestrail-blocParcours.js')
    assert b"CI.base_url_territoire+'/gpx/'+options.dataTrace.traceID" in new_helper, 'Alternative official GPX download handler changed'
    selected, category_counts = parse_listing(listing.decode('utf-8'))
    for row in selected:
        row.update(sourceListingSha256=listing_sha, sourceGpxLinkEvidence={'url': HELPER_JS, 'sha256': helper_sha,
                   'method': 'Official downloadGpx handler resolves /fr/gpx/<traceID>'})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        selected = list(pool.map(lambda row: details(row, raw_dir), selected))
    for row in selected:
        if row.get('sourceScopeConflict'):
            assert row['town'] == 'Heurteauville', 'Unexpected administrative conflict; manual check needed'
            commune_url = 'https://geo.api.gouv.fr/communes?nom=Heurteauville&fields=nom,code,codeDepartement&format=json'
            commune_raw, commune_sha = get(commune_url, raw_dir / 'geo-api-Heurteauville.json')
            matches = [c for c in json.loads(commune_raw) if c.get('nom') == 'Heurteauville']
            assert len(matches) == 1 and matches[0].get('codeDepartement') == '76', 'Official commune reference does not resolve the source conflict'
            row['department'] = '76'
            row['scopeEvidence']['administrativeReference'] = {
                'url': commune_url, 'sha256': commune_sha, 'commune': matches[0],
                'note': 'Département résolu par le référentiel officiel API Découpage administratif ; la déclaration contradictoire (27) reste conservée.',
            }
            row['sourceScopeConflict'] = 'La fiche Caux Seine indique Heurteauville (27). Le référentiel officiel identifie Heurteauville, code INSEE ' + matches[0]['code'] + ', en Seine-Maritime (76).'
    print(f'Caux Seine: {len(selected)} Randonnée fiches; departments checked', flush=True)
    validated = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for index, row in enumerate(pool.map(lambda row: validate_gpx(row, prepare, new_helper_sha), selected), 1):
            validated.append(row)
            print(f"GPX {index}/{len(selected)}: {row['sourceId']} {row['status']} {row.get('issue', '')}", flush=True)
    selected = validated
    for row in selected:
        if row['sourceId'] == 'CAUX-SEINE-150690':
            for pdf in row.get('sourcePdfs', []):
                file = raw_dir / pdf['url'].rsplit('/', 1)[-1]
                if file.exists():
                    pdf['sha256'] = hashlib.sha256(file.read_bytes()).hexdigest()
                if pdf['url'].endswith('res7066_4396.pdf'):
                    pdf.update(publishedKm=17.8, publishedDurationMinutes=270,
                               publishedDeparture='La Frenaye, place de l’Europe, parking Brassens',
                               metadataCreatedAt='2014-03-14', metadataModifiedAt='2021-05-21',
                               note='Brochure liée distincte ; 17,8 km, contre 17,21 km sur la fiche web. Métadonnées PDF datées, sans déduire une date de terrain.')
                elif pdf['url'].endswith('res8033_8518.pdf'):
                    pdf.update(publishedKm=17.2, publishedAscent=290, publishedDescent=290,
                               metadataCreatedAt='2021-07-19',
                               note='Carte PDF liée : D+ et D− de 290 m chacun, contre 270 m chacun sur la fiche web. Métadonnées PDF datées, sans déduire une date de terrain.')
    # A distinct-reference inventory, honoring the recovered overlay loaded last.
    known = {}
    evidence = []
    for path in sorted((root / 'catalogue/snapshots').glob('*.json.gz')):
        if path.name == 'caux-seine.json.gz':
            continue
        data = path.read_bytes()
        rows = json.loads(gzip.decompress(data))
        evidence.append({'path': str(path.relative_to(root)), 'sha256': hashlib.sha256(data).hexdigest(), 'rows': len(rows)})
        known.update({r['sourceId']: r for r in rows})
    known_by_geometry = {}
    known_shapes = []
    for row in known.values():
        if row.get('segments'):
            known_by_geometry.setdefault(perche.canonical(row['segments']), []).append(row)
            known_shapes.append((row, comparison.describe(row['segments'])))
    audit_rows = []
    own = []
    for index, row in enumerate(selected, 1):
        matches = []
        internal = []
        if row.get('segments'):
            key = perche.canonical(row['segments'])
            shape = comparison.describe(row['segments'])
            exact = known_by_geometry.get(key, [])
            if exact:
                matches = [{'sourceId': old['sourceId'], 'method': 'exact-geometry-6-decimals'} for old in exact]
            else:
                matches = [{'sourceId': old['sourceId'], 'method': 'bidirectional-2m-length-1pct'}
                           for old, old_shape in known_shapes if comparison.equivalent(shape, old_shape)]
            internal = [{'sourceId': old['sourceId'], 'method': 'bidirectional-2m-length-1pct'}
                        for old, old_shape in own if comparison.equivalent(shape, old_shape)]
            own.append((row, shape))
        audit_rows.append({'sourceId': row['sourceId'], 'name': row['name'], 'status': row['status'],
                           'geometryMatches': matches, 'internalGeometryMatches': internal,
                           'newGeometryCandidate': row['status'] == 'trace-verifiee' and not matches and not internal})
        print(f'Comparison {index}/{len(selected)}: {len(matches)} previous geometries', flush=True)
    metadata = lambda row: {k: v for k, v in row.items() if k != 'segments'}
    inventory = {'checkedAt': checked_at, 'sources': [{
        'source': LISTING, 'department': '76', 'total': len(selected), 'announcedTotal': len(selected),
        'collectedAll': True, 'scope': '#container-rando only', 'categoryCounts': category_counts,
        'note': 'Références explicitement Randonnée dans la liste activités. Les autres activités sont exclues. '
                'Les PDF liés sont conservés comme éditions distinctes ; leurs chiffres ne remplacent pas ceux du portail. '
                'Aucune licence ouverte générale identifiée ; uniquement faits et GPX publics liés.',
    }], 'records': [metadata(row) for row in selected], 'overrides': []}
    (output / 'inventaire-caux-seine.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n')
    (output / 'caux-seine.json.gz').write_bytes(gzip.compress(json.dumps(selected, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0))
    summary = {'checkedAt': checked_at, 'knownSnapshotReferences': len(known), 'knownSnapshots': evidence,
               'officialWalkingReferences': len(selected), 'categoryCounts': category_counts,
               'validatedGpx': sum(r['status'] == 'trace-verifiee' for r in selected),
               'referencesMatchingGeometry': sum(bool(r['geometryMatches']) for r in audit_rows),
               'referencesMatchingEarlierCauxGeometry': sum(bool(r['internalGeometryMatches']) for r in audit_rows),
               'newGeometryCandidates': sum(r['newGeometryCandidate'] for r in audit_rows), 'records': audit_rows}
    (output / 'audit-caux-seine.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k not in ['knownSnapshots', 'records']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
