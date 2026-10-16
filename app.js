import {ROUTES,SOURCE_DATE,CATALOGUE_ALIASES} from './data.js?v=normandie-20261016-r3';
import {APP_ID,STORAGE_KEY,CACHE_NAME,emptyState,filterRoutes,validateState,validateTrip,mergeBackup,stats,timerElapsed,pauseTimer,resumeTimer,localDate,routeElevation,routeMapsUrl} from './core.js?v=normandie-20261016-r3';

const $=s=>document.querySelector(s);
const icon=name=>`<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>new Intl.NumberFormat('fr-FR',{maximumFractionDigits:1}).format(n);
const routeById=id=>ROUTES.find(r=>r.id===Number(id));
const asset=p=>new URL(p,document.baseURI).href;
const external=(href,label,cls='text-button')=>`<a href="${esc(href)}" class="${cls}" target="_blank" rel="noopener noreferrer">${label}</a>`;
const dateLabel=date=>new Intl.DateTimeFormat('fr-FR',{day:'numeric',month:'short',year:'numeric'}).format(new Date(`${date}T12:00:00`));
const timeLabel=ms=>{const sec=Math.floor(ms/1000);return [Math.floor(sec/3600),Math.floor(sec/60)%60,sec%60].map(n=>String(n).padStart(2,'0')).join(':');};

let state=emptyState(),view='explorer',currentRoute=null,zoom=100,pendingImport=null,installPrompt=null,finishingTimer=false;
let previousRaw=null,storageBlocked=false;
let filters={search:'',band:'all',sort:'featured',onlyFavorites:false,onlyDone:false,department:'all',ascent:'all'};
let toastTimeout,visibleLimit=24,catalogueData=null,downloadCancel=false;

function warning(message) {$('#storage-warning').textContent=message;$('#storage-warning').hidden=false;}
try {
  previousRaw=localStorage.getItem(STORAGE_KEY);
  if(previousRaw) state=validateState(JSON.parse(previousRaw),ROUTES,{aliases:CATALOGUE_ALIASES});
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
    const clean=validateState(next,ROUTES,{aliases:CATALOGUE_ALIASES});
    localStorage.setItem(STORAGE_KEY,JSON.stringify(clean));
    state=clean;
    return true;
  } catch(error) {
    warning('Enregistrement impossible dans ce navigateur. Tes données précédentes sont conservées. Vérifie l’espace disponible et les réglages de confidentialité.');
    toast('La modification n’a pas pu être enregistrée.');return false;
  }
}

function renderCards(reset=true) {
  if(reset)visibleLimit=24;
  const routes=filterRoutes(ROUTES,filters,state);
  $('#result-count').textContent=`${routes.length} circuit${routes.length>1?'s':''}`;
  $('#route-grid').innerHTML=routes.slice(0,visibleLimit).map(r=>{
    const favorite=state.favorites.includes(r.id),done=state.trips.some(t=>t.routeId===r.id);
    const elevation=routeElevation(r);
    const relief=`<div class="card-metrics"><span>D+ ${elevationLabel(elevation.ascent,elevation.estimated)}</span><span>D− ${elevationLabel(elevation.descent,elevation.estimated)}</span>${r.durationMinutes?`<span>${durationLabel(r.durationMinutes)}</span>`:''}${r.difficulty?`<span>${esc(r.difficulty)}</span>`:''}</div><p class="card-elevation-source">${elevation.estimated?`Dénivelés estimés · ${r.elevation?.provider==='GPX officiel'?'GPX':'IGN'}`:elevation.ascent===null?'Dénivelés non renseignés':elevation.descent!==null?'Dénivelés annoncés par la fiche':'D+ annoncé par la fiche'}</p>`;
    return `<article class="route-card"><button class="favorite-button icon-button" data-action="favorite" data-id="${r.id}" aria-pressed="${favorite}" aria-label="${favorite?'Retirer des favoris':'Ajouter aux favoris'} : ${esc(r.name)}">${icon('heart')}</button><button class="card-open" data-action="open" data-id="${r.id}" aria-label="Ouvrir ${esc(r.name)}, ${fmt(r.km)} kilomètres"><div class="card-map${r.basemap?' has-basemap':''}"><img src="./${r.thumb}" loading="lazy" decoding="async" alt="${r.basemap?'Carte IGN avec le tracé du circuit ':'Aperçu de la carte du circuit '}${r.id}" width="560" height="400"><span class="distance-badge">${fmt(r.km)} km</span></div><div class="card-body"><span class="card-department">${esc(r.departmentName)}${r.isNew?' · NOUVEAU':''}</span><span class="card-town">${esc(r.town)}</span><h3>${esc(r.name)}</h3>${relief}<div class="card-bottom"><span>${done?`<span class="done-label">${icon('check')}Déjà parcouru</span>`:`Circuit ${String(r.id).padStart(2,'0')} · ${r.ambiguous?'Départ à confirmer':'Voir le parcours'}`}</span>${icon('arrow')}</div></div></button><div class="card-links">${external(routeMapsUrl(r),r.ambiguous?'Voir la commune dans Maps':'Aller au départ · Google Maps')}</div></article>`;
  }).join('');
  $('#empty-results').hidden=routes.length>0;
  $('#load-more').hidden=routes.length<=visibleLimit;
  $('#load-more').textContent=`Afficher les ${Math.min(24,routes.length-visibleLimit)} suivants (${Math.min(visibleLimit,routes.length)} sur ${routes.length})`;
  if(!routes.length && view==='favoris') {
    $('#empty-results h3').textContent=state.favorites.length?'Aucun favori avec ces filtres':'Tes envies de balade, ici';
    $('#empty-results p').textContent=state.favorites.length?'Essaie une autre distance ou efface la recherche.':'Appuie sur le cœur d’un circuit pour le retrouver facilement.';
  } else {
    $('#empty-results h3').textContent='Aucun chemin trouvé';
    $('#empty-results p').textContent='Essaie un autre lieu, une autre distance ou un autre dénivelé.';
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

let inventoryLimit=40;
const integratedStatus=status=>['integre','deja-present','doublon-geometrique','doublon-geometrique-proche'].includes(status);
const catalogueStatus={
  'integre':'Circuit intégré', 'deja-present':'Déjà dans le carnet',
  'doublon-geometrique':'Même tracé, fiche rapprochée',
  'doublon-geometrique-proche':'Tracé équivalent, fiche rapprochée',
  'sans-gpx-publie':'GPX absent de la liste officielle',
  'gpx-inexploitable':'GPX indisponible ou inexploitable',
  'distance-a-verifier':'Distance du GPX à vérifier',
  'carte-indisponible':'Fond de carte à reprendre',
  'doublon-a-reprendre':'Circuit de référence à reprendre',
  'a-construire':'Carte et profil à préparer',
  'trace-verifiee':'Trace vérifiée, intégration à préparer',
  'trace-inexploitable':'Tracé inexploitable dans la source',
  'departement-a-verifier':'Parcours interdépartemental : répartition à confirmer',
};
async function loadCoverage() {
  if(!catalogueData){
    const response=await fetch(asset('assets/catalogue.json'));
    if(!response.ok)throw Error('Inventaire indisponible');
    catalogueData=await response.json();
  }
  const linked=catalogueData.records.filter(r=>integratedStatus(r.status)&&r.routeId).length;
  $('#coverage-summary p').textContent=`${ROUTES.length} circuits dans le carnet · ${linked} références rapprochées sur ${catalogueData.collectedTotal} fiches officielles inventoriées. Couverture de toute la Normandie encore à vérifier.`;
  return catalogueData;
}
async function showCoverage() {
  $('#coverage-content').textContent='Chargement de l’inventaire…';
  $('#coverage-dialog').showModal();
  try {
    const data=await loadCoverage();
    const departments=[['14','Calvados'],['27','Eure'],['50','Manche'],['61','Orne'],['76','Seine-Maritime']];
    const rows=departments.map(([code,name])=>{
      const refs=data.records.filter(r=>r.department===code);
      const linked=refs.filter(r=>integratedStatus(r.status)&&r.routeId).length;
      return `<tr><th scope="row">${name}</th><td>${refs.length}</td><td>${linked}</td><td>${refs.length-linked}</td></tr>`;
    }).join('');
    $('#coverage-content').innerHTML=`<p class="eyebrow">INVENTAIRE DU 16 OCTOBRE 2026</p><p><strong>${ROUTES.length} circuits utilisables dans le carnet</strong>, avec leurs cartes. L’inventaire contient ${data.collectedTotal} fiches officielles, dont ${data.regionalTotal||985} références régionales. Plusieurs fiches peuvent désigner le même parcours.</p><p class="notice">Le recensement de toute la Normandie reste ouvert : les autres registres officiels, les offices locaux, les GR et leurs variantes doivent encore être croisés. Aucun pourcentage de couverture totale n’est annoncé.</p><div class="coverage-table"><table><thead><tr><th>Département</th><th>Fiches repérées</th><th>Rattachées au carnet</th><th>À reprendre</th></tr></thead><tbody>${rows}</tbody></table></div><p class="muted">Deux itinéraires interdépartementaux figurent aussi dans l’inventaire régional. Les circuits d’origine absents du catalogue régional restent conservés.</p><p>${external(data.source,'Consulter le catalogue régional officiel')}</p><details><summary>Catalogues départementaux vérifiés</summary><ul>${(data.sourceCatalogues||[]).map(s=>`<li>${external(s.source,departments.find(d=>d[0]===s.department)?.[1]||s.department)} : ${s.total} références pédestres${s.collectedAll?' recensées':' · collecte à compléter'}.${s.note?` ${esc(s.note)}`:''}</li>`).join('')}</ul></details><h3>Retrouver toutes les fiches</h3><div class="inventory-tools"><label>Nom ou commune<input id="inventory-search" type="search" placeholder="Chercher dans l’inventaire"></label><label>Département<select id="inventory-department"><option value="all">Tous</option>${departments.map(([code,name])=>`<option value="${code}">${name}</option>`).join('')}<option value="multi">Plusieurs départements</option></select></label><label>État<select id="inventory-status"><option value="all">Toutes les fiches</option><option value="pending">À reprendre</option><option value="linked">Rattachées au carnet</option></select></label></div><p id="inventory-count" role="status"></p><div id="inventory-list"></div><button id="inventory-more" class="button button-light" data-action="inventory-more">Afficher la suite</button><p class="muted">Les doublons de géométrie sont rapprochés même si le sens, le premier point ou l’échantillonnage change. La comparaison des traces rééchantillonnées se fait dans les deux sens tous les 4 m, avec un écart observé maximal de 2 m et des longueurs compatibles à 1 %. Les noms, communes et distances sont également comparés. Des variantes proches peuvent encore nécessiter une vérification humaine.</p>`;
    inventoryLimit=40;renderInventory();
    for(const id of ['inventory-search','inventory-department','inventory-status'])$('#'+id).addEventListener(id==='inventory-search'?'input':'change',()=>{inventoryLimit=40;renderInventory();});
  } catch {
    $('#coverage-content').textContent='L’inventaire n’est pas disponible ici. Ouvre le carnet en ligne pour le récupérer.';
  }
}
function renderInventory() {
  if(!catalogueData||!$('#inventory-list'))return;
  const query=$('#inventory-search').value.normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase();
  const department=$('#inventory-department').value,status=$('#inventory-status').value;
  const records=catalogueData.records.filter(r=>{
    if(department!=='all'&&(r.department||'multi')!==department)return false;
    if(status==='pending'&&integratedStatus(r.status)&&r.routeId)return false;
    if(status==='linked'&&(!integratedStatus(r.status)||!r.routeId))return false;
    return `${r.name} ${r.town} ${r.sourceId}`.normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase().includes(query);
  });
  $('#inventory-count').textContent=`${records.length} fiche${records.length>1?'s':''} · ${Math.min(inventoryLimit,records.length)} affichée${records.length>1?'s':''}`;
  $('#inventory-list').innerHTML=records.slice(0,inventoryLimit).map(r=>`<article class="inventory-entry"><h4>${esc(r.name)}</h4><p>${esc(r.town)}${r.km?' · '+fmt(r.km)+' km':''}</p><p class="inventory-state">${esc(catalogueStatus[r.status]||'Données à compléter')}</p>${r.historicalNameMatch?`<p class="muted">Nom rapproché du circuit ${esc(r.historicalNameMatch.routeId)}, sans identité de parcours confirmée. ${esc(r.historicalNameMatch.reason||'')}</p>`:''}${r.historicalSourceMatch?.geometryComparison==='differente'?`<p class="muted">La source correspond au circuit historique ${esc(r.historicalSourceMatch.routeId)}, mais les tracés diffèrent : les deux parcours sont conservés. ${esc(r.historicalSourceMatch.reason||'')}</p>`:''}${r.status==='distance-a-verifier'?`<p class="muted">Fiche : ${fmt(r.km)} km · GPX : ${fmt(r.geometryKm)} km. Variante à confirmer.</p>`:''}<div class="source-links">${r.routeId&&routeById(r.routeId)?`<button class="text-button" data-action="open" data-id="${r.routeId}">Ouvrir le circuit</button>`:''}${external(r.official,'Fiche officielle')}${r.sourceTraceUrl?external(r.sourceTraceUrl,'Tracé GeoJSON publié'):r.gpxSource?external(r.sourceDownloadReferer||r.gpxSource,r.sourceDownloadReferer?'GPX sur la fiche officielle':'GPX publié'):''}</div></article>`).join('')||'<p>Aucune fiche avec ces filtres.</p>';
  $('#inventory-more').hidden=records.length<=inventoryLimit;
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
  renderCards(false);
  const detail=$('#route-content [data-action="favorite"]');
  if(detail && Number(detail.dataset.id)===id){detail.setAttribute('aria-pressed',String(!was));detail.setAttribute('aria-label',!was?'Retirer des favoris':'Ajouter aux favoris');}
  toast(was?'Circuit retiré des favoris.':'Une nouvelle envie dans tes favoris.');
}

const routeAssets=r=>[...new Set([r.map,r.thumb,r.trace,r.gpx,r.elevationTrace,r.elevation?.profile].filter(Boolean))];
const durationLabel=minutes=>`${Math.floor(minutes/60)} h${minutes%60?' '+String(minutes%60).padStart(2,'0'):''}`;
const elevationLabel=(metres,estimated)=>metres===null?'—':`${estimated?'≈ ':''}${fmt(metres)} m`;
function elevationSection(r) {
  if(!r.elevation)return '<p class="elevation-note">D+ : total des montées · D− : total des descentes. Les valeurs absentes restent non renseignées.</p>';
  return `<section class="elevation-profile" aria-labelledby="elevation-heading"><h2 id="elevation-heading">Le relief du parcours</h2><p class="elevation-note">D+ : total des montées · D− : total des descentes.</p><div class="elevation-meta"><span>Altitude basse ≈ ${fmt(r.elevation.min)} m</span><span>Altitude haute ≈ ${fmt(r.elevation.max)} m</span></div><div id="elevation-chart" role="status">Chargement du profil…</div><p class="elevation-note">Dénivelés et profil estimés à partir ${r.elevation.provider==='GPX officiel'?'des altitudes du GPX officiel':'du relief IGN'}, arrondis à 5 m pour les montées et descentes.${r.elevationGain!=null?` La fiche de l’organisme annonce ${fmt(r.elevationGain)} m de dénivelé.`:''} ${r.elevationTrace?'Le profil suit le GPX actuel de l’office ; la carte du dossier est datée de 2022.':''}</p></section>`;
}
async function loadElevationProfile(r) {
  if(!r.elevation)return;
  try {
    const response=await fetch(asset(r.elevation.profile));if(!response.ok)throw Error('Profil indisponible');
    const data=await response.json();
    if(currentRoute?.id!==r.id)return;
    const segments=data.segments;
    if(data.routeId!==r.id||!Array.isArray(segments)||!segments.length)throw Error('Profil invalide');
    const points=segments.flat();
    if(points.length<2||!points.every(p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)))throw Error('Altitudes invalides');
    const length=points.at(-1)[0];if(length<=0)throw Error('Distance invalide');
    const low=Math.floor(Math.min(...points.map(p=>p[1]))/10)*10;
    const high=Math.max(low+20,Math.ceil(Math.max(...points.map(p=>p[1]))/10)*10);
    const x=d=>64+d/length*558,y=z=>202-(z-low)/(high-low)*178;
    const line=segment=>segment.map((p,i)=>`${i?'L':'M'}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ');
    const paths=segments.map(segment=>`<path class="profile-area" d="${line(segment)} L${x(segment.at(-1)[0]).toFixed(1)},202 L${x(segment[0][0]).toFixed(1)},202 Z"/><path class="profile-line" d="${line(segment)}"/>`).join('');
    const grid=[low,(low+high)/2,high].map(z=>`<line class="profile-grid" x1="64" x2="622" y1="${y(z)}" y2="${y(z)}"/><text x="54" y="${y(z)+7}" text-anchor="end">${fmt(z)}</text>`).join('');
    const ticks=[0,length/2,length].map((d,i)=>`<text x="${x(d)}" y="236" text-anchor="${i===0?'start':i===2?'end':'middle'}">${fmt(d/1000)} km</text>`).join('');
    const chart=$('#elevation-chart');if(!chart)return;
    chart.removeAttribute('role');
    chart.innerHTML=`<svg class="profile-svg" viewBox="0 0 640 254" role="img" aria-label="Profil du parcours : altitude en mètres selon la distance sur le tracé, de ${fmt(length/1000)} kilomètres."><title>Altitude (m) selon la distance du tracé</title>${grid}${paths}${ticks}<text x="10" y="18">m</text></svg>`;
  } catch {
    if(currentRoute?.id===r.id&&$('#elevation-chart'))$('#elevation-chart').textContent='Profil indisponible ici. Télécharge la carte et le profil avant de partir sans réseau.';
  }
}
function openRoute(id) {
  const r=routeById(id);if(!r)return;
  currentRoute=r;
  const metric=(value,label)=>`<div><strong>${esc(value)}</strong><span>${label}</span></div>`;
  const elevation=routeElevation(r);
  const extra=`${r.durationMinutes?metric(durationLabel(r.durationMinutes),'Durée indicative'):''}${r.difficulty?metric(r.difficulty,'Niveau de la fiche'):''}${metric(elevationLabel(elevation.ascent,elevation.estimated),'Dénivelé positif · D+')}${metric(elevationLabel(elevation.descent,elevation.estimated),'Dénivelé négatif · D−')}${!r.isNew?metric(r.marking,'Balisage du tableau'):''}`;
  const mapLabel=r.basemap?'Agrandir la carte IGN':r.trace?'Explorer le tracé interactif':r.isNew?'Ouvrir la fiche officielle':'Agrandir la carte';
  $('#route-content').innerHTML=`<p class="eyebrow">${esc(r.departmentName)} · CIRCUIT ${String(r.id).padStart(2,'0')}</p><h1 id="route-title">${esc(r.name)}</h1><p class="route-locality">${esc(r.town)} · ${esc(r.area||r.departmentName)}</p><div class="detail-metrics">${metric(fmt(r.km)+' km',r.distanceEstimated?'Distance calculée sur le tracé officiel':r.isNew?'Distance officielle':'Distance du dossier')}${extra}</div>${r.description?`<p class="detail-description">${esc(r.description)}</p>`:''}<div class="detail-actions"><button class="button" data-action="new-trip" data-id="${r.id}">${icon('plus')}Enregistrer une sortie</button>${external(r.official,'Fiche officielle','button button-light')}<button class="button button-light favorite-detail" data-action="favorite" data-id="${r.id}" aria-pressed="${state.favorites.includes(r.id)}" aria-label="${state.favorites.includes(r.id)?'Retirer des favoris':'Ajouter aux favoris'}">${icon('heart')}</button></div><section class="start-block"><h2>${icon('pin')}Le départ</h2><p>${esc(r.start)}<br><strong>${esc(r.town)}</strong></p>${r.ambiguous?'<p class="notice">'+esc(r.note)+'</p>':''}${external(routeMapsUrl(r),r.ambiguous?'Voir la commune dans Google Maps':'Aller au départ avec Google Maps','button button-light maps-departure')}<small class="muted">${r.ambiguous?'Départ à confirmer : Maps montre seulement la commune.':['gpx','trace'].includes(r.departurePrecision)?'Itinéraire en voiture vers le premier point du tracé officiel ; vérifie les possibilités de stationnement.':'Itinéraire en voiture vers le lieu indiqué ; vérifie le point proposé par Maps.'}</small>${r.isNew&&r.marking?`<p class="marking-note">Balisage : ${esc(r.marking)}</p>`:''}</section>${r.note&&!r.ambiguous?`<p class="notice">${esc(r.note)}</p>`:''}${r.fieldNote?`<p class="notice">${esc(r.fieldNote)}</p>`:''}${elevationSection(r)}<button class="map-preview" data-action="map" data-id="${r.id}" aria-label="${mapLabel} : ${esc(r.name)}"><img src="./${r.map}" alt="${r.basemap?'Carte IGN avec le tracé officiel':r.trace?'Aperçu du tracé GPX, sans fond topographique':r.isNew?'Fiche du circuit':'Carte du circuit '+r.id}" width="1600" height="1120"><span>${mapLabel} ${icon('plus')}</span></button><p class="map-caption">${r.basemap?'Fond © IGN – Plan IGN · Licence Ouverte 2.0 · 16 octobre 2026. Tracé officiel en rouge ; point vert : premier point du tracé.':r.isNew?(r.trace?'Aperçu du GPX officiel · tracé sans fond topographique. Le fond de la carte interactive demande Internet.':'Consulter le plan dans la fiche officielle. Aucun tracé local disponible.'):`Plan GTM du ${SOURCE_DATE} · page ${r.sourcePage} du document d’origine.`}</p>${r.isNew||r.elevationTrace?`<div class="source-links">${r.basemap?`<button class="text-button" data-action="interactive-map" data-id="${r.id}">Explorer la carte interactive</button>`:''}${r.pdf?external(r.pdf,'Plan et descriptif PDF'):(r.sourcePdfs||[]).map(p=>external(p.url,p.label||'PDF officiel')).join('')}${r.gpx||r.elevationTrace?`<a class="text-button" href="./${esc(r.gpx||r.elevationTrace)}" download data-action="download-gpx" data-id="${r.id}">${r.originalFormat==='GeoJSON'?'Télécharger l’export GPX':r.catalogue?'Télécharger le GPX du carnet':'Télécharger le GPX'}</a>`:''}${r.catalogue?external(r.sourceDownloadReferer||r.gpxSource,r.originalFormat==='GeoJSON'?'Tracé original · GeoJSON':r.sourceDownloadReferer?'Obtenir le GPX sur la fiche officielle':'GPX original de l’organisme'):''}${r.originalFormat==='GeoJSON'?'<p class="map-caption">Ce GPX est un export du carnet depuis le GeoJSON officiel ; aucun GPX original n’est publié par cette source.</p>':''}${r.erratum?external(r.erratum,'Lire l’erratum officiel'):''}</div><p class="map-caption">Sources consultées le ${r.catalogue?'16':r.isNew?'15':'16'} octobre 2026. Durées et niveaux indiqués par l’organisme ; conditions à vérifier avant le départ.</p>`:''}<div class="cache-row"><button class="button button-light" data-action="download-route" data-id="${r.id}">${icon('download')}${r.elevation?'Garder la carte et le profil hors ligne':r.basemap?'Garder la carte IGN et le tracé hors ligne':r.isNew?'Garder la fiche et le tracé hors ligne':'Garder cette carte hors ligne'}</button><span id="route-cache-status" class="cache-indicator"></span></div><section class="timer-block"><h2>Mode balade</h2><p>Un chrono pour ta sortie. Tu peux fermer le carnet et le retrouver ensuite.</p><output id="route-timer" class="stopwatch">00:00:00</output><div id="timer-actions" class="timer-actions"></div><p class="timer-footnote">La durée est calculée avec l’horloge du téléphone. Aucun parcours GPS n’est enregistré.</p></section>`;
  if(!$('#route-dialog').open)$('#route-dialog').showModal();
  $('#route-dialog').scrollTop=0;
  updateTimerUI();checkRouteCache(r);loadElevationProfile(r);
}

