import {ROUTES,SOURCE_DATE} from './data.js';
import {APP_ID,STORAGE_KEY,CACHE_NAME,emptyState,filterRoutes,validateState,validateTrip,mergeBackup,stats,timerElapsed,pauseTimer,resumeTimer,localDate} from './core.js';

const $=s=>document.querySelector(s);
const icon=name=>`<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>new Intl.NumberFormat('fr-FR',{maximumFractionDigits:1}).format(n);
const routeById=id=>ROUTES.find(r=>r.id===Number(id));
const asset=p=>new URL(p,document.baseURI).href;
const external=(href,label,cls='text-button')=>`<a href="${esc(href)}" class="${cls}" target="_blank" rel="noopener noreferrer">${label}</a>`;
const mapSearch=r=>'https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(`${r.start} ${r.town} ${r.departmentName}`);
const dateLabel=date=>new Intl.DateTimeFormat('fr-FR',{day:'numeric',month:'short',year:'numeric'}).format(new Date(`${date}T12:00:00`));
const timeLabel=ms=>{const sec=Math.floor(ms/1000);return [Math.floor(sec/3600),Math.floor(sec/60)%60,sec%60].map(n=>String(n).padStart(2,'0')).join(':');};

let state=emptyState(),view='explorer',currentRoute=null,zoom=100,pendingImport=null,installPrompt=null,finishingTimer=false;
let previousRaw=null,storageBlocked=false;
let filters={search:'',band:'all',sort:'featured',onlyFavorites:false,onlyDone:false,department:'all'};
let toastTimeout;

function warning(message) {$('#storage-warning').textContent=message;$('#storage-warning').hidden=false;}
try {
  previousRaw=localStorage.getItem(STORAGE_KEY);
  if(previousRaw) state=validateState(JSON.parse(previousRaw),ROUTES);
} catch(error) {
  // Keep unreadable data intact before permitting any new write.
  if(previousRaw){
    try {localStorage.setItem(`${STORAGE_KEY}:recovery`,previousRaw);warning('Les anciennes données sont illisibles. Une copie de récupération est conservée dans ce navigateur. Utilise une sauvegarde JSON pour restaurer ton carnet.');}
    catch {storageBlocked=true;warning('Les anciennes données sont illisibles et ne peuvent pas être mises à l’abri. L’enregistrement est suspendu pour ne pas les écraser.');}
  } else warning('Le stockage du navigateur n’est pas accessible. Les favoris et sorties ne pourront pas être enregistrés.');
}

function toast(message) {
  clearTimeout(toastTimeout);$('#toast').textContent=message;$('#toast').hidden=false;
  toastTimeout=setTimeout(()=>{$('#toast').hidden=true;},4200);
}
function persist(next) {
  if(storageBlocked){toast('Enregistrement suspendu pour préserver tes anciennes données.');return false;}
  try {
    const clean=validateState(next,ROUTES);
    localStorage.setItem(STORAGE_KEY,JSON.stringify(clean));
    state=clean;
    return true;
  } catch(error) {
    warning('Enregistrement impossible dans ce navigateur. Tes données précédentes sont conservées. Vérifie l’espace disponible et les réglages de confidentialité.');
    toast('La modification n’a pas pu être enregistrée.');return false;
  }
}

function renderCards() {
  const routes=filterRoutes(ROUTES,filters,state);
  $('#result-count').textContent=`${routes.length} circuit${routes.length>1?'s':''}`;
  $('#route-grid').innerHTML=routes.map(r=>{
    const favorite=state.favorites.includes(r.id),done=state.trips.some(t=>t.routeId===r.id);
    return `<article class="route-card"><button class="favorite-button icon-button" data-action="favorite" data-id="${r.id}" aria-pressed="${favorite}" aria-label="${favorite?'Retirer des favoris':'Ajouter aux favoris'} : ${esc(r.name)}">${icon('heart')}</button><button class="card-open" data-action="open" data-id="${r.id}" aria-label="Ouvrir ${esc(r.name)}, ${fmt(r.km)} kilomètres"><div class="card-map"><img src="./${r.thumb}" loading="lazy" decoding="async" alt="Aperçu de la carte du circuit ${r.id}" width="560" height="400"><span class="distance-badge">${fmt(r.km)} km</span></div><div class="card-body"><span class="card-department">${esc(r.departmentName)}${r.isNew?' · NOUVEAU':''}</span><span class="card-town">${esc(r.town)}</span><h3>${esc(r.name)}</h3><div class="card-bottom"><span>${done?`<span class="done-label">${icon('check')}Déjà parcouru</span>`:`Circuit ${String(r.id).padStart(2,'0')} · ${r.ambiguous?'Départ à confirmer':'Voir le parcours'}`}</span>${icon('arrow')}</div></div></button></article>`;
  }).join('');
  $('#empty-results').hidden=routes.length>0;
  if(!routes.length && view==='favoris') {
    $('#empty-results h3').textContent=state.favorites.length?'Aucun favori avec ces filtres':'Tes envies de balade, ici';
    $('#empty-results p').textContent=state.favorites.length?'Essaie une autre distance ou efface la recherche.':'Appuie sur le cœur d’un circuit pour le retrouver facilement.';
  } else {
    $('#empty-results h3').textContent='Aucun chemin trouvé';
    $('#empty-results p').textContent='Essaie un autre lieu ou une autre distance.';
  }
  document.querySelectorAll('[data-band]').forEach(b=>{const active=b.dataset.band===filters.band;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  $('#done-filter').classList.toggle('active',filters.onlyDone);$('#done-filter').setAttribute('aria-pressed',String(filters.onlyDone));
}

function renderJournal() {
  const s=stats(state);
  $('#stats').innerHTML=`<div class="stat"><strong>${fmt(s.km)}</strong><span>kilomètres parcourus</span></div><div class="stat"><strong>${s.outings}</strong><span>sortie${s.outings>1?'s':''} enregistrée${s.outings>1?'s':''}</span></div><div class="stat"><strong>${s.completed}<small> / ${ROUTES.length}</small></strong><span>circuits découverts</span></div>`;
  $('#progress-label').textContent=`${s.completed} circuit${s.completed>1?'s':''} découvert${s.completed>1?'s':''} sur ${ROUTES.length}`;
  $('#route-progress').max=ROUTES.length;$('#route-progress').value=s.completed;$('#trip-count').textContent=`${s.outings} sortie${s.outings>1?'s':''}`;
  const trips=[...state.trips].sort((a,b)=>b.date.localeCompare(a.date));
  $('#trip-list').innerHTML=trips.length?trips.map(t=>{
    const r=routeById(t.routeId);
    return `<article class="trip-entry"><time class="trip-date" datetime="${esc(t.date)}">${esc(dateLabel(t.date))}</time><div class="trip-details"><h3>${esc(r.name)}</h3><div class="trip-metrics"><span>${fmt(t.distance)} km parcourus</span><span>${t.minutes?`${Math.floor(t.minutes/60)} h ${String(t.minutes%60).padStart(2,'0')}`:'Durée non renseignée'}</span>${t.rating?`<span>${t.rating} / 5 · plaisir de la sortie</span>`:''}</div>${t.note?`<p class="trip-note">${esc(t.note)}</p>`:''}<div class="entry-actions"><button class="text-button" data-action="edit-trip" data-trip="${esc(t.id)}">Modifier</button><button class="text-button" data-action="delete-trip" data-trip="${esc(t.id)}">Supprimer</button></div></div></article>`;
  }).join(''):`<div class="empty-state">${icon('book')}<h3>Le premier souvenir t’attend</h3><p>Après ta balade, enregistre les kilomètres réels et ce qui t’a plu.</p><button class="button" data-action="new-trip">Ajouter ma première sortie</button></div>`;
  refreshOfflineStatus();
}

function setView() {
  view=['explorer','favoris','carnet'].includes(location.hash.slice(1))?location.hash.slice(1):'explorer';
  document.body.classList.toggle('favorites-page',view==='favoris');
  $('#explorer-view').hidden=view==='carnet';$('#carnet-view').hidden=view!=='carnet';
  filters.onlyFavorites=view==='favoris';
  $('#explorer-title').textContent=view==='favoris'?'Mes envies de grand air':'Où est-ce qu’on va ?';
  document.querySelectorAll('[data-nav]').forEach(a=>{if(a.dataset.nav===view)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  if(view==='carnet')renderJournal();else renderCards();
  updateTimerUI();
}

function toggleFavorite(id) {
  if(!routeById(id))return;
  const was=state.favorites.includes(id);
  if(!persist({...state,favorites:was?state.favorites.filter(n=>n!==id):[...state.favorites,id]}))return;
  renderCards();
  const detail=$('#route-content [data-action="favorite"]');
  if(detail && Number(detail.dataset.id)===id){detail.setAttribute('aria-pressed',String(!was));detail.setAttribute('aria-label',!was?'Retirer des favoris':'Ajouter aux favoris');}
  toast(was?'Circuit retiré des favoris.':'Une nouvelle envie dans tes favoris.');
}

const routeAssets=r=>[r.map,r.thumb,...(r.trace?[r.trace,r.gpx]:[])];
const durationLabel=minutes=>`${Math.floor(minutes/60)} h${minutes%60?' '+String(minutes%60).padStart(2,'0'):''}`;
function openRoute(id) {
  const r=routeById(id);if(!r)return;
  currentRoute=r;
  const metric=(value,label)=>`<div><strong>${esc(value)}</strong><span>${label}</span></div>`;
  const extra=r.isNew?`${r.durationMinutes?metric(durationLabel(r.durationMinutes),'Durée indicative'):''}${r.difficulty?metric(r.difficulty,'Niveau de la fiche'):''}${r.elevationGain!=null?metric('+'+r.elevationGain+' m','Dénivelé annoncé'):''}`:metric(r.marking,'Balisage du tableau');
  const mapLabel=r.trace?'Explorer le tracé interactif':r.isNew?'Ouvrir la fiche officielle':'Agrandir la carte';
  $('#route-content').innerHTML=`<p class="eyebrow">${esc(r.departmentName)} · CIRCUIT ${String(r.id).padStart(2,'0')}</p><h1 id="route-title">${esc(r.name)}</h1><p class="route-locality">${esc(r.town)} · ${esc(r.area||r.departmentName)}</p><div class="detail-metrics">${metric(fmt(r.km)+' km',r.isNew?'Distance officielle':'Distance du dossier')}${extra}</div>${r.description?`<p class="detail-description">${esc(r.description)}</p>`:''}<div class="detail-actions"><button class="button" data-action="new-trip" data-id="${r.id}">${icon('plus')}Enregistrer une sortie</button>${external(r.official,'Fiche officielle','button button-light')}<button class="button button-light favorite-detail" data-action="favorite" data-id="${r.id}" aria-pressed="${state.favorites.includes(r.id)}" aria-label="${state.favorites.includes(r.id)?'Retirer des favoris':'Ajouter aux favoris'}">${icon('heart')}</button></div><section class="start-block"><h2>${icon('pin')}Le départ</h2><p>${esc(r.start)}<br><strong>${esc(r.town)}</strong></p>${r.ambiguous?'<p class="notice">'+esc(r.note)+'</p>':external(mapSearch(r),'Rechercher ce lieu dans Google Maps')}${!r.ambiguous?'<small class="muted">Recherche du lieu de départ ; vérifier le stationnement sur place.</small>':''}${r.isNew&&r.marking?`<p class="marking-note">Balisage : ${esc(r.marking)}</p>`:''}</section>${r.note&&!r.ambiguous?`<p class="notice">${esc(r.note)}</p>`:''}${r.fieldNote?`<p class="notice">${esc(r.fieldNote)}</p>`:''}<button class="map-preview" data-action="map" data-id="${r.id}" aria-label="${mapLabel} : ${esc(r.name)}"><img src="./${r.map}" alt="${r.trace?'Aperçu du tracé GPX, sans fond topographique':r.isNew?'Fiche du circuit':'Carte du circuit '+r.id}" width="1600" height="1120"><span>${mapLabel} ${icon('plus')}</span></button><p class="map-caption">${r.isNew?(r.trace?'Aperçu du GPX officiel · tracé sans fond topographique. Le fond de la carte interactive demande Internet.':'Consulter le plan dans la fiche officielle. Aucun tracé local disponible.'):`Plan GTM du ${SOURCE_DATE} · page ${r.sourcePage} du document d’origine.`}</p>${r.isNew?`<div class="source-links">${r.pdf?external(r.pdf,'Plan et descriptif PDF'):''}${r.gpx?`<a class="text-button" href="./${esc(r.gpx)}" download>Télécharger le GPX</a>`:''}${r.erratum?external(r.erratum,'Lire l’erratum officiel'):''}</div><p class="map-caption">Sources consultées le 15 octobre 2026. Durées et niveaux indiqués par l’organisme ; conditions à vérifier avant le départ.</p>`:''}<div class="cache-row"><button class="button button-light" data-action="download-route" data-id="${r.id}">${icon('download')}${r.isNew?'Garder la fiche et le tracé hors ligne':'Garder cette carte hors ligne'}</button><span id="route-cache-status" class="cache-indicator"></span></div><section class="timer-block"><h2>Mode balade</h2><p>Un chrono pour ta sortie. Tu peux fermer le carnet et le retrouver ensuite.</p><output id="route-timer" class="stopwatch">00:00:00</output><div id="timer-actions" class="timer-actions"></div><p class="timer-footnote">La durée est calculée avec l’horloge du téléphone. Aucun parcours GPS n’est enregistré.</p></section>`;
  if(!$('#route-dialog').open)$('#route-dialog').showModal();
  $('#route-dialog').scrollTop=0;
  updateTimerUI();checkRouteCache(r);
}

async function checkRouteCache(r) {
  const span=$('#route-cache-status');if(!span)return;
  const cached=(await Promise.all(routeAssets(r).map(isCached))).every(Boolean);
  if(currentRoute?.id===r.id)span.textContent=cached?(r.isNew?'Fiche et tracé conservés. Fond de carte en ligne uniquement.':'Carte disponible hors ligne sur cet appareil.'):'Pas encore téléchargé pour le hors-ligne.';
}
let interactiveMap=null,mapRequest=0;
async function openMap(id) {
  const r=routeById(id);if(!r)return;
  const request=++mapRequest;
  if(interactiveMap){interactiveMap.remove();interactiveMap=null;}
  $('#map-title').textContent=r.name;
  const interactive=Boolean(r.trace&&window.L);
  $('#map-stage').hidden=interactive;$('#interactive-map').hidden=!interactive;
  $('#image-zoom-toolbar').hidden=interactive;$('#trace-toolbar').hidden=!interactive;
  $('#map-footnote').textContent=r.isNew?'Tracé GPX officiel · fond OpenStreetMap en ligne uniquement · aucun suivi de ta position.':`Carte du dossier GTM · ${SOURCE_DATE} · Aucun positionnement GPS sur cette carte.`;
  if(!$('#map-dialog').open)$('#map-dialog').showModal();
  if(!interactive){$('#map-image').src=asset(r.map);$('#map-image').alt=`Carte du circuit ${r.id} : ${r.name}`;setZoom(100,true);return;}
  $('#trace-status').textContent='Chargement du tracé…';
  try {
    const response=await fetch(asset(r.trace));if(!response.ok)throw Error('Tracé indisponible');
    const geo=await response.json();if(request!==mapRequest||!$('#map-dialog').open)return;
    const L=window.L;
    const map=interactiveMap=L.map('interactive-map',{scrollWheelZoom:true});
    const line=L.geoJSON(geo,{style:{color:'#c75632',weight:5,opacity:1}}).addTo(map);
    const bounds=line.getBounds();map.fitBounds(bounds,{padding:[34,34],maxZoom:15});
    const coordinate=geo.geometry.type==='MultiLineString'?geo.geometry.coordinates[0][0]:geo.geometry.coordinates[0];
    L.circleMarker([coordinate[1],coordinate[0]],{radius:8,color:'#fff',weight:3,fillColor:'#173f38',fillOpacity:1}).addTo(map).bindTooltip('Premier point du GPX officiel');
    map.routeBounds=bounds;
    L.control.scale({imperial:false}).addTo(map);
    const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'});
    tiles.on('tileerror',()=>{$('#trace-status').textContent='Fond indisponible. Le tracé reste consultable sans fond topographique.';});
    $('#trace-status').textContent=navigator.onLine?'Déplace la carte et zoome pour explorer.':'Hors ligne : tracé seul, sans fond topographique.';
    if(navigator.onLine)tiles.addTo(map);
    map.invalidateSize();
  }catch{if(request===mapRequest){$('#trace-status').textContent='Tracé indisponible. Télécharge-le avant de partir, ou consulte la fiche officielle.';}}
}
$('#map-dialog').addEventListener('close',()=>{mapRequest++;if(interactiveMap){interactiveMap.remove();interactiveMap=null;}});
function setZoom(value,reset=false) {
  const stage=$('#map-stage'),img=$('#map-image');
  const cx=(stage.scrollLeft+stage.clientWidth/2)/(img.clientWidth||stage.clientWidth||1);
  const cy=(stage.scrollTop+stage.clientHeight/2)/(img.clientHeight||stage.clientHeight||1);
  zoom=Math.min(350,Math.max(100,value));img.style.width=`${zoom}%`;$('#zoom-label').textContent=`${zoom} %`;
  if(reset){stage.scrollLeft=0;stage.scrollTop=0;}else{stage.scrollLeft=cx*img.clientWidth-stage.clientWidth/2;stage.scrollTop=cy*img.clientHeight-stage.clientHeight/2;}
}
let drag=null;
$('#map-stage').addEventListener('pointerdown',e=>{if($('#map-stage').hidden||e.pointerType!=='mouse'||e.button!==0)return;const s=e.currentTarget;drag={x:e.clientX,y:e.clientY,left:s.scrollLeft,top:s.scrollTop};s.setPointerCapture(e.pointerId);s.classList.add('dragging');e.preventDefault();});
$('#map-stage').addEventListener('pointermove',e=>{if(!drag)return;const s=e.currentTarget;s.scrollLeft=drag.left+drag.x-e.clientX;s.scrollTop=drag.top+drag.y-e.clientY;});
for(const event of ['pointerup','pointercancel','lostpointercapture'])$('#map-stage').addEventListener(event,()=>{drag=null;$('#map-stage').classList.remove('dragging');});
document.addEventListener('error',e=>{
  if(!(e.target instanceof HTMLImageElement))return;
  if(e.target.id==='map-image'||e.target.closest('.map-preview'))toast('Cette carte n’est pas disponible. Connecte-toi puis télécharge-la avant de repartir hors ligne.');
},true);

function showTrip({routeId=null,trip=null,fromTimer=false}={}) {
  finishingTimer=fromTimer;
  $('#trip-form').reset();$('#trip-error').hidden=true;
  $('#trip-title').textContent=trip?'Modifier ma sortie':'Raconter ma sortie';
  $('#trip-route').innerHTML=ROUTES.map(r=>`<option value="${r.id}">${esc(r.name)} · ${fmt(r.km)} km</option>`).join('');
  $('#trip-id').value=trip?.id||'';
  $('#trip-route').value=String(trip?.routeId||routeId||ROUTES[0].id);
  $('#trip-date').value=trip?.date||localDate();
  $('#trip-distance').value=trip?.distance||routeById($('#trip-route').value).km;
  $('#trip-minutes').value=trip?.minutes??(fromTimer?Math.max(1,Math.round(timerElapsed(state.timer)/60000)):0);
  $('#trip-rating').value=trip?.rating||'';$('#trip-note').value=trip?.note||'';
  $('#trip-route').disabled=fromTimer;
  if(!$('#trip-dialog').open)$('#trip-dialog').showModal();
}
$('#trip-route').addEventListener('change',()=>{if(!$('#trip-id').value)$('#trip-distance').value=routeById($('#trip-route').value).km;});
$('#trip-form').addEventListener('submit',e=>{
  e.preventDefault();
  try {
    const trip=validateTrip({id:$('#trip-id').value||crypto.randomUUID(),routeId:Number($('#trip-route').value),date:$('#trip-date').value,distance:Number($('#trip-distance').value),minutes:Number($('#trip-minutes').value),rating:$('#trip-rating').value?Number($('#trip-rating').value):null,note:$('#trip-note').value.trim()},new Set(ROUTES.map(r=>r.id)));
    const trips=state.trips.some(t=>t.id===trip.id)?state.trips.map(t=>t.id===trip.id?trip:t):[...state.trips,trip];
    if(!persist({...state,trips,timer:finishingTimer?null:state.timer}))return;
    $('#trip-dialog').close();finishingTimer=false;renderCards();renderJournal();updateTimerUI();toast('Ta sortie est enregistrée. Un souvenir de plus.');
  } catch(error) {$('#trip-error').textContent=error.message;$('#trip-error').hidden=false;}
});

function startTimer(id) {
  if(!routeById(id))return;
  if(state.timer && state.timer.routeId!==id && !confirm('Un chrono existe pour un autre circuit. Le remplacer sans enregistrer cette sortie ?'))return;
  if(state.timer?.routeId===id){if(persist({...state,timer:resumeTimer(state.timer)}))updateTimerUI();return;}
  if(persist({...state,timer:{routeId:id,elapsedMs:0,startedAt:Date.now()}})){updateTimerUI();toast('Bonne balade, Pierre !');}
}
function updateTimerUI() {
  const t=state.timer;
  $('#active-timer').hidden=!t;
  if(t){$('#active-timer-label').textContent=(t.startedAt===null?'En pause · ':'')+routeById(t.routeId).name;$('#active-timer-time').textContent=timeLabel(timerElapsed(t));}
  const output=$('#route-timer'),actions=$('#timer-actions');
  if(!output || !currentRoute)return;
  const here=t?.routeId===currentRoute.id;
  output.textContent=here?timeLabel(timerElapsed(t)):'00:00:00';
  // Keep the controls stable while the seconds tick, to preserve keyboard focus.
  const key=`${currentRoute.id}:${here}:${t?.startedAt===null}`;
  if(actions.dataset.key===key)return;
  actions.dataset.key=key;
  actions.innerHTML=here?`<button class="button" data-action="${t.startedAt===null?'timer-resume':'timer-pause'}">${t.startedAt===null?'Reprendre':'Mettre en pause'}</button><button class="button button-light" data-action="timer-finish">Terminer et enregistrer</button>`:`<button class="button" data-action="timer-start" data-id="${currentRoute.id}">${icon('clock')}Démarrer ma balade</button>`;
}

function exportData() {
  const data={app:APP_ID,version:1,exportedAt:new Date().toISOString(),favorites:state.favorites,trips:state.trips};
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download=`mon-carnet-rando-${localDate()}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Sauvegarde préparée. Conserve le fichier téléchargé.');
}
$('#import-file').addEventListener('change',async e=>{
  const file=e.target.files[0];e.target.value='';if(!file)return;
  try {
    if(file.size>2_000_000)throw new Error('Le fichier dépasse la limite de 2 Mo.');
    pendingImport=validateState(JSON.parse(await file.text()),ROUTES,{backup:true});
    $('#info-title').textContent='Importer ma sauvegarde';
    const merged=mergeBackup(state,pendingImport),added=merged.trips.length-state.trips.length;
    $('#info-content').innerHTML=`<h3>Une sauvegarde reconnue</h3><p>Ce fichier contient ${pendingImport.trips.length} sortie(s) et ${pendingImport.favorites.length} favori(s).</p><p><strong>${added} nouvelle(s) sortie(s)</strong> seront ajoutées. Tes sorties actuelles seront conservées ; les doublons portant le même identifiant seront ignorés.</p><button class="button" data-action="confirm-import">Ajouter à mon carnet</button>`;
    $('#info-dialog').showModal();
  }catch(error){pendingImport=null;toast(`Import refusé : ${error instanceof SyntaxError?'le fichier JSON est illisible.':error.message}`);}
});

