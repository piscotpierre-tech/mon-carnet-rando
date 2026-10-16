import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';

function harness(){
  const events={},stores=new Map();let offline=false,httpStale=false;
  const address=x=>typeof x==='string'?x:x.url;
  const caches={
    async open(name){if(!stores.has(name))stores.set(name,new Map());const store=stores.get(name);return {
      async addAll(urls){for(const u of urls)store.set(address(u),new Response('shell:'+address(u)));},
      async match(request){return store.get(address(request))?.clone();},
      async put(request,response){store.set(address(request),response.clone());},
    };},
    async keys(){return [...stores.keys()];},async delete(name){return stores.delete(name);},
  };
  const self={location:{href:'https://exemple.github.io/mon-carnet-rando/sw.js'},addEventListener:(name,fn)=>events[name]=fn,skipWaiting:()=>Promise.resolve(),clients:{claim:()=>Promise.resolve()}};
  const fetch=async (request,options)=>{if(offline)throw new Error('Offline');const r=new Response((httpStale&&options?.cache!=='no-cache'?'http-cache:':'network:')+address(request));Object.defineProperty(r,'type',{value:'basic'});return r;};
  vm.runInNewContext(fs.readFileSync(new URL('../sw.js',import.meta.url),'utf8'),{self,caches,URL,fetch,Response,Request});
  return {stores,caches,offline(value){offline=value;},staleHttpCache(value){httpStale=value;},async lifecycle(name){let promise;events[name]({waitUntil:p=>promise=p});await promise;},async request(url,{mode='cors',method='GET'}={}){let promise;events.fetch({request:{url,mode,method},respondWith:p=>promise=p});return promise;}};
}

test('le cache de l’application fonctionne dans un sous-dossier GitHub Pages',async()=>{
  const h=harness();await h.lifecycle('install');
  const keys=[...h.stores.get('pierre-rando-v1-shell').keys()];
  assert(keys.includes('https://exemple.github.io/mon-carnet-rando/index.html'));
  assert(keys.every(k=>k.startsWith('https://exemple.github.io/mon-carnet-rando/')));
  for(const name of ['app.js','styles.css','data.js','core.js','catalogue-routes.js'])assert(keys.includes('https://exemple.github.io/mon-carnet-rando/'+name+'?v=normandie-20261016-r2'));
  h.offline(true);
  const r=await h.request('https://exemple.github.io/mon-carnet-rando/',{mode:'navigate'});
  assert.match(await r.text(),/index.html/);
});
test('une carte d’origine ou une nouvelle carte IGN garde son fond après la perte du réseau',async()=>{
  const h=harness();await h.lifecycle('install');
  for(const path of ['maps/19.webp','maps/35-ign.webp','thumbs/35-ign.webp','profiles/35.json','profiles/19-source.gpx']) {
    h.offline(false);
    const url='https://exemple.github.io/mon-carnet-rando/assets/'+path;
    const first=await h.request(url);assert.equal(await first.text(),'network:'+url);
    h.offline(true);const second=await h.request(url);assert.equal(await second.text(),'network:'+url);
  }
});
test('le code se rafraîchit malgré un cache HTTP ancien et retombe sur sa copie sans réseau',async()=>{
  const h=harness();await h.lifecycle('install');
  h.staleHttpCache(true);
  const url='https://exemple.github.io/mon-carnet-rando/app.js';
  const live=await h.request(url);assert.equal(await live.text(),'network:'+url);
  h.offline(true);
  const cached=await h.request(url);assert.equal(await cached.text(),'network:'+url);
});
test('le service worker laisse tranquilles les autres dépôts et sites externes',async()=>{
  const h=harness();
  assert.equal(await h.request('https://exemple.github.io/forge/index.html'),undefined);
  assert.equal(await h.request('https://www.google.com/maps/'),undefined);
  assert.equal(await h.request('https://exemple.github.io/mon-carnet-rando/',{method:'POST'}),undefined);
});
test('l’activation nettoie ses anciennes versions en préservant les caches d’autres applications',async()=>{
  const h=harness();await h.caches.open('forge-cache-v9');await h.caches.open('pierre-rando-v0-shell');await h.caches.open('pierre-rando-v1-assets');
  await h.lifecycle('activate');
  assert(h.stores.has('forge-cache-v9'));assert(h.stores.has('pierre-rando-v1-assets'));assert(!h.stores.has('pierre-rando-v0-shell'));
});

test('les traces téléchargées restent lisibles sans réseau et Leaflet est embarqué',async()=>{
  const h=harness();await h.lifecycle('install');
  for(const filename of ['31.geojson','31.gpx']) {
    const url='https://exemple.github.io/mon-carnet-rando/assets/traces/'+filename;
    const assets=await h.caches.open('pierre-rando-v1-assets');await assets.put(url,new Response('saved:'+filename));
    h.offline(true);assert.equal(await (await h.request(url)).text(),'saved:'+filename);
  }
  const shell=h.stores.get('pierre-rando-v1-shell');
  assert(shell.has('https://exemple.github.io/mon-carnet-rando/assets/vendor/leaflet/leaflet.js'));
  assert(shell.has('https://exemple.github.io/mon-carnet-rando/assets/vendor/leaflet/leaflet.css'));
  assert.equal(await h.request('https://tile.openstreetmap.org/13/4070/2800.png'),undefined);
});