async function checkRouteCache(r) {
  const span=$('#route-cache-status');if(!span)return;
  const cached=(await Promise.all(routeAssets(r).map(isCached))).every(Boolean);
  if(currentRoute?.id===r.id)span.textContent=cached?(r.elevation?'Carte, profil du relief et tracé disponibles hors ligne sur cet appareil.':r.basemap?'Carte IGN et tracé disponibles hors ligne sur cet appareil.':r.isNew?'Fiche et tracé conservés. Fond de carte en ligne uniquement.':'Carte disponible hors ligne sur cet appareil.'):'Pas encore téléchargé pour le hors-ligne.';
}
let interactiveMap=null,mapRequest=0;
async function openMap(id,useInteractive=false) {
  const r=routeById(id);if(!r)return;
  const request=++mapRequest;
  if(interactiveMap){interactiveMap.remove();interactiveMap=null;}
  $('#map-title').textContent=r.name;
  const interactive=Boolean(r.trace&&window.L&&(useInteractive||!r.basemap));
  $('#map-stage').hidden=interactive;$('#interactive-map').hidden=!interactive;
  $('#image-zoom-toolbar').hidden=interactive;$('#trace-toolbar').hidden=!interactive;
  $('#map-footnote').textContent=r.basemap?'Fond © IGN – Plan IGN · Licence Ouverte 2.0 · 16/10/2026. Tracé officiel ; point vert : premier point du tracé. Aucun suivi de position.':r.isNew?'Tracé GPX officiel · fond OpenStreetMap en ligne uniquement · aucun suivi de ta position.':`Carte du dossier GTM · ${SOURCE_DATE} · Aucun positionnement GPS sur cette carte.`;
  if(!$('#map-dialog').open)$('#map-dialog').showModal();
  if(!interactive){$('#map-image').src=asset(r.map);$('#map-image').alt=`Carte du circuit ${r.id} : ${r.name}`;setZoom(100,true);return;}
  $('#trace-status').textContent='Chargement du tracé…';
  try {
    const response=await fetch(asset(r.trace));if(!response.ok)throw Error('Tracé indisponible');
    const geo=await response.json();if(request!==mapRequest||!$('#map-dialog').open)return;
    const L=window.L;
    const map=interactiveMap=L.map('interactive-map',{scrollWheelZoom:true});
    if(r.basemap)L.imageOverlay(asset(r.map),r.mapBounds,{pane:'tilePane',zIndex:0,alt:'Carte IGN du circuit',attribution:'Fond local © IGN – Plan IGN · Licence Ouverte 2.0'}).addTo(map);
    const line=L.geoJSON(geo,{style:{color:'#c75632',weight:5,opacity:1}}).addTo(map);
    const bounds=line.getBounds();map.fitBounds(bounds,{padding:[34,34],maxZoom:15});
    const coordinate=geo.geometry.type==='MultiLineString'?geo.geometry.coordinates[0][0]:geo.geometry.coordinates[0];
    L.circleMarker([coordinate[1],coordinate[0]],{radius:8,color:'#fff',weight:3,fillColor:'#173f38',fillOpacity:1}).addTo(map).bindTooltip(r.originalFormat==='GeoJSON'?'Premier point du tracé officiel':'Premier point du GPX officiel');
    map.routeBounds=bounds;
    L.control.scale({imperial:false}).addTo(map);
    const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,zIndex:1,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'});
    tiles.on('tileerror',()=>{$('#trace-status').textContent=r.basemap?'Fond en ligne indisponible : la carte IGN reste affichée autour du circuit.':'Fond indisponible. Le tracé reste consultable sans fond topographique.';});
    $('#trace-status').textContent=navigator.onLine?'Déplace la carte et zoome pour explorer.':r.basemap?'Hors ligne : carte IGN et tracé disponibles autour du circuit.':'Hors ligne : tracé seul, sans fond topographique.';
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
    pendingImport=validateState(JSON.parse(await file.text()),ROUTES,{backup:true,aliases:CATALOGUE_ALIASES});
    $('#info-title').textContent='Importer ma sauvegarde';
    const merged=mergeBackup(state,pendingImport),added=merged.trips.length-state.trips.length;
    $('#info-content').innerHTML=`<h3>Une sauvegarde reconnue</h3><p>Ce fichier contient ${pendingImport.trips.length} sortie(s) et ${pendingImport.favorites.length} favori(s).</p><p><strong>${added} nouvelle(s) sortie(s)</strong> seront ajoutées. Tes sorties actuelles seront conservées ; les doublons portant le même identifiant seront ignorés.</p><button class="button" data-action="confirm-import">Ajouter à mon carnet</button>`;
    $('#info-dialog').showModal();
  }catch(error){pendingImport=null;toast(`Import refusé : ${error instanceof SyntaxError?'le fichier JSON est illisible.':error.message}`);}
});

