// Real Chromium smoke test, run after the catalogue has been built.
// Each mobile viewport gets a fresh context and synthetic legacy data only.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, mkdir, stat, writeFile} from 'node:fs/promises';
import {resolve, extname, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import {ROUTES} from '../data.js';
import {APP_ID, STORAGE_KEY, routeMapsUrl} from '../core.js';

const root=resolve(fileURLToPath(new URL('../',import.meta.url)));
const artifacts=resolve(root,'artifacts/browser');
const base='/mon-carnet-rando/';
const departments=['14','27','50','61','76'];
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json','.geojson':'application/geo+json','.gpx':'application/gpx+xml','.webmanifest':'application/manifest+json','.webp':'image/webp','.png':'image/png','.svg':'image/svg+xml'};
const legacy={version:1,favorites:[19,27],trips:[{id:'smoke-legacy-trip',routeId:19,date:'2026-10-15',distance:6.4,minutes:103,rating:5,note:'Souvenir de test à préserver.'}],timer:{routeId:19,elapsedMs:5600,startedAt:null}};
const selected=departments.map(department=>{
  const candidates=ROUTES.filter(r=>r.department===department&&r.basemap&&r.trace&&r.gpx).sort((a,b)=>a.id-b.id);
  const route=candidates.find(r=>r.catalogue&&r.elevation)||candidates.find(r=>r.elevation)||candidates[0];
  assert(route,`No mapped route with GPX in department ${department}`);
  return route;
});

await mkdir(artifacts,{recursive:true});
const server=createServer(async(req,res)=>{
  try {
    const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    if(pathname===base.slice(0,-1)){res.writeHead(302,{Location:base});res.end();return;}
    if(!pathname.startsWith(base)){res.writeHead(404);res.end();return;}
    let filename=resolve(root,pathname.slice(base.length)||'index.html');
    if(!filename.startsWith(root+sep)&&filename!==resolve(root)){res.writeHead(403);res.end();return;}
    if((await stat(filename)).isDirectory())filename=resolve(filename,'index.html');
    const bytes=await readFile(filename);
    res.writeHead(200,{'Content-Type':mime[extname(filename)]||'application/octet-stream','Cache-Control':'no-cache'});
    res.end(req.method==='HEAD'?undefined:bytes);
  } catch {
    res.writeHead(404);res.end('Not found');
  }
});
await new Promise((ok,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',ok);});
const origin=`http://127.0.0.1:${server.address().port}`;
const url=origin+base;
let browser,activePage,stage='launch';
const evidence={base,viewports:[],geojsonExport:null,offline:null};

async function noOverflow(page,label) {
  const dimensions=await page.evaluate(()=>({viewport:innerWidth,width:document.documentElement.scrollWidth,dialogs:[...document.querySelectorAll('dialog[open]')].map(d=>({left:d.getBoundingClientRect().left,right:d.getBoundingClientRect().right}))}));
  assert(dimensions.width<=dimensions.viewport+1,`${label}: horizontal page overflow ${JSON.stringify(dimensions)}`);
  for(const d of dimensions.dialogs)assert(d.left>=-1&&d.right<=dimensions.viewport+1,`${label}: dialog outside viewport`);
}
async function screenshot(page,name) {
  await page.screenshot({path:resolve(artifacts,name+'.png'),animations:'disabled'});
}
async function ready(page) {
  await page.locator('#route-grid .route-card').first().waitFor();
  assert.equal(Number(await page.locator('#total-routes').textContent()),ROUTES.length);
}
async function imageReady(page,selector) {
  await page.locator(selector).waitFor({state:'visible'});
  await page.waitForFunction(selector=>{const img=document.querySelector(selector);return img?.complete&&img.naturalWidth>100&&img.naturalHeight>100;},selector);
}
async function openRoute(page,route) {
  await page.locator('#department').selectOption(route.department);
  await page.locator('#search').fill(String(route.id));
  const card=page.locator(`.card-open[data-id="${route.id}"]`);
  // Numeric IDs normally isolate one card; allow pagination if an ID also
  // occurs in several names or descriptions in a future catalogue.
  for(let n=0;!await card.count()&&n<10&&await page.locator('#load-more').isVisible();n++)await page.locator('#load-more').click();
  await card.click();
  await page.locator('#route-dialog').waitFor({state:'visible'});
  assert.equal(await page.locator('#route-title').textContent(),route.name);
  await imageReady(page,'#route-content .map-preview img');
  if(route.elevation)await page.locator('#elevation-chart .profile-svg').waitFor();
}
async function checkGpx(page,route,label) {
  const link=page.locator(`#route-content a[download][href="./${route.gpx}"]`);
  await link.waitFor();
  if(route.originalFormat==='GeoJSON')assert.match(await link.textContent(),/export GPX/);
  const pending=page.waitForEvent('download');
  await link.click();
  const download=await pending;
  assert.equal(await download.failure(),null,`${label}: GPX download failed`);
  const target=resolve(artifacts,label+'.gpx');
  await download.saveAs(target);
  const xml=await readFile(target,'utf8');
  assert.match(xml,/<(?:\w+:)?gpx\b/);
  assert.match(xml,/<(?:\w+:)?(?:trkpt|rtept)\b/);
}
async function preserved(page) {
  const stored=await page.evaluate(key=>JSON.parse(localStorage.getItem(key)),STORAGE_KEY);
  assert.deepEqual(stored,legacy,'Legacy favorites, trip or paused timer changed');
  assert.equal(await page.locator('#active-timer-time').textContent(),'00:00:05');
  assert.equal(await page.locator('#storage-warning').isVisible(),false);
}
async function backupRoundtrip(page) {
  await page.locator('.bottom-nav [data-nav="carnet"]').click();
  await page.locator('#trip-list').getByText(legacy.trips[0].note,{exact:true}).waitFor();
  const pending=page.waitForEvent('download');
  await page.locator('[data-action="export"]').click();
  const download=await pending;
  assert.equal(await download.failure(),null);
  const bytes=await readFile(await download.path());
  const backup=JSON.parse(bytes);
  assert.equal(backup.app,APP_ID);assert.equal(backup.version,1);
  assert.deepEqual(backup.favorites,legacy.favorites);assert.deepEqual(backup.trips,legacy.trips);
  await page.locator('#import-file').setInputFiles({name:'smoke-roundtrip.json',mimeType:'application/json',buffer:bytes});
  await page.locator('[data-action="confirm-import"]').click();
  await page.locator('#info-dialog').waitFor({state:'hidden'});
  await preserved(page);
  await page.locator('.bottom-nav [data-nav="favoris"]').click();
  for(const id of legacy.favorites)await page.locator(`.card-open[data-id="${id}"]`).waitFor();
  assert.equal(await page.locator('#route-grid .route-card').count(),legacy.favorites.length);
  await page.locator('.bottom-nav [data-nav="explorer"]').click();
}

try {
  browser=await chromium.launch({headless:true});
  for(const width of [360,390,430]) {
    stage=`mobile-${width}`;
    const context=await browser.newContext({viewport:{width,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:1,acceptDownloads:true,locale:'fr-FR',timezoneId:'Europe/Paris',storageState:{cookies:[],origins:[{origin,localStorage:[{name:STORAGE_KEY,value:JSON.stringify(legacy)}]}]}});
    const page=activePage=await context.newPage();
    page.setDefaultTimeout(15000);
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    try {
      await page.goto(url,{waitUntil:'domcontentloaded'});
      await ready(page);await preserved(page);await noOverflow(page,stage);
      await screenshot(page,`${stage}-explorer`);
      await backupRoundtrip(page);
      const checked=[];
      for(const route of selected) {
        stage=`mobile-${width}-${route.department}`;
        await openRoute(page,route);await noOverflow(page,stage+'-fiche');
        const maps=await page.locator('#route-content .maps-departure').getAttribute('href');
        assert.equal(maps,routeMapsUrl(route),`${stage}: incorrect Maps destination`);
        assert.equal(new URL(maps).origin,'https://www.google.com');
        if(route.startCoordinate&&!route.ambiguous)assert.equal(new URL(maps).searchParams.get('destination'),`${route.startCoordinate[1]},${route.startCoordinate[0]}`);
        if(width===390)await checkGpx(page,route,`${stage}-download`);
        await screenshot(page,`${stage}-fiche`);
        await page.locator('#route-content [data-action="map"]').click();
        await imageReady(page,'#map-image');
        assert.equal(new URL(await page.locator('#map-image').getAttribute('src')).pathname,base+route.map);
        await noOverflow(page,stage+'-carte');await screenshot(page,`${stage}-carte`);
        await page.locator('[data-action="close-map"]').click();
        await page.locator('[data-action="close-route"]').click();
        checked.push({department:route.department,routeId:route.id,profile:Boolean(route.elevation),source:route.originalFormat||'GPX'});
      }
      evidence.viewports.push({width,routes:checked,legacyPreserved:true,backupRoundtrip:true});
      if(width===390) {
        const exported=ROUTES.find(r=>r.originalFormat==='GeoJSON');
        if(exported) {
          stage='mobile-390-geojson';
          await openRoute(page,exported);
          await page.locator('#route-content').getByText('Distance calculée sur le tracé officiel',{exact:true}).waitFor();
          const original=page.locator('#route-content').getByRole('link',{name:'Tracé original · GeoJSON',exact:true});
          await original.waitFor();assert.equal(await original.getAttribute('href'),exported.gpxSource);
          await page.locator('#route-content').getByText('Ce GPX est un export du carnet depuis le GeoJSON officiel ; aucun GPX original n’est publié par cette source.',{exact:true}).waitFor();
          await checkGpx(page,exported,'mobile-390-geojson-export');
          await noOverflow(page,stage);await screenshot(page,stage);
          evidence.geojsonExport={routeId:exported.id,exportLabel:true,originalLink:true,distanceLabel:true,gpxDownload:true};
          await page.locator('[data-action="close-route"]').click();
        }
        const route=selected.find(r=>r.department==='50'&&r.elevation)||selected.find(r=>r.elevation);
        assert(route,'Offline test requires a route with a profile');
        stage='offline-390';
        await page.evaluate(async()=>{await navigator.serviceWorker.ready;return true;});
        await page.waitForFunction(()=>Boolean(navigator.serviceWorker.controller));
        await openRoute(page,route);
        await page.locator('#route-content [data-action="download-route"]').click();
        await page.waitForFunction(()=>document.querySelector('#route-cache-status')?.textContent.includes('disponibles hors ligne'));
        await context.setOffline(true);
        await page.reload({waitUntil:'domcontentloaded'});
        await ready(page);await page.locator('#offline-banner').waitFor({state:'visible'});
        await openRoute(page,route);await preserved(page);await noOverflow(page,'offline-fiche');
        await screenshot(page,'offline-390-fiche');
        await checkGpx(page,route,'offline-390-download');
        await page.locator('#route-content [data-action="map"]').click();
        await imageReady(page,'#map-image');await screenshot(page,'offline-390-carte');
        await page.locator('[data-action="close-map"]').click();
        await page.locator('#route-content [data-action="interactive-map"]').click();
        await imageReady(page,'#interactive-map .leaflet-image-layer');
        await page.locator('#interactive-map .leaflet-overlay-pane path').first().waitFor();
        assert.match(await page.locator('#trace-status').textContent(),/Hors ligne.*IGN/);
        await noOverflow(page,'offline-interactive');await screenshot(page,'offline-390-interactive');
        evidence.offline={width,routeId:route.id,shell:true,map:true,interactiveBasemap:true,profile:true,gpxDownload:true,legacyPreserved:true};
        await context.setOffline(false);
      }
      assert.deepEqual(errors,[],`${stage}: uncaught browser errors`);
    } catch(error) {
      await screenshot(page,`${stage}-failure`).catch(()=>{});
      throw error;
    } finally {
      await context.close();activePage=null;
    }
  }
  await writeFile(resolve(artifacts,'report.json'),JSON.stringify(evidence,null,2));
  console.log(`OK: 360/390/430 px, ${selected.length} départements, cartes/profils/Maps/GPX, sauvegarde historique et mode hors ligne réel.`);
} catch(error) {
  if(activePage)await screenshot(activePage,`${stage}-failure`).catch(()=>{});
  await writeFile(resolve(artifacts,'report.json'),JSON.stringify({...evidence,failedStage:stage,error:error.message},null,2));
  throw error;
} finally {
  await browser?.close();
  await new Promise(ok=>server.close(ok));
}
