"""Build self-contained, georeferenced route maps from the open Plan IGN WMS.

Requires Python 3 + Pillow. Run from any directory; optional route IDs select a
subset. Downloaded backgrounds are cached outside the repository for retries.
The GPX geometry is never simplified or shifted, and both image sizes share
exactly the same EPSG:3857 extent. No OpenStreetMap tiles are downloaded.
"""
import concurrent.futures
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFont, ImageStat

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(tempfile.gettempdir()) / "pierre-rando-plan-ign"
CACHE.mkdir(exist_ok=True)
RADIUS = 6378137
DATE = "2026-10-16"
SERVICE = "https://data.geopf.fr/wms-r/wms"
LAYER = "GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2"
SIZES = {"map": (1960, 1400), "thumb": (700, 500)}


def project(lon, lat, *_):
    return (RADIUS * math.radians(lon),
            RADIUS * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def inverse(x, y):
    return [math.degrees(2 * math.atan(math.exp(y / RADIUS)) - math.pi / 2),
            math.degrees(x / RADIUS)]


def extent(points):
    xs, ys = zip(*points)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    width = max((max(xs) - min(xs)) * 1.36,
                (max(ys) - min(ys)) * 1.36 * 1.4, 2400)
    height = width / 1.4
    return [cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2]


def background(bbox, size):
    query = urllib.parse.urlencode({
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
        "LAYERS": LAYER, "STYLES": "normal", "CRS": "EPSG:3857",
        "BBOX": ",".join(f"{v:.6f}" for v in bbox),
        "WIDTH": size[0], "HEIGHT": size[1], "FORMAT": "image/png",
        "TRANSPARENT": "FALSE",
    })
    url = SERVICE + "?" + query
    cached = CACHE / (hashlib.sha256(url.encode()).hexdigest() + ".png")
    for attempt in range(3):
        try:
            if cached.exists():
                raw = cached.read_bytes()
            else:
                request = urllib.request.Request(url, headers={
                    "User-Agent": "MonCarnetRando/1.0 (+https://github.com/piscotpierre-tech/mon-carnet-rando)"
                })
                with urllib.request.urlopen(request, timeout=40) as response:
                    raw = response.read()
            image = Image.open(io.BytesIO(raw)).convert("RGB")
            assert image.size == size, "Unexpected WMS dimensions"
            assert max(ImageStat.Stat(image).stddev) > 10, "Empty basemap"
            cached.write_bytes(raw)
            return image, url, hashlib.sha256(raw).hexdigest()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def font(size, bold=False):
    suffix = "-Bold" if bold else ""
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/DejaVuSans{suffix}.ttf", size)


def draw_map(image, bbox, segments):
    w, h = image.size
    scale = w / 700
    draw = ImageDraw.Draw(image)
    x0, y0, x1, y1 = bbox
    def pixel(point):
        x, y = point
        return ((x - x0) / (x1 - x0) * w, (y1 - y) / (y1 - y0) * h)
    for segment in segments:
        pixels = [pixel(p) for p in segment]
        draw.line(pixels, fill="white", width=round(9 * scale), joint="curve")
        draw.line(pixels, fill="#bd492a", width=round(5 * scale), joint="curve")
    # The GPX's first point is labelled honestly; it is not a surveyed parking.
    sx, sy = pixel(segments[0][0])
    radius = 10 * scale
    draw.ellipse((sx-radius, sy-radius, sx+radius, sy+radius), fill="#173f38", outline="white", width=round(3*scale))
    small = font(round(11*scale))
    legend = "Tracé officiel  •  ● Premier point GPX"
    draw.rounded_rectangle((10*scale, h-49*scale, 296*scale, h-25*scale), radius=4*scale, fill="white")
    draw.text((18*scale, h-44*scale), legend, font=small, fill="#173f38")
    credit = f"© IGN – Plan IGN • Licence Ouverte 2.0 • {DATE}"
    draw.rectangle((0, h-21*scale, w, h), fill="white")
    draw.text((10*scale, h-18*scale), credit, font=font(round(10*scale)), fill="#30443e")
    # North is up in the chosen projection.
    draw.text((w-25*scale, 12*scale), "N", font=font(round(13*scale), True), fill="#173f38")
    draw.line((w-20*scale, 52*scale, w-20*scale, 33*scale), fill="#173f38", width=round(2*scale))
    draw.polygon([(w-20*scale, 27*scale), (w-24*scale, 35*scale), (w-16*scale, 35*scale)], fill="#173f38")
    return image


def build(route):
    raw_geo = (ROOT / route["trace"]).read_bytes()
    geo = json.loads(raw_geo)
    coords = geo["geometry"]["coordinates"]
    if geo["geometry"]["type"] == "LineString":
        coords = [coords]
    segments = [[project(*p) for p in segment] for segment in coords]
    bbox = extent([p for segment in segments for p in segment])
    metadata = {
        "routeId": route["id"], "provider": "IGN", "layer": LAYER,
        "licence": "Licence Ouverte / Open Licence 2.0", "fetchedAt": DATE,
        "crs": "EPSG:3857", "bbox": bbox,
        "bounds": [inverse(bbox[0], bbox[1]), inverse(bbox[2], bbox[3])],
        "traceSha256": hashlib.sha256(raw_geo).hexdigest(), "images": {},
    }
    for kind, size in SIZES.items():
        image, url, source_hash = background(bbox, size)
        draw_map(image, bbox, segments)
        relative = f"assets/{'maps' if kind == 'map' else 'thumbs'}/{route['id']}-ign.webp"
        target = ROOT / relative
        image.save(target, "WEBP", quality=91, method=6)
        metadata["images"][kind] = {
            "path": relative, "width": size[0], "height": size[1], "wmsUrl": url,
            "backgroundSha256": source_hash,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
    (ROOT / f"assets/maps/{route['id']}-ign.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    print(f"OK {route['id']} · {route['name']}", flush=True)


if __name__ == "__main__":
    data = subprocess.check_output(["node", "--input-type=module", "-e",
        "import {ROUTES} from './data.js'; console.log(JSON.stringify(ROUTES.filter(r=>r.isNew)))"], cwd=ROOT)
    routes = json.loads(data)
    selected = set(map(int, sys.argv[1:]))
    if selected:
        routes = [r for r in routes if r["id"] in selected]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(build, routes))
