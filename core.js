export const APP_ID = 'pierre-rando';
export const STORAGE_KEY = 'pierre-rando:v1';
export const CACHE_NAME = 'pierre-rando-v1-assets';
export const normalise = value => String(value).normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim();
export const emptyState = () => ({version:1, favorites:[], trips:[], timer:null});

export function routeElevation(route) {
  const valid=n=>Number.isFinite(n)&&n>=0;
  const profile=route.elevation;
  return {
    ascent:valid(profile?.ascent)?profile.ascent:valid(route.elevationGain)?route.elevationGain:null,
    descent:valid(profile?.descent)?profile.descent:null,
    estimated:Boolean(profile?.estimated),
  };
}

export function routeMapsUrl(route) {
  // An unresolved departure must never become an apparent precise destination.
  const url=new URL(route.ambiguous?'https://www.google.com/maps/search/':'https://www.google.com/maps/dir/');
  url.searchParams.set('api','1');
  const place=[route.ambiguous?null:route.start,route.town,route.departmentName,'France'].filter(Boolean).join(', ');
  url.searchParams.set(route.ambiguous?'query':'destination',place);
  if(!route.ambiguous)url.searchParams.set('travelmode','driving');
  return url.href;
}

export function filterRoutes(routes, filters, state) {
  const q = normalise(filters.search || '');
  const result = routes.filter(r => {
    if (q && !normalise(`${r.name} ${r.town} ${r.start} ${r.departmentName} ${r.department} ${r.id}`).includes(q)) return false;
    if (filters.department && filters.department !== 'all' && r.department !== filters.department) return false;
    if (filters.band === 'short' && r.km > 6) return false;
    if (filters.band === 'medium' && (r.km <= 6 || r.km > 10)) return false;
    if (filters.band === 'long' && r.km <= 10) return false;
    if (filters.onlyFavorites && !state.favorites.includes(r.id)) return false;
    if (filters.onlyDone && !state.trips.some(t => t.routeId === r.id)) return false;
    const ascent=routeElevation(r).ascent;
    if (filters.ascent && filters.ascent !== 'all') {
      if (filters.ascent === 'unknown') {if(ascent!==null)return false;}
      else {
        if(ascent===null)return false;
        if(filters.ascent==='low'&&ascent>150)return false;
        if(filters.ascent==='medium'&&(ascent<=150||ascent>300))return false;
        if(filters.ascent==='high'&&ascent<=300)return false;
      }
    }
    return true;
  });
  const featured = [19,31,35,39,43,47,27,20,24];
  const rank = r => featured.includes(r.id) ? featured.indexOf(r.id) : 100+r.id;
  return result.sort((a,b) => {
    if(filters.sort==='ascent-asc'||filters.sort==='ascent-desc') {
      const x=routeElevation(a).ascent,y=routeElevation(b).ascent;
      if(x===null||y===null)return x===y?a.id-b.id:x===null?1:-1;
      return (filters.sort==='ascent-asc'?x-y:y-x)||a.id-b.id;
    }
    return filters.sort === 'distance-asc' ? a.km-b.km || a.id-b.id : filters.sort === 'distance-desc' ? b.km-a.km || a.id-b.id : filters.sort === 'name' ? a.name.localeCompare(b.name,'fr') : rank(a)-rank(b);
  });
}

function validDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const d = new Date(`${value}T12:00:00Z`);
  return Number.isFinite(d.getTime()) && d.toISOString().slice(0,10) === value;
}

export function validateTrip(value, routeIds) {
  if (!value || typeof value !== 'object') throw new Error('Une sortie est illisible.');
  if (typeof value.id !== 'string' || !/^[\w-]{1,100}$/.test(value.id)) throw new Error('Identifiant de sortie invalide.');
  if (!routeIds.has(value.routeId)) throw new Error('Une sortie fait référence à un circuit inconnu.');
  if (!validDate(value.date)) throw new Error('La date de la sortie est invalide.');
  if (!Number.isFinite(value.distance) || value.distance < 0.1 || value.distance > 300) throw new Error('La distance doit être comprise entre 0,1 et 300 km.');
  if (!Number.isInteger(value.minutes) || value.minutes < 0 || value.minutes > 1440) throw new Error('La durée doit être comprise entre 0 et 1 440 minutes.');
  if (value.rating !== null && (!Number.isInteger(value.rating) || value.rating < 1 || value.rating > 5)) throw new Error('La note doit être comprise entre 1 et 5.');
  if (typeof value.note !== 'string' || value.note.length > 2000) throw new Error('Le souvenir ne doit pas dépasser 2 000 caractères.');
  return {id:value.id,routeId:value.routeId,date:value.date,distance:value.distance,minutes:value.minutes,rating:value.rating,note:value.note};
}

export function validateState(value, routes, {backup=false}={}) {
  if (!value || typeof value !== 'object' || value.version !== 1) throw new Error('Ce format de sauvegarde n’est pas compatible.');
  if (backup && value.app !== APP_ID) throw new Error('Ce fichier ne vient pas de Mon carnet rando.');
  const ids = new Set(routes.map(r=>r.id));
  if (!Array.isArray(value.favorites) || !value.favorites.every(id=>ids.has(id))) throw new Error('La liste des favoris contient un circuit inconnu.');
  if (!Array.isArray(value.trips) || value.trips.length > 5000) throw new Error('La liste des sorties est invalide ou trop longue.');
  const trips = value.trips.map(t=>validateTrip(t,ids));
  if (new Set(trips.map(t=>t.id)).size !== trips.length) throw new Error('Des identifiants de sorties sont en double.');
  let timer=null;
  if (!backup && value.timer) {
    const t=value.timer;
    if (!ids.has(t.routeId) || !Number.isFinite(t.elapsedMs) || t.elapsedMs<0 || t.elapsedMs>604800000 || (t.startedAt!==null && (!Number.isFinite(t.startedAt) || t.startedAt<0 || t.startedAt>Date.now()+300000))) throw new Error('Le chronomètre enregistré est invalide.');
    timer={routeId:t.routeId,elapsedMs:t.elapsedMs,startedAt:t.startedAt};
  }
  return {version:1,favorites:[...new Set(value.favorites)],trips,timer};
}

export function mergeBackup(current, incoming) {
  // Existing entries win on an identical ID: importing never silently replaces a note.
  const entries=new Map(incoming.trips.map(t=>[t.id,t]));
  for (const t of current.trips) entries.set(t.id,t);
  return {...current,favorites:[...new Set([...current.favorites,...incoming.favorites])],trips:[...entries.values()]};
}

export function stats(state) {
  return {outings:state.trips.length,completed:new Set(state.trips.map(t=>t.routeId)).size,km:Math.round(state.trips.reduce((n,t)=>n+t.distance,0)*10)/10,minutes:state.trips.reduce((n,t)=>n+t.minutes,0)};
}

export function timerElapsed(timer,now=Date.now()) {
  if (!timer) return 0;
  return timer.elapsedMs + (timer.startedAt===null ? 0 : Math.max(0,now-timer.startedAt));
}
export function pauseTimer(timer,now=Date.now()) {return {...timer,elapsedMs:timerElapsed(timer,now),startedAt:null};}
export function resumeTimer(timer,now=Date.now()) {return timer.startedAt===null ? {...timer,startedAt:now} : timer;}
export function localDate(now=new Date()) {return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;}

