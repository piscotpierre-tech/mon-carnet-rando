import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {APP_ID,emptyState,validateState,mergeBackup,timerElapsed} from '../core.js';
import {ROUTES,CATALOGUE_ALIASES,ORIGINAL_ROUTES} from '../data.js';

// These four IDs were candidates in 5f55f1d. Repaired regional GPXs make
// different IDs canonical in the next catalogue, without changing the walk.
const aliases={2323:1622,2298:1610,2282:1620,2302:1611};
const routes=[19,1622,1610,1620,1611].map(id=>({id}));
const makeState=()=>({version:1,favorites:[19,2323,2298,2282,2302,1622],
  trips:Object.keys(aliases).map((id,index)=>({id:'saved-'+id,routeId:Number(id),date:'2026-10-16',
    distance:8.5+index,minutes:100+index,rating:4,note:'Souvenir du parcours '+id})),
  timer:{routeId:2323,elapsedMs:5600,startedAt:Date.now()-10000}});

test('les quatre anciens IDs du catalogue conservent favoris, sorties et chrono',()=>{
  const saved=makeState(),before=structuredClone(saved);
  const migrated=validateState(saved,routes,{aliases});
  assert.deepEqual(migrated.favorites,[19,1622,1610,1620,1611]);
  for(const trip of saved.trips)assert.deepEqual(migrated.trips.find(t=>t.id===trip.id),{...trip,routeId:aliases[trip.routeId]});
  assert.deepEqual(migrated.timer,{...saved.timer,routeId:1622});
  const now=Date.now();assert.equal(timerElapsed(migrated.timer,now),timerElapsed(saved.timer,now));
  assert.deepEqual(saved,before,'La lecture ne modifie pas la sauvegarde fournie');
});

test('une ancienne sauvegarde importée migre les circuits et garde le chrono local',()=>{
  const saved=makeState();
  const local=validateState({...emptyState(),timer:saved.timer},routes,{aliases});
  const imported=validateState({...saved,app:APP_ID},routes,{backup:true,aliases});
  assert.equal(imported.timer,null);
  const merged=mergeBackup(local,imported);
  assert.equal(merged.trips.length,4);
  assert.deepEqual(merged.timer,local.timer);
  const exported=JSON.parse(JSON.stringify({...merged,app:APP_ID}));
  const roundtrip=validateState(exported,routes,{backup:true,aliases});
  assert.deepEqual(roundtrip.trips,merged.trips);
  assert.deepEqual(roundtrip.favorites,merged.favorites);
});

test('les alias ne rendent pas valides les données malformées ou circuits inconnus',()=>{
  const saved=makeState();
  for(const update of [{favorites:[999999]},{favorites:['2323']},
    {trips:[{...saved.trips[0],routeId:'2323'}]},
    {trips:[{...saved.trips[0],note:null}]},
    {trips:[{...saved.trips[0],date:'2026-02-30'}]},
    {timer:{...saved.timer,elapsedMs:-1}},
    {timer:{...saved.timer,routeId:999999}}])assert.throws(()=>validateState({...saved,...update},routes,{aliases}));
  assert.throws(()=>validateState(saved,routes,{aliases:{2323:999999}}));
  assert.equal(validateState({...emptyState(),favorites:[19]},routes,{aliases:{19:1622}}).favorites[0],19);
});

test('les alias publiés ciblent des circuits disponibles sans remplacer les 48 historiques',()=>{
  const available=new Set(ROUTES.map(r=>r.id)),originals=new Set(ORIGINAL_ROUTES.map(r=>r.id));
  for(const [source,target] of Object.entries(CATALOGUE_ALIASES)){
    assert(Number.isSafeInteger(Number(source))&&Number(source)>=1001);
    assert(!originals.has(Number(source)));
    assert(!available.has(Number(source)));
    assert(available.has(target));
  }
});

const report=JSON.parse(readFileSync(new URL('../assets/catalogue.json',import.meta.url),'utf8'));
test('le catalogue complet conserve les quatre anciens IDs ou leurs alias vers une cible publiée',
  {skip:report.integratedNew<=5},()=>{
    const available=new Set(ROUTES.map(r=>r.id));
    for(const id of [2323,2298,2282,2302])assert(available.has(id)||available.has(CATALOGUE_ALIASES[id]),
      `Le circuit ${id} a disparu sans alias vers un circuit publié ; les sauvegardes deviendraient illisibles.`);
  });
