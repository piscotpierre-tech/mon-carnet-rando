"""Build validated circuits, maps, profiles and the coverage report before deploy.

No map is downloaded by the user's phone until requested. The published maps
are self-contained local WebP files, with no OSM bulk tile download. Failed
documents remain visible in the coverage report instead of becoming fake routes.
"""
import concurrent.futures
import gzip
import hashlib
import importlib
import inspect
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
prepare = importlib.import_module('prepare-catalogue')
maps = importlib.import_module('build-maps')
elevations = importlib.import_module('build-elevations')
comparison = importlib.import_module('trace-comparison')
GENERATED = ROOT / '.generated-catalogue'
GENERATED.mkdir(exist_ok=True)
for folder in ['assets/maps', 'assets/thumbs', 'assets/profiles', 'assets/traces', 'records']:
    (GENERATED / folder).mkdir(parents=True, exist_ok=True)
maps.ROOT = elevations.ROOT = GENERATED
DEPARTMENTS = prepare.source.DEPARTMENTS
DATE = prepare.source.DATE


def rendering_version():
    # Inventory-only changes must not download hundreds of identical maps again.
    # Keep compatibility with the first published renderer while its actual
    # geometry, map and profile recipes remain byte-for-byte unchanged.
    signature=hashlib.sha256((ROOT/'scripts/build-maps.py').read_bytes()+
        (ROOT/'scripts/build-elevations.py').read_bytes()+inspect.getsource(build_map).encode()+
        inspect.getsource(write_geometry).encode()+
        inspect.getsource(build).split('    try:\n        write_geometry',1)[1].encode()).hexdigest()
    return ('a88eac0bb75023206d3e52772bb5f47268b2754f1bed58087937f7d60c95db5e'
            if signature=='7a0bdbf02de9aaf7f5e8b839b23b709026b3b96de636ce39f2a03ae8b7c365a2' else signature)


def canonical(segments):
    """Exact geometry duplicates, allowing reversed direction and loop rotation."""
    parts = []
    for segment in segments:
        points = [(round(p[0], 6), round(p[1], 6)) for p in segment]
        points = [p for i,p in enumerate(points) if not i or p != points[i-1]]
        closed = len(points)>2 and points[0] == points[-1]
        if closed:
            points.pop()
            # Lexicographic minimum is stable even when a GPX starts elsewhere.
            def rotation(values):
                minimum = min(values)
                candidates = [i for i,p in enumerate(values) if p == minimum]
                return min(tuple(values[i:] + values[:i]) for i in candidates)
            key = min(rotation(points), rotation(points[::-1]))
        else:
            key = min(tuple(points), tuple(points[::-1]))
        parts.append(key)
    return hashlib.sha256(repr(sorted(parts)).encode()).hexdigest()


