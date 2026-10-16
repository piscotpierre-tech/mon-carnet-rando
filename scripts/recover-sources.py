"""Revalidate 22 inspected official GPXs without recollecting the catalogue.

Only the allowlisted source IDs and unchanged published URLs are eligible.
Original response bytes stay in prepare-catalogue's cache, with their SHA256
retained in every snapshot. This script does not build or publish any route.
"""
import argparse
import gzip
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
prepare = importlib.import_module('prepare-catalogue')
TARGET_URLS = {
    'ITINOR050V502EN9': 'https://cdt61.media.tourinsoft.eu/upload/gpx-garmin-PR-le-cul-de-fer-2.gpx',
    'ITINOR061FS0000F': 'https://cdt61.media.tourinsoft.eu/upload/a-pied-gue-de-culoiseau.gpx',
    'ITINOR061FS0000L': 'https://cdt61.media.tourinsoft.eu/upload/Parcours-botanique-a-la-roche-d-oetre.gpx',
    'ITINOR061FS0000W': 'https://cdt61.media.tourinsoft.eu/upload/a-pied-la-pierre-procureuse.gpx',
    'ITINOR061V502ZJX': 'https://cdt61.media.tourinsoft.eu/upload/4-Tour-des-collines-du-Perche-de-la-Ferte-Vidame-a-Tourouvre-cpt.gpx',
    'ITINOR061V502ZKD': 'https://cdt61.media.tourinsoft.eu/upload/5-Tour-des-collines-du-Perche-de-Tourouvre-a-Mortagne-au-Perche-cpt.gpx',
    'ITINOR061V508OCR': 'https://cdt61.media.tourinsoft.eu/upload/Randonnee-le-bois-des-sicots-le-perche-randonnee-a-pied.gpx',
    'ITINOR061V508QZB': 'https://cdt61.media.tourinsoft.eu/upload/Le-Moncel-et-Bellegarde.gpx',
    'ITINOR061V508R71': 'https://cdt61.media.tourinsoft.eu/upload/les-jauneaux-randonee-a-pied-pays-d-alencon.gpx',
    'ITINOR061V509M40': 'https://cdt61.media.tourinsoft.eu/upload/Randonnee-les-bornes-cavalieres-randonnee-a-pied.gpx',
    'ITINOR061V50A5CH': 'https://cdt61.media.tourinsoft.eu/upload/SuisseNormande-Autour-du-Noireau.gpx',
    'ITINOR027FS0000H': 'https://cdt61.media.tourinsoft.eu/upload/Le-parc-parissot-et-les-3-rivieres.gpx',
    'ITINOR027V50S0XS': 'https://cdt61.media.tourinsoft.eu/upload/La-vallee-du-guiel.gpx',
    'ITINOR027V50S27N': 'https://cdt61.media.tourinsoft.eu/upload/La-vallee-de-saint-aubin.gpx',
    'ITINOR050FS0000V': 'https://cdt61.media.tourinsoft.eu/upload/Mortain-St-Hilaire-parcours-14.9.gpx',
    'ITINOR050V502NOB': 'https://cdt61.media.tourinsoft.eu/upload/St-Jean-de-Daye-St-Lo-parcours-23.1.gpx',
    'ITINOR050V502NPS': 'https://cdt61.media.tourinsoft.eu/upload/Conde-sur-Vire-Pont-Farcy-parcours-19.5.gpx',
    'ITINOR050V502NLL': 'https://cdt61.media.tourinsoft.eu/upload/Baupte-Carentan-parcours-8.6.gpx',
    'ITINOR050V502K35': 'https://cdt61.media.tourinsoft.eu/upload/St-Hilaire-Ducey-parcours-19.gpx',
    'ITINOR050V502NLB': 'https://cdt61.media.tourinsoft.eu/upload/La-Haye-Baupte-parcours-12.9.gpx',
    'ITINOR050V502NAR': 'https://cdt61.media.tourinsoft.eu/upload/Bricquebec-St-Sauveur-parcours-13.6.gpx',
    'ITINOR050V502NL8': 'https://cdt61.media.tourinsoft.eu/upload/St-Sauveur-La-Haye-parcours-16.1-2.gpx',
}


def recover(root=ROOT):
    recovered = {}
    # Validate every selected source before writing any catalogue file.
    for path in sorted((root / 'catalogue/snapshots').glob('*.json.gz')):
        rows = json.loads(gzip.decompress(path.read_bytes()))
        for row in rows:
            sid = row['sourceId']
            if sid not in TARGET_URLS:
                continue
            assert row.get('gpxSource') == TARGET_URLS[sid], f'Source URL changed: {sid}'
            result = prepare.validate(row)
            assert result['status'] == 'trace-verifiee', f"{sid}: {result.get('issue')}"
            assert result.get('gpxRepairs') and result.get('validatedGpxSha256'), f'Repair not documented: {sid}'
            recovered[sid] = result
    assert set(recovered) == set(TARGET_URLS), 'Some targeted sources are missing from the snapshots'
    changed = []
    # Keep the original collected snapshots untouched. This overlay is read
    # last by build-catalogue, preserving both the failed export and its audit.
    path = root / 'catalogue/snapshots/zz-recovered-gpx.json.gz'
    updated = [recovered[sid] for sid in sorted(recovered)]
    previous = json.loads(gzip.decompress(path.read_bytes())) if path.exists() else None
    if updated != previous:
        path.write_bytes(gzip.compress(json.dumps(updated, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0))
        changed.append(str(path.relative_to(root)))
    for path in [root / 'catalogue/inventaire-regional.json', root / 'catalogue/inventaire-complementaire.json']:
        original = json.loads(path.read_text())
        updated = dict(original)
        for field in ['records', 'overrides']:
            if field not in original:
                continue
            updated[field] = []
            for row in original[field]:
                result = recovered.get(row['sourceId'])
                if result is None:
                    updated[field].append(row)
                    continue
                assert row.get('gpxSource') == result['gpxSource'], f"Inventory URL changed: {row['sourceId']}"
                merged = dict(row)
                merged.update({key: value for key, value in result.items() if key in {
                    'status', 'gpxSha256', 'validatedGpxSha256', 'gpxRepairs', 'geometryKm', 'pointCount',
                }})
                merged.pop('issue', None)
                updated[field].append(merged)
        if updated != original:
            path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n')
            changed.append(str(path.relative_to(root)))
    print(f'{len(recovered)} sources revalidated; {len(changed)} files updated')
    for path in changed:
        print(path)
    return recovered, changed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, help='Directory containing original responses named by URL SHA256 + .gpx')
    args = parser.parse_args()
    if args.cache_dir:
        prepare.CACHE = args.cache_dir
    recover()
