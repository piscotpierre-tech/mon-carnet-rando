"""Prepare paired ascent/descent and profiles using the public IGN ground model.

Python 3 standard library only. Optional route IDs select a subset. Geometry
comes from each route's existing GeoJSON or its verified official GPX source.
No altitude is inferred from a blank GPX, and gaps between segments are not
treated as climbs. The server response is cached outside the repository.
"""
import concurrent.futures
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(tempfile.gettempdir()) / "pierre-rando-ign-elevations"
CACHE.mkdir(exist_ok=True)
ENDPOINT = "https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevationLine.json"
RESOURCE = "ign_rge_alti_wld"
DATE = "2026-10-16"


def distance(a, b):
    lon1, lat1, *_ = a
    lon2, lat2, *_ = b
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    angle = (math.sin((phi2 - phi1) / 2) ** 2 + math.cos(phi1) * math.cos(phi2)
             * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371000 * 2 * math.atan2(math.sqrt(angle), math.sqrt(max(0, 1-angle)))


def geometry(path):
    raw = (ROOT / path).read_bytes()
    if path.endswith(".geojson"):
        geo = json.loads(raw)["geometry"]
        segments = [geo["coordinates"]] if geo["type"] == "LineString" else geo["coordinates"]
    else:
        root = ET.fromstring(raw)
        segments = []
        for element in root.iter():
            if element.tag.split("}")[-1] in ("trkseg", "rte"):
                points = []
                for p in element:
                    if p.tag.split("}")[-1] not in ("trkpt", "rtept"):
                        continue
                    coordinate = [float(p.attrib["lon"]), float(p.attrib["lat"])]
                    altitude = next((c.text for c in p if c.tag.split("}")[-1] == "ele"), None)
                    if altitude is not None:
                        coordinate.append(float(altitude))
                    points.append(coordinate)
                if len(points) > 1:
                    segments.append(points)
    assert segments and all(len(s) > 1 for s in segments), "Missing route geometry"
    assert all(-6 < p[0] < 10 and 42 < p[1] < 52 for s in segments for p in s)
    return segments, hashlib.sha256(raw).hexdigest()


def sample(points):
    length = sum(distance(a,b) for a,b in zip(points, points[1:]))
    body = {
        "lon": "|".join(str(p[0]) for p in points),
        "lat": "|".join(str(p[1]) for p in points),
        "resource": RESOURCE, "delimiter": "|",
        "sampling": min(5000, max(2, math.ceil(length / 25) + 1)),
        "measures": "false", "profile_mode": "simple", "indent": "false", "zonly": "false",
    }
    encoded = json.dumps(body, separators=(",", ":")).encode()
    key = hashlib.sha256(encoded).hexdigest()
    cached = CACHE / (key + ".json")
    for attempt in range(3):
        try:
            if cached.exists():
                raw = cached.read_bytes()
            else:
                request = urllib.request.Request(ENDPOINT, data=encoded, headers={
                    "Content-Type": "application/json", "Accept": "application/json",
                    "User-Agent": "MonCarnetRando/1.0 (+https://github.com/piscotpierre-tech/mon-carnet-rando)",
                })
                with urllib.request.urlopen(request, timeout=45) as response:
                    raw = response.read()
            data = json.loads(raw)
            samples = data["elevations"]
            # The service can append an endpoint (notably for a closed loop).
            assert body["sampling"] <= len(samples) <= body["sampling"] + 1, "Incomplete elevation response"
            assert distance([samples[0]["lon"], samples[0]["lat"]], points[0]) < 5
            assert distance([samples[-1]["lon"], samples[-1]["lat"]], points[-1]) < 5
            assert all(math.isfinite(float(p["z"])) and -25 <= float(p["z"]) <= 1500 for p in samples), "Missing ground altitude"
            differences = data["height_differences"]
            assert all(math.isfinite(differences[k]) and differences[k] >= 0 for k in ("positive", "negative"))
            cached.write_bytes(raw)
            return data, {"sampling": body["sampling"], "returned": len(samples), "requestSha256": key}
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def build(route):
    gpx_altitudes = route.get("elevationMethod") == "gpx"
    source_path = route["gpx"] if gpx_altitudes else route.get("trace") or route.get("elevationTrace")
    segments, source_hash = geometry(source_path)
    results, requests = [], []
    gain, loss, walked = 0, 0, 0
    altitudes = []
    for segment in segments:
        if gpx_altitudes:
            assert all(len(p) >= 3 and math.isfinite(p[2]) and -25 <= p[2] <= 1500 for p in segment), "Incomplete GPX altitude"
            heights = [p[2] for p in segment]
            data = {
                "elevations": [{"lon": p[0], "lat": p[1], "z": p[2]} for p in segment],
                "height_differences": {
                    "positive": sum(max(b-a,0) for a,b in zip(heights,heights[1:])),
                    "negative": sum(max(a-b,0) for a,b in zip(heights,heights[1:])),
                },
            }
            provenance = {"sampling": len(segment), "returned": len(segment), "sourceSha256": source_hash}
        else:
            data, provenance = sample(segment)
        requests.append(provenance)
        gain += data["height_differences"]["positive"]
        loss += data["height_differences"]["negative"]
        profile, previous = [], None
        for point in data["elevations"]:
            coordinate = [point["lon"], point["lat"]]
            if previous is not None:
                walked += distance(previous, coordinate)
            previous = coordinate
            z = float(point["z"])
            profile.append([round(walked, 1), z])
            altitudes.append(z)
        results.append(profile)
    summary = {
        "ascent": int(5 * math.floor(gain / 5 + .5)), "descent": int(5 * math.floor(loss / 5 + .5)),
        "min": math.floor(min(altitudes)), "max": math.ceil(max(altitudes)),
        "distanceKm": round(walked / 1000, 3), "estimated": True,
        "provider": "GPX officiel" if gpx_altitudes else "IGN RGE ALTI", "checkedAt": DATE,
        "profile": f"assets/profiles/{route['id']}.json",
    }
    output = {
        "routeId": route["id"], "summary": summary,
        "sourceTrace": source_path, "sourceSha256": source_hash,
        "sourceUrl": route.get("gpxSource") or route.get("elevationTraceSource"),
        "endpoint": route["gpxSource"] if gpx_altitudes else ENDPOINT,
        "resource": "GPX altitude" if gpx_altitudes else RESOURCE,
        "spacingTargetMetres": None if gpx_altitudes else 25,
        "profileMode": "gpx-altitude" if gpx_altitudes else "simple", "requests": requests,
        "heightDifferences": {"positive": round(gain, 3), "negative": round(loss, 3)},
        "segments": results,
    }
    target = ROOT / summary["profile"]
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"OK {route['id']} · D+ ≈ {summary['ascent']} m · D− ≈ {summary['descent']} m · {route['name']}", flush=True)


if __name__ == "__main__":
    routes = json.loads(subprocess.check_output(["node", "--input-type=module", "-e",
        "import{ROUTES}from'./data.js';console.log(JSON.stringify(ROUTES))"], cwd=ROOT))
    selected = set(map(int, sys.argv[1:]))
    routes = [r for r in routes if (r.get("trace") or r.get("elevationTrace")) and (not selected or r["id"] in selected)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(build, routes))
