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


def historical_match(record, by_url, by_name, original_shapes):
    """A similar label is an audit hint, never proof that a trace is redundant."""
    hints = {}
    existing = by_url.get(record.get('gpxSource')) if record.get('gpxSource') else None
    if existing and record.get('segments') and existing['id'] in original_shapes:
        equivalent = comparison.equivalent(comparison.describe(record['segments']), original_shapes[existing['id']])
        hints['historicalSourceMatch'] = {
            'routeId': existing['id'],
            'geometryComparison': 'equivalente' if equivalent else 'differente',
            'reason': 'Même URL GPX ; comparaison avec la trace historique conservée.',
        }
        # An official URL can be updated in place. Keep a divergent trace rather
        # than silently discarding it because its download address is unchanged.
        if not equivalent:
            existing = None
    name_match = by_name.get((prepare.normal(record['name']), prepare.normal(record['town'])))
    if name_match and record.get('km') and abs(record['km'] - name_match['km']) <= max(.4, name_match['km'] * .08):
        hints['historicalNameMatch'] = {
            'routeId': name_match['id'], 'status': 'a-verifier',
            'reason': 'Même nom, commune et distance compatible ; rapprochement nominal non confirmé.',
        }
    return existing, hints


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


def retry_cached_elevation(cached, record, checkpoint):
    """Retry only missing relief; retain the already built map and geometry."""
    r = cached['route']
    if not all((GENERATED / r[field]).is_file() for field in ['trace', 'gpx']):
        # A profile must never be built against an absent cached source. The
        # final file checks will identify this incomplete cache separately.
        return cached
    try:
        heights = [p[2] for s in record['segments'] for p in s if len(p) > 2]
        all_heights = len(heights) == r['tracePointCount'] and all(-25 <= h <= 1500 for h in heights)
        try:
            elevations.build(r)
        except Exception:
            if not (all_heights and max(heights) - min(heights) > .5):
                raise
            r['elevationMethod'] = 'gpx'
            elevations.build(r)
        r['elevation'] = json.loads((GENERATED / f"assets/profiles/{r['id']}.json").read_text())['summary']
        r.pop('elevationIssue', None)
        cached.pop('elevationIssue', None)
    except Exception as error:
        r.pop('elevationMethod', None)
        r['elevationIssue'] = 'Relief non calculable avec les données disponibles.'
        cached['elevationIssue'] = str(error)
    checkpoint.write_text(json.dumps(cached, ensure_ascii=False, separators=(',', ':')) + '\n')
    return cached


def build(record):
    r=record['route']
    checkpoint=GENERATED / f"records/{r['id']}.json"
    source_hash=hashlib.sha256((rendering_version()+json.dumps(record,ensure_ascii=False,sort_keys=True)).encode()).hexdigest()
    if checkpoint.exists():
        old=json.loads(checkpoint.read_text())
        if old.get('sourceHash')==source_hash:
            return retry_cached_elevation(old, record, checkpoint) if old.get('elevationIssue') else old
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


def catalogue_aliases(report, ids, originals, routes):
    """Keep saved references usable when another source becomes canonical."""
    original_ids = {r['id'] for r in originals}
    available = original_ids | {r['id'] for r in routes}
    aliases = {}
    for record in report:
        reserved = ids.get(record['sourceId'])
        target = record.get('routeId')
        if reserved is None or target not in available or reserved == target:
            continue
        if reserved in original_ids or reserved in available:
            raise ValueError(f'Un circuit conservé ne peut pas devenir un alias : {reserved}')
        aliases[reserved] = target
    return aliases


