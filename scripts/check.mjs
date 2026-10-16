import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {ROUTES} from '../data.js';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const app=fs.readFileSync(path.join(root,'app.js'),'utf8');
const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);
assert.equal(ids.length,new Set(ids).size,'Duplicate HTML id');
const refs=[...app.matchAll(/\$\('#([\w-]+)'\)/g)].map(m=>m[1]);
const dynamic=['route-cache-status','route-timer','timer-actions'];
for(const id of refs)assert(ids.includes(id)||dynamic.includes(id),'Missing element: '+id);
let total=0;
for(const r of ROUTES){for(const key of ['map','thumb']){const p=path.join(root,r[key]);assert(fs.existsSync(p),'Missing asset: '+r[key]);assert(fs.statSync(p).size>1000);total+=fs.statSync(p).size;}}
for(const r of ROUTES.filter(r=>r.isNew)) {
  assert(r.official.startsWith('https://'),'Official source missing');
  for(const key of ['trace','gpx'])assert(fs.existsSync(path.join(root,r[key])),'Missing trace: '+r[key]);
  const geo=JSON.parse(fs.readFileSync(path.join(root,r.trace),'utf8'));
  const segments=geo.geometry.type==='LineString'?[geo.geometry.coordinates]:geo.geometry.coordinates;
  const points=segments.flat();assert.equal(points.length,r.tracePointCount);
  assert(points.length>5);assert(points.every(([lon,lat])=>lon>-2.1&&lon<1.9&&lat>48&&lat<50.2),'Trace outside Normandy');
  assert.equal(r.basemap,'IGN Plan IGN','Every new circuit needs a real background map');
  const metadata=JSON.parse(fs.readFileSync(path.join(root,`assets/maps/${r.id}-ign.json`),'utf8'));
  assert.equal(metadata.routeId,r.id);assert.equal(metadata.crs,'EPSG:3857');
  assert.equal(metadata.traceSha256,createHash('sha256').update(fs.readFileSync(path.join(root,r.trace))).digest('hex'),'Map built from a different trace');
  assert.deepEqual(r.mapBounds,metadata.bounds,'Interactive image bounds must match the WMS extent');
  const [x0,y0,x1,y1]=metadata.bbox;
  const [southwest,northeast]=r.mapBounds;
  for(const [lon,lat] of points) {
    const x=6378137*lon*Math.PI/180,y=6378137*Math.log(Math.tan(Math.PI/4+lat*Math.PI/360));
    assert(x>x0&&x<x1&&y>y0&&y<y1,'Route clipped by the background');
    assert(lat>southwest[0]&&lat<northeast[0]&&lon>southwest[1]&&lon<northeast[1]);
  }
  for(const key of ['map','thumb']) {
    const image=fs.readFileSync(path.join(root,r[key]));
    assert.equal(image.toString('ascii',0,4),'RIFF');assert.equal(image.toString('ascii',8,12),'WEBP');
    assert.equal(metadata.images[key].path,r[key]);
    assert.equal(metadata.images[key].sha256,createHash('sha256').update(image).digest('hex'),'Map changed without provenance update');
    const request=new URL(metadata.images[key].wmsUrl);
    assert.equal(request.hostname,'data.geopf.fr');assert.equal(request.searchParams.get('LAYERS'),'GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2');
    assert.deepEqual(request.searchParams.get('BBOX').split(',').map(Number),metadata.bbox.map(v=>Number(v.toFixed(6))));
  }
}
for(const match of html.matchAll(/(?:src|href)="\.\/([^"#]+)"/g))assert(fs.existsSync(path.join(root,match[1].split('?')[0])),'Missing HTML asset: '+match[1]);
const manifest=JSON.parse(fs.readFileSync(path.join(root,'manifest.webmanifest'),'utf8'));
assert.equal(manifest.scope,'./');assert.equal(manifest.start_url,'./#explorer');
for(const icon of manifest.icons)assert(fs.existsSync(path.join(root,icon.src)));
for(const name of ['app.js','core.js','data.js','styles.css','index.html','manifest.webmanifest'])assert(fs.readFileSync(path.join(root,'sw.js'),'utf8').includes(name),'Missing shell asset: '+name);
assert(!/<script[^>]+src="https?:/i.test(html),'Unexpected external script');
assert(!/<link[^>]+href="https?:/i.test(html),'Unexpected external stylesheet');
assert(!/\/assets\//.test(html.replaceAll('./assets/','')),'Assets must use relative paths');
console.log(`OK : ${ROUTES.length} circuits, ${ROUTES.length*2} images, ${ids.length} identifiants HTML uniques. Cartes et aperçus : ${(total/1e6).toFixed(2)} Mo. Chemins relatifs GitHub Pages vérifiés.`);
