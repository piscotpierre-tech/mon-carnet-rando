"""Inventory the public pedestrian catalogue; retain failures, never claim completeness.

Python standard library only. Cached HTTP responses allow an interrupted collection
to resume. Facts and source URLs are retained; photos/tracking scripts are excluded.
"""
import concurrent.futures
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://www.normandie-tourisme.fr/preparer-son-sejour/a-voir-a-faire/activites-sportives/randonnee-pedestre/"
CACHE = Path(tempfile.gettempdir()) / "pierre-rando-catalogue"
CACHE.mkdir(exist_ok=True)
DATE = "2026-10-16"
DEPARTMENTS = {"14": "Calvados", "27": "Eure", "50": "Manche", "61": "Orne", "76": "Seine-Maritime"}


def get(url, data=None):
    target = CACHE / hashlib.sha256(url.encode() + (data or b"" )).hexdigest()
    if target.exists():
        return target.read_text()
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0 (compatible; MonCarnetRando/1.0)"})
            with urllib.request.urlopen(req, timeout=35) as response:
                text = response.read().decode("utf-8")
            target.write_text(text)
            return text
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def attr(text, key):
    match = re.search(r'\b' + re.escape(key) + r'="([^"]*)"', text)
    return html.unescape(match[1]) if match else None


def parse_list(text):
    records = []
    chunks = re.split(r'<li\b[^>]*\bdata-wpet-offer="', text)[1:]
    for chunk in chunks:
        post_id = int(chunk.split('"')[0])
        source_id = attr(chunk, "data-layer-wpet-offer-id")
        official = re.search(r'href="(https://www\.normandie-tourisme\.fr/itineraire/[^"?#]+)', chunk)
        if not official or not source_id:
            raise ValueError(f"Unrecognised official card {post_id}")
        distance = re.search(r'([\d]+(?:[,.]\d+)?)\s*km', html.unescape(re.sub('<[^>]+>', ' ', chunk)))
        department = re.search(r'(?:ITINOR|R)0?(14|27|50|61|76)', source_id)
        records.append({
            "sourceId": source_id, "postId": post_id,
            "name": attr(chunk, "data-layer-wpet-offer-title"),
            "town": attr(chunk, "data-layer-wpet-offer-location"),
            "department": department[1] if department else None,
            "km": float(distance[1].replace(',', '.')) if distance else None,
            "official": html.unescape(official[1]),
            "gpxSource": attr(chunk, "data-gpx"),
        })
    return records


def page(number):
    url = BASE if number == 1 else BASE + f"page/{number}/"
    try:
        text = get(url)
        current = re.search(r'"paged":"(\d+)"', text)
        assert current and int(current[1]) == number, "Pagination returned another page"
        return {"page": number, "url": url, "records": parse_list(text), "sha256": hashlib.sha256(text.encode()).hexdigest()}
    except Exception as error:
        return {"page": number, "url": url, "error": str(error), "records": []}


def batch(number):
    url = "https://www.normandie-tourisme.fr/wp-json/wp-etourisme/query/search"
    params = {"idPage": "792", "lang": "fr", "langCode": "fr", "request": BASE,
              "posts_per_page": "100", "paged": str(number), "type": "pagination"}
    try:
        text = get(url, urllib.parse.urlencode(params).encode())
        data = json.loads(text)
        records = parse_list(data["templates"]["offers"])
        positions = {p["ID"]: p["wpetFields"].get("geo") for p in data.get("data", [])}
        for record in records:
            position = positions.get(record["postId"])
            if position:
                record["officialLocation"] = position["coordinates"]
        return {"page": number, "url": url, "parameters": params, "records": records,
                "apiReportedTotal": data["results"], "sha256": hashlib.sha256(text.encode()).hexdigest()}
    except Exception as error:
        return {"page": number, "url": url, "error": str(error), "records": []}


def collect():
    first = get(BASE)
    match = re.search(r'résultat\(s\) sur\s*(\d+)', first)
    assert match, "Official total not found"
    total = int(match[1])
    pages = math.ceil(total / 100)
    records, reports = {}, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(batch, range(1, pages + 1)):
            reports.append({k: v for k, v in result.items() if k != "records"})
            for r in result["records"]:
                records[r["sourceId"]] = r
            print(f"Lot {result['page']}/{pages}: {len(records)} annonces · {result.get('error', 'OK')}", flush=True)
    result = {"checkedAt": DATE, "source": BASE, "announcedTotal": total,
              "collectedTotal": len(records), "allPagesCollected": all("error" not in r for r in reports),
              "scope": "Catalogue régional des itinéraires pédestres publiés par Normandie Tourisme ; ne constitue pas le recensement de tous les chemins normands.",
              "pages": reports, "records": list(records.values())}
    target = ROOT / "catalogue/inventaire-regional.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {target}: {len(records)}/{total}", flush=True)


if __name__ == "__main__":
    collect()
