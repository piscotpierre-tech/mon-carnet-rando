const PREFIX='pierre-rando-v1-';
const SHELL=PREFIX+'shell';
const ASSETS=PREFIX+'assets';
const ROOT=new URL('./',self.location.href);
const INDEX=new URL('index.html',ROOT).href;
const FILES=['./','index.html','styles.css?v=normandie-20261016','app.js?v=normandie-20261016','core.js?v=normandie-20261016','data.js?v=normandie-20261016','catalogue-routes.js?v=normandie-20261016','manifest.webmanifest','assets/catalogue.json','assets/icons/icon-192.png','assets/icons/icon-512.png','assets/vendor/leaflet/leaflet.js','assets/vendor/leaflet/leaflet.css'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(SHELL).then(cache=>cache.addAll(FILES.map(p=>new Request(new URL(p,ROOT).href,{cache:'reload'})))).then(()=>self.skipWaiting()));});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('pierre-rando-')&&!k.startsWith(PREFIX)).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',event=>{
  const request=event.request,url=new URL(request.url);
  if(request.method!=='GET'||url.origin!==ROOT.origin||!url.pathname.startsWith(ROOT.pathname))return;
  if(request.mode==='navigate'){
    event.respondWith((async()=>{try{const response=await fetch(request,{cache:'no-cache'});if(response.ok){const c=await caches.open(SHELL);await c.put(INDEX,response.clone());}return response;}catch{return (await caches.open(SHELL)).match(INDEX);}})());return;
  }
  const mapPath=url.pathname.startsWith(new URL('assets/profiles/',ROOT).pathname)||url.pathname.startsWith(new URL('assets/maps/',ROOT).pathname)||url.pathname.startsWith(new URL('assets/thumbs/',ROOT).pathname)||url.pathname.startsWith(new URL('assets/traces/',ROOT).pathname);
  event.respondWith((async()=>{
    const cache=await caches.open(mapPath?ASSETS:SHELL),cached=await cache.match(request);
    if(mapPath&&cached)return cached;
    // App code is refreshed online; an installed carnet must not keep stale JS.
    try {
      const response=await fetch(request,{cache:mapPath?'default':'no-cache'});
      if(response.ok&&response.type==='basic')await cache.put(request,response.clone());
      return !response.ok&&cached ? cached : response;
    } catch(error) {
      if(cached)return cached;
      throw error;
    }
  })());
});