function showSources() {
  $('#info-title').textContent='Le carnet et ses sources';
  $('#info-content').innerHTML=`<p>Un carnet personnel pour Pierre : <strong>${ROUTES.length} circuits dans les cinq départements de Normandie</strong>, dont 20 nouvelles suggestions.</p><h3>Les nouvelles randonnées</h3><p>Quatre circuits par département ont été ajoutés depuis les sites des offices de tourisme, organismes départementaux et portails publics de randonnée. Sources consultées le 15 octobre 2026. Chaque fiche donne ses liens officiels, le descriptif PDF lorsqu’il est proposé et le GPX disponible.</p><p>Les aperçus des nouveaux circuits sont dessinés à partir des coordonnées des GPX officiels, sans fond topographique. La carte interactive utilise Leaflet et le fond © OpenStreetMap contributors, chargé en ligne. Les PDF cartographiques restent accessibles sur les sites de leurs éditeurs.</p><h3>Les 28 cartes d’origine</h3><p>Les cartes autour de Granville viennent du <strong>Plan Balisage GTM du 10 février 2022</strong>, document de travail du Comité Départemental de la Randonnée Pédestre de la Manche. Le document liste 30 circuits mais fournit 28 cartes : les n° 3 et 11 sont absents. Les anciennes fiches et leurs identifiants sont conservés.</p><ul><li>N° 9 : départ différent entre tableau et fiche (casino / nouvel office).</li><li>N° 13 et 14 : mairie dans le tableau, église sur la fiche.</li><li>N° 25 : sigles de départ différents (CSNRG / CNSRG).</li><li>N° 27 : carte à 12 km ; tableau et office à 12,5 km, valeur retenue.</li></ul><p>Ces départs restent signalés. Les informations absentes des sources ne sont pas inventées. Vérifie les accès, la météo, les marées sur le littoral et les déviations locales avant chaque sortie.</p><h3>Tes données</h3><p>Favoris, chrono et sorties restent dans ce navigateur. Aucun compte ni synchronisation de tes notes. Exporte régulièrement une sauvegarde JSON ; les sauvegardes de l’ancienne version restent compatibles.</p><h3>Sans réseau</h3><p>Le téléchargement conserve les cartes d’origine et les nouveaux aperçus et traces GPX. Le fond OpenStreetMap, les PDF externes et les liens de départ demandent Internet. Aucune tuile du fond n’est téléchargée par le bouton hors ligne. Le navigateur peut libérer le stockage : vérifie la disponibilité avant de partir. Aucun suivi GPS ni guidage en direct.</p><h3>Installer le carnet</h3><p>Utilise le bouton d’installation s’il apparaît, ou le menu du navigateur puis « Ajouter à l’écran d’accueil ».</p><p>${external('https://github.com/piscotpierre-tech/mon-carnet-rando/blob/main/SOURCES.md','Toutes les sources, circuit par circuit')}</p>`;
  $('#info-dialog').showModal();
}

