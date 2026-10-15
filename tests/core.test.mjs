import test from 'node:test';
import assert from 'node:assert/strict';
import {ROUTES} from '../data.js';
import {APP_ID,emptyState,filterRoutes,validateState,validateTrip,mergeBackup,stats,timerElapsed,pauseTimer,resumeTimer,localDate} from '../core.js';

const ids=new Set(ROUTES.map(r=>r.id));
const trip=(override={})=>({id:'sortie-1',routeId:19,date:'2026-10-15',distance:6.4,minutes:103,rating:5,note:'Belle lumière sur la baie.',...override});
const filters={search:'',band:'all',sort:'featured'};

test('48 fiches, dont les 28 d’origine, sans inventer les cartes manquantes ni masquer les départs ambigus',()=>{
  assert.equal(ROUTES.length,48);assert.equal(ids.size,48);assert.equal(ROUTES.filter(r=>!r.isNew).length,28);
  assert.equal(ids.has(3),false);assert.equal(ids.has(11),false);
  assert.deepEqual(ROUTES.filter(r=>r.ambiguous).map(r=>r.id),[9,13,14,25]);
  assert.equal(ROUTES.find(r=>r.id===27).km,12.5);
  assert.match(ROUTES.find(r=>r.id===27).note,/12 km/);
});
test('recherche insensible aux accents, casse et espace périphérique',()=>{
  const result=filterRoutes(ROUTES,{...filters,search:'  CERENCES  '},emptyState());
  assert.deepEqual(new Set(result.map(r=>r.id)),new Set([2,23,24]));
  assert.equal(filterRoutes(ROUTES,{...filters,search:'endroit-inexistant'},emptyState()).length,0);
});
test('les tranches de distance partitionnent tous les circuits, y compris les bornes 6 et 10 km',()=>{
  const short=filterRoutes(ROUTES,{...filters,band:'short'},emptyState());
  const medium=filterRoutes(ROUTES,{...filters,band:'medium'},emptyState());
  const long=filterRoutes(ROUTES,{...filters,band:'long'},emptyState());
  assert.equal(short.length+medium.length+long.length,ROUTES.length);
  assert.equal(new Set([...short,...medium,...long].map(r=>r.id)).size,ROUTES.length);
  assert(short.some(r=>r.km===6));assert(medium.some(r=>r.km===10));
  assert(!medium.some(r=>r.km===6));assert(!long.some(r=>r.km===10));
});
test('favoris et circuits déjà parcourus peuvent être combinés sans modifier les données source',()=>{
  const state={...emptyState(),favorites:[19,27],trips:[trip()]};
  assert.deepEqual(filterRoutes(ROUTES,{...filters,onlyFavorites:true,onlyDone:true},state).map(r=>r.id),[19]);
  const descending=filterRoutes(ROUTES,{...filters,sort:'distance-desc'},state);
  assert.equal(descending[0].km,20);assert.equal(ROUTES[0].id,1);
});
test('les statistiques comptent les kilomètres réels et les parcours distincts',()=>{
  assert.deepEqual(stats({...emptyState(),trips:[trip(),trip({id:'sortie-2',distance:6.2,minutes:110})]}),{outings:2,completed:1,km:12.6,minutes:213});
});
test('l’import refuse les versions étrangères, circuits inconnus, dates impossibles et données hors limites',()=>{
  const base={app:APP_ID,version:1,favorites:[19],trips:[trip()]};
  assert.equal(validateState(base,ROUTES,{backup:true}).trips[0].distance,6.4);
  for(const override of [{app:'forge'},{version:2},{favorites:[999]},{trips:[trip({routeId:999})]},{trips:[trip({date:'2026-02-30'})]},{trips:[trip({distance:NaN})]},{trips:[trip({distance:-1})]},{trips:[trip({minutes:2.5})]},{trips:[trip({rating:8})]},{trips:[trip({note:'x'.repeat(2001)})]},{trips:[trip(),trip()]}]){
    assert.throws(()=>validateState({...base,...override},ROUTES,{backup:true}));
  }
});
test('l’import ne remplace pas une sortie locale de même identifiant et ne duplique pas les favoris',()=>{
  const current={...emptyState(),favorites:[19],trips:[trip({note:'Note locale à préserver.'})],timer:{routeId:19,elapsedMs:20,startedAt:null}};
  const incoming={...emptyState(),favorites:[19,27],trips:[trip({note:'Ancienne version.'}),trip({id:'nouvelle-sortie',routeId:27})]};
  const merged=mergeBackup(current,incoming);
  assert.equal(merged.trips.length,2);assert.equal(merged.trips.find(t=>t.id==='sortie-1').note,'Note locale à préserver.');
  assert.deepEqual(merged.favorites,[19,27]);assert.deepEqual(merged.timer,current.timer);
});
test('pause, reprise et rechargement du chrono gardent une durée cohérente',()=>{
  let t={routeId:19,elapsedMs:0,startedAt:10000};
  assert.equal(timerElapsed(t,15000),5000);
  t=pauseTimer(t,15000);assert.equal(timerElapsed(t,100000),5000);
  t=resumeTimer(t,100000);assert.equal(timerElapsed(t,102500),7500);
  assert.equal(timerElapsed(JSON.parse(JSON.stringify(t)),103000),8000);
  assert.equal(timerElapsed({...t,startedAt:200000},100000),5000);
});
test('les champs inconnus sont éliminés et le chrono d’une sauvegarde ne remplace pas le chrono local',()=>{
  const clean=validateState({app:APP_ID,version:1,favorites:[19,19],trips:[trip({extra:'non'})],timer:{malformed:true},extra:'non'},ROUTES,{backup:true});
  assert.deepEqual(clean.favorites,[19]);assert.equal(clean.timer,null);assert(!('extra' in clean));assert(!('extra' in clean.trips[0]));
  assert.throws(()=>validateTrip(trip({id:'<script>'}),ids));
});
test('la date par défaut utilise les composantes locales, sans conversion UTC',()=>{
  const fake={getFullYear:()=>2026,getMonth:()=>9,getDate:()=>15};
  assert.equal(localDate(fake),'2026-10-15');
});

test('le filtre par département se combine à la recherche, aux distances et favoris',()=>{
  for(const department of ['14','27','50','61','76']) {
    const result=filterRoutes(ROUTES,{...filters,department},emptyState());
    assert.equal(result.length,department==='50'?32:4);assert(result.every(r=>r.department===department));
  }
  assert.equal(filterRoutes(ROUTES,{...filters,search:'seine-maritime'},emptyState()).length,4);
  assert.deepEqual(filterRoutes(ROUTES,{...filters,department:'14',band:'short'},emptyState()).map(r=>r.id),[33]);
  assert.deepEqual(filterRoutes(ROUTES,{...filters,department:'61',onlyFavorites:true},{...emptyState(),favorites:[19,45]}).map(r=>r.id),[45]);
});
test('les anciennes données restent identiques et les nouveaux circuits peuvent être enregistrés',()=>{
  const previous={...emptyState(),favorites:[1,19,27],trips:[trip()],timer:{routeId:19,elapsedMs:5600,startedAt:null}};
  assert.deepEqual(validateState(previous,ROUTES),previous);
  const next={...previous,favorites:[...previous.favorites,50],trips:[...previous.trips,trip({id:'nouveau',routeId:50})]};
  assert.deepEqual(validateState(next,ROUTES),next);
});
