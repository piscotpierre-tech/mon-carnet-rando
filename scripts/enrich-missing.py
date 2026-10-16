"""Read public detail fields for announcements without a listed GPX.

Only factual itinerary fields and document URLs are retained. No photos,
marketing descriptions, contact details or tracking code are copied.
"""
import concurrent.futures
import importlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
source = importlib.import_module('collect-normandie')


def detail(record):
    result = {'sourceId': record['sourceId'], 'official': record['official']}
    try:
        text = source.get(record['official'])
        data = json.loads(re.search(r'var IRISCollectionTheme = (\{.*?\});', text)[1])['queriedObject']['wpetFields']
        result['facts'] = {k:v for k,v in data.items() if any(term in k.lower() for term in ['gpx','pdf','document','denivel','duree','depart','distance','niveau','code-insee','balisage','adresse'])}
        result['documentUrls'] = sorted(set(re.findall(r'https?://[^\s"<>\\]+\.(?:gpx|pdf)(?:\?[^\s"<>\\]*)?', text.replace('\\/', '/'), re.I)))
        result['status'] = 'detail-consulte'
    except Exception as error:
        result.update(status='detail-indisponible', issue=str(error))
    return result


if __name__ == '__main__':
    records = json.loads((ROOT / 'catalogue/inventaire-regional.json').read_text())['records']
    records = [r for r in records if not r['gpxSource']]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i, r in enumerate(pool.map(detail, records), 1):
            results.append(r)
            if i % 10 == 0:
                (ROOT / 'catalogue/details-manquants.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
                print(f"Fiches sans GPX : {i}/{len(records)}", flush=True)
    (ROOT / 'catalogue/details-manquants.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
