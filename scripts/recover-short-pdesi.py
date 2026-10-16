"""Revalidate only PDESI 13592 from the existing, hash-verified source cache.

No HTTP request is made. The initial snapshot stays byte-identical, and a
single-record overlay carries the validation correction. No geometry is added,
resampled, moved or inferred, and this script does not build or publish routes.
"""
import argparse
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
collect = importlib.import_module('collect-seine-maritime')
SOURCE_ID = 'CD76-PDESI-2025-13592'
FEATURE_ID = 13592
OVERLAY = 'catalogue/snapshots/zz-recovered-short-pdesi.json.gz'


def recover(root=ROOT, cache_dir=None):
    cache_dir = cache_dir or collect.source.CACHE
    original_path = root / 'catalogue/snapshots/cd76.json.gz'
    rows = json.loads(gzip.decompress(original_path.read_bytes()))
    previous = next(row for row in rows if row['sourceId'] == SOURCE_ID)
    assert previous['sourceFeatureId'] == FEATURE_ID and previous['sourceFormat'] == 'GeoJSON'
    assert previous['sourceDatasetUrl'] == collect.URL, 'The source URL changed'
    cached = cache_dir / hashlib.sha256(collect.URL.encode()).hexdigest()
    raw = cached.read_bytes()  # A missing source cache is an error, never a download.
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == previous['sourceDatasetSha256'], 'The source cache does not match the original snapshot hash'
    dataset = json.loads(raw)
    feature = next(feature for feature in dataset['features'] if feature['properties']['OBJECTID'] == FEATURE_ID)
    facts = feature['properties']
    assert str(facts['Pedestre']).lower().strip() == 'oui', 'The source does not qualify this geometry as pedestrian'
    assert facts['Nom_iti'] == previous['name'], 'The source label changed'
    result = dict(previous)
    result.update(status='trace-verifiee', **collect.validate_geometry(feature['geometry']))
    result.pop('issue', None)
    result['sourceValidationCorrection'] = {
        'reason': 'Seuil arbitraire de plus de cinq points remplacé par le minimum géométrique de deux points par segment.',
        'previousStatus': previous['status'], 'originalSnapshot': 'catalogue/snapshots/cd76.json.gz',
        'sourceDatasetSha256': digest, 'coordinatesUnchanged': True,
    }
    result['sourceFeatureFacts'] = {key: facts[key] for key in ['OBJECTID', 'Nom_iti', 'Type', 'Pedestre', 'SHAPE_Leng']}
    target = root / OVERLAY
    updated = [result]
    changed = []
    existing = json.loads(gzip.decompress(target.read_bytes())) if target.exists() else None
    if existing != updated:
        target.write_bytes(gzip.compress(json.dumps(updated, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0))
        changed.append(OVERLAY)
    inventory_path = root / 'catalogue/inventaire-complementaire.json'
    inventory = json.loads(inventory_path.read_text())
    replaced = False
    for index, row in enumerate(inventory['records']):
        if row['sourceId'] == SOURCE_ID:
            updated_metadata = {key: value for key, value in result.items() if key != 'segments'}
            if row != updated_metadata:
                inventory['records'][index] = updated_metadata
                replaced = True
            break
    else:
        raise ValueError('The source ID is absent from the existing inventory')
    if replaced:
        inventory_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n')
        changed.append(str(inventory_path.relative_to(root)))
    print(f"{SOURCE_ID}: {result['pointCount']} points, {result['geometryKm']} km; {len(changed)} files updated")
    return result, changed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, help='Existing collect-normandie HTTP cache directory; no request is made')
    args = parser.parse_args()
    recover(cache_dir=args.cache_dir)