function showSources() {
  $('#info-title').textContent='Le carnet et ses sources';
  $('#info-content').innerHTML=`<p>Un carnet personnel pour Pierre : <strong>${ROUTES.length} circuits dans les cinq départements de Normandie</strong>, avec un catalogue officiel suivi par département.</p><h3>Les nouvelles randonnées</h3><p>Les circuits ont été ajoutés depuis les sites des offices de tourisme, organismes départementaux et portails publics de randonnée. Sources consultées le 15 octobre 2026. Chaque fiche donne ses liens officiels, le descriptif PDF lorsqu’il est proposé et le GPX disponible.</p><p>Les circuits supplémentaires affichent une vraie carte : fond © IGN – Plan IGN, sous Licence Ouverte 2.0, avec le GPX officiel en rouge. Les images sont géoréférencées, intégrées au carnet et téléchargeables hors ligne. Elles ont été préparées le 16 octobre 2026. Le point vert est le premier point du GPX, pas nécessairement le parking décrit. La carte interactive garde ce fond local autour du circuit et charge OpenStreetMap en ligne pour explorer plus loin. Les PDF cartographiques restent accessibles sur les sites de leurs éditeurs.</p><h3>Montées et descentes</h3><p>${ROUTES.filter(r=>r.elevation).length} circuits disposent de D+, D− et d’un profil estimés à partir du relief IGN ou des altitudes du GPX officiel, consultés le 16 octobre 2026. Ces estimations sont arrondies à 5 m. Les chiffres annoncés par les organismes restent indiqués dans les fiches. Les valeurs absentes ne sont pas remplacées par zéro. Le filtre de montée trie selon les dénivelés connus, sans prétendre donner un niveau de difficulté.</p><h3>Les 28 cartes d’origine</h3><p>Les cartes autour de Granville viennent du <strong>Plan Balisage GTM du 10 février 2022</strong>, document de travail du Comité Départemental de la Randonnée Pédestre de la Manche. Le document liste 30 circuits mais fournit 28 cartes : les n° 3 et 11 sont absents. Les anciennes fiches et leurs identifiants sont conservés.</p><ul><li>N° 9 : départ différent entre tableau et fiche (casino / nouvel office).</li><li>N° 13 et 14 : mairie dans le tableau, église sur la fiche.</li><li>N° 25 : sigles de départ différents (CSNRG / CNSRG).</li><li>N° 27 : carte à 12 km ; tableau et office à 12,5 km, valeur retenue.</li></ul><p>Ces départs restent signalés. Les informations absentes des sources ne sont pas inventées. Le bouton « Couverture par département » donne l’inventaire régional, les doublons et les fichiers à reprendre ; il ne garantit pas que tous les itinéraires normands sont présents. Vérifie les accès, la météo, les marées sur le littoral et les déviations locales avant chaque sortie.</p><h3>Tes données</h3><p>Favoris, chrono et sorties restent dans ce navigateur. Aucun compte ni synchronisation de tes notes. Exporte régulièrement une sauvegarde JSON ; les sauvegardes de l’ancienne version restent compatibles.</p><h3>Sans réseau</h3><p>Le téléchargement conserve les cartes d’origine, les cartes IGN avec leur fond et les traces GPX. La carte agrandissable reste lisible sans réseau. Le fond OpenStreetMap au-delà des environs du circuit, les PDF externes et les liens de départ demandent Internet. Aucune tuile OpenStreetMap n’est téléchargée par le bouton hors ligne. Le navigateur peut libérer le stockage : vérifie la disponibilité avant de partir. Aucun suivi GPS ni guidage en direct.</p><h3>Installer le carnet</h3><p>Utilise le bouton d’installation s’il apparaît, ou le menu du navigateur puis « Ajouter à l’écran d’accueil ».</p><p>${external('https://github.com/piscotpierre-tech/mon-carnet-rando/blob/main/SOURCES.md','Toutes les sources, circuit par circuit')}</p>`;
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
async function downloadGpx(id,link) {
  const r=routeById(id),path=r?.gpx||r?.elevationTrace;
  if(!path||link?.dataset.downloading)return;
  if(link){link.dataset.downloading='true';link.setAttribute('aria-busy','true');}
  try {
    const url=asset(path);
    let cache,response;
    if('caches' in window&&isSecureContext) {
      try {cache=await caches.open(CACHE_NAME);response=await cache.match(url);}catch {}
    }
    if(!response) {
      response=await fetch(url);
      if(!response.ok)throw new Error('GPX indisponible. Télécharge la carte et le tracé avant de partir sans réseau.');
      if(cache)try {await cache.put(url,response.clone());}catch {}
    }
    const bytes=await response.arrayBuffer();
    if(!bytes.byteLength)throw new Error('Le fichier GPX est vide. Reconnecte-toi pour le récupérer.');
    // Native downloads may bypass the service worker. Download a local Blob
    // built from cached bytes instead of navigating to the GPX asset URL.
    const objectUrl=URL.createObjectURL(new Blob([bytes],{type:'application/gpx+xml'}));
    const anchor=document.createElement('a');
    anchor.href=objectUrl;anchor.download=new URL(url).pathname.split('/').at(-1);
    document.body.append(anchor);anchor.click();anchor.remove();
    setTimeout(()=>URL.revokeObjectURL(objectUrl),30000);
  } catch(error) {
    toast(error.message||'GPX indisponible ici. Télécharge la carte et le tracé avant de partir sans réseau.');
  } finally {
    if(link){delete link.dataset.downloading;link.removeAttribute('aria-busy');}
  }
}
async function downloadRoute(id,button) {
  if(!('caches' in window) || !isSecureContext){toast('Le hors-ligne demande une application ouverte en HTTPS.');return;}
  const r=routeById(id);if(!r)return;
  if(button)button.disabled=true;
  try {
    const cache=await caches.open(CACHE_NAME);
    for(const path of routeAssets(r))await cacheAsset(cache,path);
    toast(r.elevation?'Carte, profil du relief et tracé téléchargés sur cet appareil.':r.basemap?'Carte IGN et tracé téléchargés sur cet appareil.':r.isNew?'Fiche et tracé conservés sur cet appareil.':'Carte téléchargée sur cet appareil.');checkRouteCache(r);refreshOfflineStatus();
  }catch(error){toast(error.message||'Téléchargement impossible.');}
  finally{if(button)button.disabled=false;}
}
async function refreshOfflineStatus() {
  if(!('caches' in window) || !isSecureContext){$('#offline-status').textContent='Le téléchargement hors ligne sera disponible après publication en HTTPS.';return;}
  try {const cache=await caches.open(CACHE_NAME);const responses=await Promise.all(ROUTES.map(async r=>(await Promise.all(routeAssets(r).map(p=>cache.match(asset(p))))).every(Boolean)));const n=responses.filter(Boolean).length;$('#offline-status').textContent=`${n} carte${n>1?'s':''} sur ${ROUTES.length} disponible${n>1?'s':''} hors ligne sur cet appareil.`;}catch{$('#offline-status').textContent='Le navigateur ne donne pas accès aux cartes enregistrées.';}
}
async function downloadAll() {
  if(!('caches' in window) || !isSecureContext){toast('Le hors-ligne demande une application ouverte en HTTPS.');return;}
  const button=$('#download-all');button.disabled=true;downloadCancel=false;$('#cancel-download').hidden=false;$('#cancel-download').disabled=false;$('#cancel-download').textContent='Arrêter le téléchargement';let n=0;
  const department=$('#download-department').value;
  const selected=ROUTES.filter(r=>department==='all'||r.department===department);
  try {
    const cache=await caches.open(CACHE_NAME);
    for(const r of selected){if(downloadCancel)break;for(const path of routeAssets(r))await cacheAsset(cache,path);button.textContent=`Cartes téléchargées : ${++n} / ${selected.length}`;}
    toast(downloadCancel?`Téléchargement arrêté : ${n} cartes conservées.`:`Les ${selected.length} cartes, leurs tracés et les profils disponibles sont conservés sur cet appareil.`);
  }catch(error){toast(`Téléchargement arrêté après ${n} cartes. Les cartes déjà conservées restent disponibles.`);}
  finally{button.disabled=false;$('#cancel-download').hidden=true;button.innerHTML=`${icon('download')}Garder les cartes hors ligne`;refreshOfflineStatus();}
}

document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-action]');if(!b)return;
  const id=Number(b.dataset.id);
  switch(b.dataset.action){
    case 'open':openRoute(id);break;
    case 'load-more':visibleLimit+=24;renderCards(false);break;
    case 'coverage':await showCoverage();break;
    case 'close-coverage':$('#coverage-dialog').close();break;
    case 'inventory-more':inventoryLimit+=40;renderInventory();break;
    case 'inventory-filter':renderInventory();break;
    case 'favorite':toggleFavorite(id);break;
    case 'sources':showSources();break;
    case 'close-route':$('#route-dialog').close();break;
    case 'map':openMap(id);break;
    case 'interactive-map':openMap(id,true);break;
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
    case 'reset-filters':filters={...filters,search:'',band:'all',sort:'featured',onlyDone:false,department:'all',ascent:'all'};$('#department').value='all';$('#ascent').value='all';$('#search').value='';$('#sort').value='featured';renderCards();break;
    case 'timer-start':startTimer(id);break;
    case 'timer-pause':if(state.timer && persist({...state,timer:pauseTimer(state.timer)}))updateTimerUI();break;
    case 'timer-resume':if(state.timer && persist({...state,timer:resumeTimer(state.timer)}))updateTimerUI();break;
    case 'timer-finish':if(state.timer && persist({...state,timer:pauseTimer(state.timer)})){updateTimerUI();showTrip({routeId:state.timer.routeId,fromTimer:true});}break;
    case 'active-timer':if(state.timer)openRoute(state.timer.routeId);break;
    case 'export':exportData();break;
    case 'import':$('#import-file').click();break;
    case 'confirm-import':if(pendingImport && persist(mergeBackup(state,pendingImport))){pendingImport=null;$('#info-dialog').close();renderJournal();renderCards();toast('La sauvegarde a été ajoutée au carnet.');}break;
    case 'download-gpx':e.preventDefault();await downloadGpx(id,b);break;
    case 'download-route':await downloadRoute(id,b);break;
    case 'download-all':await downloadAll();break;
    case 'cancel-download':downloadCancel=true;b.disabled=true;b.textContent='Arrêt après la carte en cours…';break;
    case 'install':if(installPrompt){await installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;$('#install-button').hidden=true;}break;
  }
});
$('#search').addEventListener('input',e=>{filters.search=e.target.value;renderCards();});
$('#department').addEventListener('change',e=>{filters.department=e.target.value;renderCards();});
$('#sort').addEventListener('change',e=>{filters.sort=e.target.value;renderCards();});
$('#ascent').addEventListener('change',e=>{filters.ascent=e.target.value;renderCards();});
document.querySelectorAll('[data-band]').forEach(b=>b.addEventListener('click',()=>{filters.band=b.dataset.band;renderCards();}));
$('#done-filter').addEventListener('click',()=>{filters.onlyDone=!filters.onlyDone;renderCards();});
window.addEventListener('hashchange',setView);
function onlineUI(){$('#offline-banner').hidden=navigator.onLine;}
window.addEventListener('online',onlineUI);window.addEventListener('offline',onlineUI);
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;$('#install-button').hidden=false;});
window.addEventListener('appinstalled',()=>{$('#install-button').hidden=true;installPrompt=null;});
window.addEventListener('storage',e=>{if(e.key!==STORAGE_KEY)return;try{state=e.newValue?validateState(JSON.parse(e.newValue),ROUTES,{aliases:CATALOGUE_ALIASES}):emptyState();renderCards();renderJournal();updateTimerUI();}catch{warning('Une autre fenêtre a enregistré des données illisibles. Ferme-la puis recharge le carnet.');}});
for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('click',e=>{if(e.target!==dialog)return;const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();});
if('serviceWorker' in navigator && isSecureContext){navigator.serviceWorker.register('./sw.js?v=normandie-20261016-r3',{updateViaCache:'none'}).catch(()=>toast('Le mode hors ligne n’a pas pu être activé. Le carnet reste utilisable en ligne.'));}
setInterval(updateTimerUI,1000);
$('#total-routes').textContent=ROUTES.length;
$('#distance-range').textContent=`${fmt(Math.min(...ROUTES.map(r=>r.km)))} à ${fmt(Math.max(...ROUTES.map(r=>r.km)))}`;
onlineUI();setView();
loadCoverage().catch(()=>{$('#coverage-summary p').textContent='Le suivi de couverture sera disponible lors de la prochaine connexion.';});
