"""Validate each published GPX before it becomes a usable circuit.

Failures remain in the inventory, including missing geometry or suspicious
lengths. Raw responses are cached for resuming and their hashes retained.
"""
import concurrent.futures
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from importlib import import_module
source = import_module("collect-normandie")
CACHE = source.CACHE / "gpx"
CACHE.mkdir(exist_ok=True)


def normal(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value or '').lower() if c.isalnum())


def distance(a, b):
    p, q = math.radians(a[1]), math.radians(b[1])
    h = math.sin((q-p)/2)**2 + math.cos(p)*math.cos(q)*math.sin(math.radians(b[0]-a[0])/2)**2
    return 12742000 * math.asin(min(1, math.sqrt(h)))


def parse(raw):
    xml = ET.fromstring(raw)
    segments = []
    for parent in xml.iter():
        if parent.tag.split('}')[-1] not in ['trkseg', 'rte']:
            continue
        segment = []
        for point in parent:
            if point.tag.split('}')[-1] not in ['trkpt', 'rtept']:
                continue
            lon, lat = float(point.attrib['lon']), float(point.attrib['lat'])
            assert -6 < lon < 10 and 42 < lat < 52, 'Coordinates outside metropolitan France'
            coordinate = [round(lon, 7), round(lat, 7)]
            elevation = next((p.text for p in point if p.tag.split('}')[-1] == 'ele'), None)
            # Empty or invalid altitude does not invalidate usable coordinates.
            # It remains absent and must later come from the IGN ground model.
            try:
                altitude = float(elevation) if elevation is not None and elevation.strip() else None
                if altitude is not None and math.isfinite(altitude):
                    coordinate.append(altitude)
            except ValueError:
                pass
            if not segment or coordinate[:2] != segment[-1][:2]:
                segment.append(coordinate)
        if len(segment) > 1:
            segments.append(segment)
    assert segments and sum(map(len, segments)) > 5, 'No usable GPX track'
    return segments


def validate(record):
    result = dict(record)
    url = record.get('gpxSource')
    if not url:
        result['status'] = 'sans-gpx-publie'
        return result
    target = CACHE / (hashlib.sha256(url.encode()).hexdigest() + '.gpx')
    try:
        if target.exists():
            raw = target.read_bytes()
        else:
            req = urllib.request.Request(url, headers={'User-Agent': 'MonCarnetRando/1.0'})
            with urllib.request.urlopen(req, timeout=40) as response:
                raw = response.read()
            target.write_bytes(raw)
        segments = parse(raw)
        length = sum(distance(a, b) for segment in segments for a, b in zip(segment, segment[1:])) / 1000
        assert .1 <= length <= 1200, 'Implausible GPX length'
        target.write_bytes(raw)
        result.update(gpxSha256=hashlib.sha256(raw).hexdigest(), geometryKm=round(length, 3), pointCount=sum(map(len, segments)))
        km = record.get('km')
        if km and abs(length-km) > max(1, km*.25):
            result.update(status='distance-a-verifier', issue=f"Fiche {km} km ; GPX {length:.1f} km")
        else:
            result['status'] = 'trace-verifiee'
        result['segments'] = segments
    except Exception as error:
        result.update(status='gpx-inexploitable', issue=str(error))
    return result


def main():
    inventory = json.loads((ROOT / 'catalogue/inventaire-regional.json').read_text())
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for i, record in enumerate(pool.map(validate, inventory['records']), 1):
            results.append(record)
            if i % 25 == 0:
                (ROOT / 'catalogue/preparation.json').write_text(json.dumps(results, ensure_ascii=False, separators=(',', ':')) + '\n')
                print(f"GPX {i}/{len(inventory['records'])} · {record['status']}", flush=True)
    (ROOT / 'catalogue/preparation.json').write_text(json.dumps(results, ensure_ascii=False, separators=(',', ':')) + '\n')
    print('GPX collection complete', flush=True)


if __name__ == '__main__':
    main()