def build_map(route):
    """One WMS request per circuit; thumbnail is resized from the same full map."""
    raw_geo = (GENERATED / route['trace']).read_bytes()
    geometry = json.loads(raw_geo)['geometry']
    coordinates = [geometry['coordinates']] if geometry['type']=='LineString' else geometry['coordinates']
    segments = [[maps.project(*p) for p in s] for s in coordinates]
    bbox = maps.extent([p for s in segments for p in s])
    size = maps.SIZES['map']
    image, url, source_hash = maps.background(bbox, size)
    maps.draw_map(image, bbox, segments)
    metadata = {'routeId':route['id'], 'provider':'IGN', 'layer':maps.LAYER,
                'licence':'Licence Ouverte / Open Licence 2.0', 'fetchedAt':DATE,
                'crs':'EPSG:3857', 'bbox':bbox,
                'bounds':[maps.inverse(bbox[0],bbox[1]),maps.inverse(bbox[2],bbox[3])],
                'traceSha256':hashlib.sha256(raw_geo).hexdigest(), 'images':{}}
    for kind, dimensions in maps.SIZES.items():
        relative = route[kind]
        output = image if kind=='map' else image.resize(dimensions, maps.Image.Resampling.LANCZOS)
        target = GENERATED / relative
        output.save(target, 'WEBP', quality=86, method=4)
        metadata['images'][kind]={'path':relative,'width':dimensions[0],'height':dimensions[1],
                                 'wmsUrl':url,'backgroundSha256':source_hash,
                                 'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    (GENERATED / f"assets/maps/{route['id']}-ign.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    route['mapBounds']=metadata['bounds']


def write_geometry(route, segments):
    geo={'type':'Feature','properties':{'source':route['gpxSource'],'sourceId':route['sourceId']},
         'geometry':{'type':'LineString' if len(segments)==1 else 'MultiLineString',
                     'coordinates':segments[0] if len(segments)==1 else segments}}
    (GENERATED / route['trace']).write_text(json.dumps(geo,ensure_ascii=False,separators=(',',':'))+'\n')
    # Geometry is reserialized as GPX: no gap between segments is joined.
    root=ET.Element('gpx',{'version':'1.1','creator':'Mon carnet rando','xmlns':'http://www.topografix.com/GPX/1/1'})
    track=ET.SubElement(root,'trk');ET.SubElement(track,'name').text=route['name']
    for segment in segments:
        trkseg=ET.SubElement(track,'trkseg')
        for point in segment:
            p=ET.SubElement(trkseg,'trkpt',{'lon':str(point[0]),'lat':str(point[1])})
            if len(point)>2:ET.SubElement(p,'ele').text=str(point[2])
    ET.ElementTree(root).write(GENERATED / route['gpx'],encoding='utf-8',xml_declaration=True)


def build(record):
    r=record['route']
    checkpoint=GENERATED / f"records/{r['id']}.json"
    source_hash=hashlib.sha256((rendering_version()+json.dumps(record,ensure_ascii=False,sort_keys=True)).encode()).hexdigest()
    if checkpoint.exists():
        old=json.loads(checkpoint.read_text())
        if old.get('sourceHash')==source_hash:
            return old
    result={'sourceId':record['sourceId'],'routeId':r['id'],'sourceHash':source_hash}
    try:
        write_geometry(r,record['segments'])
        build_map(r)
    except Exception as error:
        return {**result,'status':'carte-indisponible','issue':str(error)}
    try:
        heights=[p[2] for s in record['segments'] for p in s if len(p)>2]
        all_heights=len(heights)==r['tracePointCount'] and all(-25<=h<=1500 for h in heights)
        try:
            # A common ground model avoids accumulating arbitrary GPX noise.
            elevations.build(r)
        except Exception:
            if not (all_heights and max(heights)-min(heights)>.5):
                raise
            r['elevationMethod']='gpx'
            elevations.build(r)
        r['elevation']=json.loads((GENERATED / f"assets/profiles/{r['id']}.json").read_text())['summary']
    except Exception as error:
        r.pop('elevationMethod',None)
        r['elevationIssue']='Relief non calculable avec les données disponibles.'
        result['elevationIssue']=str(error)
    result.update(status='integre',route=r)
    checkpoint.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    return result


def main():
    inventory=json.loads((ROOT / 'catalogue/inventaire-regional.json').read_text())
    regional_total=inventory['collectedTotal']
    extra_path=ROOT/'catalogue/inventaire-complementaire.json'
    extra=json.loads(extra_path.read_text()) if extra_path.exists() else {'records':[],'overrides':[],'sources':[]}
    overrides={r['sourceId']:r for r in extra['overrides']}
    inventory['records']=[overrides.get(r['sourceId'],r) for r in inventory['records']]+extra['records']
    originals=json.loads(subprocess.check_output(['node','--input-type=module','-e',
        "import{ORIGINAL_ROUTES}from'./data.js';console.log(JSON.stringify(ORIGINAL_ROUTES))"],cwd=ROOT))
    ids_path=ROOT / 'catalogue/route-ids.json'
    ids=json.loads(ids_path.read_text())
    snapshots={}
    for path in sorted((ROOT / 'catalogue/snapshots').glob('*.json.gz')):
        snapshots.update({r['sourceId']:r for r in json.loads(gzip.decompress(path.read_bytes()))})
    if '--local-snapshot' in sys.argv:
        # A local checkpoint is useful while downloading the remaining sources.
        snapshots.update({r['sourceId']:r for r in json.loads((ROOT / 'catalogue/preparation.json').read_text())})
    records=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for i,r in enumerate(pool.map(lambda r:snapshots.get(r['sourceId']) or prepare.validate(r),inventory['records']),1):
            records.append(r)
            if i%50==0:print(f"Sources {i}/{len(inventory['records'])}",flush=True)
    by_url={r.get('gpxSource') or r.get('elevationTraceSource'):r for r in originals if r.get('gpxSource') or r.get('elevationTraceSource')}
    by_name={(prepare.normal(r['name']),prepare.normal(r['town'])):r for r in originals}
    geometry_keys={};geometry_shapes=[]
    for r in originals:
        if r.get('trace'):
            geo=json.loads((ROOT/r['trace']).read_text())['geometry']
            segs=[geo['coordinates']] if geo['type']=='LineString' else geo['coordinates']
            geometry_keys[canonical(segs)]=r['id']
            geometry_shapes.append((r['id'],comparison.describe(segs)))
        elif r.get('elevationTrace'):
            segs=prepare.parse((ROOT/r['elevationTrace']).read_bytes())
            geometry_keys[canonical(segs)]=r['id']
            geometry_shapes.append((r['id'],comparison.describe(segs)))
    candidates=[];report=[]
    for record in records:
        item={k:v for k,v in record.items() if k!='segments'}
        existing=by_url.get(record.get('gpxSource')) if record.get('gpxSource') else None
        name_match=by_name.get((prepare.normal(record['name']),prepare.normal(record['town'])))
        if not existing and name_match and record.get('km') and abs(record['km']-name_match['km'])<=max(.4,name_match['km']*.08):
            existing=name_match
        if existing:
            item.update(status='deja-present',routeId=existing['id'],duplicateReason='Même GPX publié ou même nom, commune et distance compatible')
        elif record['status']=='trace-verifiee' and record.get('department'):
            key=canonical(record['segments'])
            shape=None;near_match=None
            if key not in geometry_keys:
                shape=comparison.describe(record['segments'])
                near_match=next((identifier for identifier,previous in geometry_shapes if comparison.equivalent(shape,previous)),None)
            if near_match is not None:
                item.update(status='doublon-geometrique-proche',routeId=near_match,duplicateReason='Tracés comparés dans les deux sens tous les 4 m : écart observé ≤ 2 m, longueurs compatibles à 1 %.')
            elif key in geometry_keys:
                item.update(status='doublon-geometrique',routeId=geometry_keys[key],duplicateReason='Géométrie identique, indépendamment du départ et du sens')
            else:
                route_id=ids[record['sourceId']]
                geometry_keys[key]=route_id
                geometry_shapes.append((route_id,shape or comparison.describe(record['segments'])))
                km=record.get('km') or round(record['geometryKm'],1)
                coordinate=record['segments'][0][0][:2]
                r={'id':route_id,'sourceId':record['sourceId'],'name':record['name'],'town':record['town'],
                   'km':km,'distanceEstimated':not bool(record.get('km')),
                   'department':record['department'],'departmentName':DEPARTMENTS[record['department']],
                   'start':'Premier point du GPX officiel','startCoordinate':coordinate,'departurePrecision':'gpx',
                   'marking':'Non renseigné','ambiguous':False,
                   'note':'Le point de départ correspond au début du GPX ; il ne garantit pas un parking. Vérifie la fiche officielle avant de partir.',
                   'isNew':True,'catalogue':True,'official':record['official'],'sourceCheckedAt':DATE,
                   'gpxSource':record.get('gpxSource') or record['sourceTraceUrl'],
                   'gpx':f'assets/traces/{route_id}.gpx','trace':f'assets/traces/{route_id}.geojson',
                   'tracePointCount':record['pointCount'],'geometryKm':record['geometryKm'],
                   'map':f'assets/maps/{route_id}-ign.webp','thumb':f'assets/thumbs/{route_id}-ign.webp','basemap':'IGN Plan IGN'}
                if record.get('gpxSha256'):r['gpxSourceSha256']=record['gpxSha256']
                if record.get('sourceFormat')=='GeoJSON':
                    r.update(originalFormat='GeoJSON',sourceEdition=record['sourceEdition'],
                             sourceDatasetSha256=record['sourceDatasetSha256'],sourceFeatureId=record['sourceFeatureId'],
                             start='Premier point du tracé officiel',departurePrecision='trace',
                             note=f"Tracé officiel : {record['sourceEdition']}. Le premier point du tracé ne garantit pas un parking. La distance est calculée sur la géométrie publiée.")
                if record.get('sourceDeparture'):
                    r['start']=record['sourceDeparture']
                if record.get('sourceParking'):
                    r['startCoordinate']=record['sourceParking']
                    r['departurePrecision']='source'
                    r['note']='Le stationnement et le départ sont indiqués par l’organisme. Vérifie les conditions actuelles sur sa fiche.'
                for field,target in [('sourceDurationMinutes','durationMinutes'),('sourceAscent','elevationGain'),('sourceDescent','elevationLoss')]:
                    if record.get(field) is not None:r[target]=record[field]
                candidates.append({**record,'route':r})
                item.update(status='a-construire',routeId=route_id)
        report.append(item)
    print(f"Construction de {len(candidates)} circuits supplémentaires",flush=True)
    if '--only' in sys.argv:
        selected=set(sys.argv[sys.argv.index('--only')+1:])
        candidates=[r for r in candidates if r['sourceId'] in selected]
    results={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for i,result in enumerate(pool.map(build,candidates),1):
            results[result['sourceId']]=result
            print(f"Carte {i}/{len(candidates)} · {result['sourceId']} · {result['status']}",flush=True)
    routes=[r['route'] for r in results.values() if r['status']=='integre']
    if '--only' not in sys.argv and len(routes)<len(candidates)*.95:
        raise RuntimeError('Plus de 5 % des cartes ont échoué : publication suspendue, version précédente conservée.')
    available={r['id'] for r in originals+routes}
    for item in report:
        result=results.get(item['sourceId'])
        if result:
            item.update({k:v for k,v in result.items() if k not in ['route','sourceHash']})
        if item.get('routeId') not in available:
            if item['status'] in ['doublon-geometrique','doublon-geometrique-proche']:item.update(status='doublon-a-reprendre',issue='Le circuit de référence n’a pas pu être construit.')
            item.pop('routeId',None)
    for folder in ['maps','thumbs','profiles','traces']:
        shutil.copytree(GENERATED / f'assets/{folder}',ROOT / f'assets/{folder}',dirs_exist_ok=True)
    (ROOT / 'catalogue-routes.js').write_text('export const CATALOGUE_ROUTES = '+json.dumps(routes,ensure_ascii=False,separators=(',',':'))+';\n')
    output={k:v for k,v in inventory.items() if k not in ['records','pages']}
    output.update(records=report,collectedTotal=len(report),regionalTotal=regional_total,sourceCatalogues=extra['sources'],integratedNew=len(routes),usableTotal=len(originals)+len(routes),
                  withProfiles=sum(bool(r.get('elevation')) for r in originals+routes),
                  exhaustiveNormandy=False,departmentReconciliation='À poursuivre : catalogues départementaux, offices locaux et itinéraires non publiés dans ce catalogue régional.')
    (ROOT / 'assets/catalogue.json').write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n')
    print(f"Publié : {len(originals)+len(routes)} circuits utilisables ; {len(report)} références inventoriées",flush=True)


if __name__=='__main__':
    main()