async function isCached(path) {
  if(!('caches' in window) || !isSecureContext)return false;
  try{return Boolean(await (await caches.open(CACHE_NAME)).match(asset(path)));}catch{return false;}
}
async function cacheAsset(cache,path) {
  const url=asset(path);if(await cache.match(url))return;
  const response=await fetch(url,{cache:'reload'});
  if(!response.ok)throw new Error('Carte indisponible. Vérifie ta connexion.');
  await cache.put(url,response);
}
async function downloadRoute(id,button) {
  if(!('caches' in window) || !isSecureContext){toast('Le hors-ligne demande une application ouverte en HTTPS.');return;}
  const r=routeById(id);if(!r)return;
  if(button)button.disabled=true;
  try {
    const cache=await caches.open(CACHE_NAME);
    for(const path of routeAssets(r))await cacheAsset(cache,path);
    toast(r.isNew?'Fiche et tracé conservés sur cet appareil.':'Carte téléchargée sur cet appareil.');checkRouteCache(r);refreshOfflineStatus();
  }catch(error){toast(error.message||'Téléchargement impossible.');}
  finally{if(button)button.disabled=false;}
}
async function refreshOfflineStatus() {
  if(!('caches' in window) || !isSecureContext){$('#offline-status').textContent='Le téléchargement hors ligne sera disponible après publication en HTTPS.';return;}
  try {const cache=await caches.open(CACHE_NAME);const responses=await Promise.all(ROUTES.map(async r=>(await Promise.all(routeAssets(r).map(p=>cache.match(asset(p))))).every(Boolean)));const n=responses.filter(Boolean).length;$('#offline-status').textContent=`${n} carte${n>1?'s':''} sur ${ROUTES.length} disponible${n>1?'s':''} hors ligne sur cet appareil.`;}catch{$('#offline-status').textContent='Le navigateur ne donne pas accès aux cartes enregistrées.';}
}
async function downloadAll() {
  if(!('caches' in window) || !isSecureContext){toast('Le hors-ligne demande une application ouverte en HTTPS.');return;}
  const button=$('#download-all');button.disabled=true;let n=0;
  try {
    const cache=await caches.open(CACHE_NAME);
    for(const r of ROUTES){for(const path of routeAssets(r))await cacheAsset(cache,path);button.textContent=`Cartes téléchargées : ${++n} / ${ROUTES.length}`;}
    toast(`Les ${ROUTES.length} fiches et leurs cartes ou tracés sont conservés. Fonds interactifs en ligne uniquement.`);
  }catch(error){toast(`Téléchargement arrêté après ${n} cartes. Les cartes déjà conservées restent disponibles.`);}
  finally{button.disabled=false;button.innerHTML=`${icon('download')}Garder les cartes hors ligne`;refreshOfflineStatus();}
}