def main():
    inventory=json.loads((ROOT / 'catalogue/inventaire-regional.json').read_text())
    regional_total=inventory['collectedTotal']
    extra={'records':[],'overrides':[],'sources':[]}
    for path in sorted((ROOT/'catalogue').glob('inventaire-*.json')):
        if path.name=='inventaire-regional.json':continue
        additional=json.loads(path.read_text())
        for field in extra:extra[field].extend(additional.get(field,[]))
    overrides={r['sourceId']:r for r in extra['overrides']}
    inventory['records']=[overrides.get(r['sourceId'],r) for r in inventory['records']]+extra['records']
    source_ids=[r['sourceId'] for r in inventory['records']]
    if len(source_ids)!=len(set(source_ids)):
        raise ValueError('Un identifiant source est présent dans plusieurs inventaires : rapprochement requis avant publication.')
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
    geometry_keys={};geometry_shapes=[];original_shapes={}
    for r in originals:
        if r.get('trace'):
            geo=json.loads((ROOT/r['trace']).read_text())['geometry']
            segs=[geo['coordinates']] if geo['type']=='LineString' else geo['coordinates']
            geometry_keys[canonical(segs)]=r['id']
            original_shapes[r['id']]=comparison.describe(segs)
            geometry_shapes.append((r['id'],original_shapes[r['id']]))
        elif r.get('elevationTrace'):
            segs=prepare.parse((ROOT/r['elevationTrace']).read_bytes())
            geometry_keys[canonical(segs)]=r['id']
            original_shapes[r['id']]=comparison.describe(segs)
            geometry_shapes.append((r['id'],original_shapes[r['id']]))
    candidates=[];report=[]
    for record in records:
        item={k:v for k,v in record.items() if k!='segments'}
        existing,hints=historical_match(record,by_url,by_name,original_shapes)
        item.update(hints)
        if existing:
            item.update(status='deja-present',routeId=existing['id'],duplicateReason='Même source GPX publiée, sans divergence géométrique constatée.')
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
                if record.get('pdf') or record.get('sourcePdf'):r['pdf']=record.get('pdf') or record['sourcePdf']
                if record.get('sourceMarking'):r['marking']=record['sourceMarking']
                if record.get('sourceDifficulty'):r['difficulty']=record['sourceDifficulty']
                for field in ['sourceEdition','sourceApi','sourceApiSha256','sourceApiPages','sourceAdvisedParking','sourcePdfs','sourceDownloadReferer','sourceAlternativePage','sourceScopeConflict','sourceDatasetSha256','sourceFeatureId','sourceUpdatedAt','sourceCityCodes','sourceDepartureCityCode','scopeEvidence','gpxRepairs','validatedGpxSha256']:
                    if record.get(field) is not None:r[field]=record[field]
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
                if record.get('scopeEvidence',{}).get('departureInNormandy') is False:
                    r['note']+=' Parcours interdépartemental : le départ publié est hors de Normandie ; des communes normandes traversées sont explicitement indiquées par le portail.'
                if record.get('sourceEdition') and record.get('sourceFormat')!='GeoJSON':
                    r['note']+=' Source : '+str(record['sourceEdition'])+'.'
                parking_text=record.get('sourceParkingDescription') or record.get('sourceAdvisedParking')
                if parking_text:
                    r['note']+=' Stationnement indiqué par l’organisme : '+str(parking_text)+'.'
                if record.get('gpxRepairs'):
                    r['note']+=' Un défaut de format du fichier officiel a été corrigé sans modifier ses coordonnées ; le fichier original reste accessible.'
                if record.get('sourceScopeConflict'):
                    r['note']+=' '+record['sourceScopeConflict']
                for field,target in [('sourceDurationMinutes','durationMinutes'),('sourceAscent','elevationGain'),('sourceDescent','elevationLoss')]:
                    if record.get(field) is not None:r[target]=record[field]
                if hints:
                    r.update(hints)
                    r['note']+=' Une fiche historique ressemble à ce parcours ; leur correspondance reste à vérifier, les traces sont conservées séparément.'
                candidates.append({**record,'route':r})
                item.update(status='a-construire',routeId=route_id)
        elif record['status']=='trace-verifiee':
            item.update(status='departement-a-verifier',issue='Répartition départementale du parcours à confirmer avant intégration.')
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
    aliases=catalogue_aliases(report,ids,originals,routes)
    (ROOT / 'catalogue-routes.js').write_text('export const CATALOGUE_ROUTES = '+json.dumps(routes,ensure_ascii=False,separators=(',',':'))+';\n'
        +'export const CATALOGUE_ALIASES = '+json.dumps(aliases,separators=(',',':'))+';\n')
    output={k:v for k,v in inventory.items() if k not in ['records','pages']}
    output.update(records=report,collectedTotal=len(report),regionalTotal=regional_total,sourceCatalogues=extra['sources'],integratedNew=len(routes),usableTotal=len(originals)+len(routes),
                  withProfiles=sum(bool(r.get('elevation')) for r in originals+routes),
                  exhaustiveNormandy=False,departmentReconciliation='À poursuivre : autres registres officiels, offices locaux, GR et variantes ; les références sans trace exploitable restent identifiées.')
    (ROOT / 'assets/catalogue.json').write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n')
    print(f"Publié : {len(originals)+len(routes)} circuits utilisables ; {len(report)} références inventoriées",flush=True)


if __name__=='__main__':
    main()
