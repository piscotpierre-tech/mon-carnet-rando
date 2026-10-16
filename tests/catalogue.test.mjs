import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {ROUTES,ORIGINAL_ROUTES} from '../data.js';
import {emptyState,filterRoutes,routeMapsUrl} from '../core.js';

test('le catalogue conserve les circuits originaux et les identifiants des sorties',()=>{
  assert.equal(ORIGINAL_ROUTES.length,48);
  assert.equal(new Set(ROUTES.map(r=>r.id)).size,ROUTES.length);
  for(const r of ORIGINAL_ROUTES)assert.equal(ROUTES.find(x=>x.id===r.id),r);
  assert(ROUTES.filter(r=>r.catalogue).every(r=>r.id>=1001&&r.sourceId));
});
test('aucune fiche officielle ne disparaît du suivi, même sans fichier exploitable',()=>{
  const source=JSON.parse(fs.readFileSync(new URL('../catalogue/inventaire-regional.json',import.meta.url)));
  const report=JSON.parse(fs.readFileSync(new URL('../assets/catalogue.json',import.meta.url)));
  assert.equal(source.collectedTotal,source.records.length);
  assert.equal(source.records.length,report.records.length);
  assert.deepEqual(new Set(report.records.map(r=>r.sourceId)),new Set(source.records.map(r=>r.sourceId)));
  assert.equal(new Set(report.records.map(r=>r.sourceId)).size,source.records.length);
  assert.equal(report.exhaustiveNormandy,false);
  for(const r of report.records){assert(r.status);if(r.routeId)assert(ROUTES.some(x=>x.id===r.routeId));}
  assert.equal(report.usableTotal,ROUTES.length);
  assert.equal(report.integratedNew,ROUTES.filter(r=>r.catalogue).length);
});
test('les filtres partitionnent aussi le catalogue étendu sans omettre les longues étapes',()=>{
  const bands=['short','medium','long'].flatMap(band=>filterRoutes(ROUTES,{band},emptyState()));
  assert.equal(bands.length,ROUTES.length);
  assert.equal(new Set(bands.map(r=>r.id)).size,ROUTES.length);
  for(const r of ROUTES.filter(r=>r.catalogue)){
    assert(Number.isFinite(r.km)&&r.km>0);
    assert(r.trace&&r.gpx&&r.map&&r.thumb);
    assert(r.elevation||r.elevationIssue);
  }
});
test('Maps utilise latitude, longitude du premier point sans inventer un parking',()=>{
  const route={start:'Premier point du GPX',startCoordinate:[-.25,49.1],town:'Commune',departmentName:'Calvados'};
  let u=new URL(routeMapsUrl(route));assert.equal(u.searchParams.get('destination'),'49.1,-0.25');
  assert(!u.searchParams.has('origin'));
  u=new URL(routeMapsUrl({...route,ambiguous:true}));assert.equal(u.pathname,'/maps/search/');assert(!u.searchParams.get('query').includes('49.1'));
  u=new URL(routeMapsUrl({...route,startCoordinate:[NaN,49.1]}));assert(u.searchParams.get('destination').includes('Commune'));
});