document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-action]');if(!b)return;
  const id=Number(b.dataset.id);
  switch(b.dataset.action){
    case 'open':openRoute(id);break;
    case 'favorite':toggleFavorite(id);break;
    case 'sources':showSources();break;
    case 'close-route':$('#route-dialog').close();break;
    case 'map':openMap(id);break;
    case 'close-map':$('#map-dialog').close();break;
    case 'zoom-in':setZoom(zoom+50);break;
    case 'zoom-out':setZoom(zoom-50);break;
    case 'zoom-reset':setZoom(100,true);break;
    case 'trace-reset':if(interactiveMap?.routeBounds)interactiveMap.fitBounds(interactiveMap.routeBounds,{padding:[34,34]});break;
    case 'new-trip':showTrip({routeId:id||null});break;
    case 'close-trip':$('#trip-dialog').close();finishingTimer=false;break;
    case 'close-info':$('#info-dialog').close();pendingImport=null;break;
    case 'edit-trip':{const trip=state.trips.find(t=>t.id===b.dataset.trip);if(trip)showTrip({trip});break;}
    case 'delete-trip':if(confirm('Supprimer cette sortie du carnet ?')){if(persist({...state,trips:state.trips.filter(t=>t.id!==b.dataset.trip)})){renderJournal();renderCards();toast('Sortie supprimée.');}}break;
    case 'reset-filters':filters={...filters,search:'',band:'all',sort:'featured',onlyDone:false,department:'all'};$('#department').value='all';$('#search').value='';$('#sort').value='featured';renderCards();break;
    case 'timer-start':startTimer(id);break;
    case 'timer-pause':if(state.timer && persist({...state,timer:pauseTimer(state.timer)}))updateTimerUI();break;
    case 'timer-resume':if(state.timer && persist({...state,timer:resumeTimer(state.timer)}))updateTimerUI();break;
    case 'timer-finish':if(state.timer && persist({...state,timer:pauseTimer(state.timer)})){updateTimerUI();showTrip({routeId:state.timer.routeId,fromTimer:true});}break;
    case 'active-timer':if(state.timer)openRoute(state.timer.routeId);break;
    case 'export':exportData();break;
    case 'import':$('#import-file').click();break;
    case 'confirm-import':if(pendingImport && persist(mergeBackup(state,pendingImport))){pendingImport=null;$('#info-dialog').close();renderJournal();renderCards();toast('La sauvegarde a été ajoutée au carnet.');}break;
    case 'download-route':await downloadRoute(id,b);break;
    case 'download-all':await downloadAll();break;
    case 'install':if(installPrompt){await installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;$('#install-button').hidden=true;}break;
  }
});
$('#search').addEventListener('input',e=>{filters.search=e.target.value;renderCards();});
$('#department').addEventListener('change',e=>{filters.department=e.target.value;renderCards();});
$('#sort').addEventListener('change',e=>{filters.sort=e.target.value;renderCards();});
document.querySelectorAll('[data-band]').forEach(b=>b.addEventListener('click',()=>{filters.band=b.dataset.band;renderCards();}));
$('#done-filter').addEventListener('click',()=>{filters.onlyDone=!filters.onlyDone;renderCards();});
window.addEventListener('hashchange',setView);
function onlineUI(){$('#offline-banner').hidden=navigator.onLine;}
window.addEventListener('online',onlineUI);window.addEventListener('offline',onlineUI);
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;$('#install-button').hidden=false;});
window.addEventListener('appinstalled',()=>{$('#install-button').hidden=true;installPrompt=null;});
window.addEventListener('storage',e=>{if(e.key!==STORAGE_KEY)return;try{state=e.newValue?validateState(JSON.parse(e.newValue),ROUTES):emptyState();renderCards();renderJournal();updateTimerUI();}catch{warning('Une autre fenêtre a enregistré des données illisibles. Ferme-la puis recharge le carnet.');}});
for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('click',e=>{if(e.target!==dialog)return;const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();});
if('serviceWorker' in navigator && isSecureContext){navigator.serviceWorker.register('./sw.js').catch(()=>toast('Le mode hors ligne n’a pas pu être activé. Le carnet reste utilisable en ligne.'));}
setInterval(updateTimerUI,1000);
$('#total-routes').textContent=ROUTES.length;
$('#distance-range').textContent=`${fmt(Math.min(...ROUTES.map(r=>r.km)))} à ${fmt(Math.max(...ROUTES.map(r=>r.km)))}`;
onlineUI();setView();
