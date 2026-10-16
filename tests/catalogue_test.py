import importlib
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'scripts'))
prepare=importlib.import_module('prepare-catalogue')
build=importlib.import_module('build-catalogue')
comparison=importlib.import_module('trace-comparison')
elevations=importlib.import_module('build-elevations')


class CatalogueTests(unittest.TestCase):
    def test_closed_geometry_duplicates_ignore_start_and_direction(self):
        a=[[0,49],[.01,49],[.01,49.01],[0,49.01],[0,49]]
        b=a[2:-1]+a[:3]
        self.assertEqual(build.canonical([a]),build.canonical([b]))
        self.assertEqual(build.canonical([a]),build.canonical([a[::-1]]))

    def test_different_loops_and_segment_gaps_are_not_merged(self):
        a=[[[0,49],[.01,49],[.01,49.01]]]
        b=[[[0,49],[.01,49]],[[.01,49],[.01,49.01]]]
        self.assertNotEqual(build.canonical(a),build.canonical(b))

    def test_parse_retains_disjoint_segments_and_absent_altitudes(self):
        raw=b'<gpx><trk><trkseg>'+b''.join(f'<trkpt lon="0.{i}" lat="49"/>'.encode() for i in range(4))+b'</trkseg><trkseg>'+b''.join(f'<trkpt lon="0.{i}" lat="49.1"><ele>50</ele></trkpt>'.encode() for i in range(4))+b'</trkseg></trk></gpx>'
        segments=prepare.parse(raw)
        self.assertEqual(len(segments),2)
        self.assertEqual(len(segments[0][0]),2)
        self.assertEqual(segments[1][0][2],50)

    def test_outside_france_and_empty_tracks_are_rejected(self):
        for raw in [b'<gpx/>',b'<gpx><trk><trkseg><trkpt lon="0" lat="0"/></trkseg></trk></gpx>']:
            with self.assertRaises((AssertionError,ValueError)):
                prepare.parse(raw)

    def test_blank_altitudes_do_not_discard_a_valid_track(self):
        raw=b'<gpx><rte>'+b''.join(f'<rtept lon="0.{i}" lat="49"><ele> </ele></rtept>'.encode() for i in range(6))+b'</rte></gpx>'
        segment=prepare.parse(raw)[0]
        self.assertEqual(len(segment),6)
        self.assertTrue(all(len(p)==2 for p in segment))

    def test_same_path_with_different_sampling_is_merged(self):
        a=[[[0,49],[.01,49],[.01,49.01]]]
        b=[[[0,49],[.005,49],[.01,49],[.01,49.005],[.01,49.01]]]
        self.assertTrue(comparison.equivalent(comparison.describe(a),comparison.describe(b)))

    def test_nearby_alternative_and_shortcuts_stay_distinct(self):
        a=[[[0,49],[.01,49],[.01,49.01]]]
        for b in [[[[0,49.0001],[.01,49.0001],[.01,49.0101]]],[[[0,49],[.01,49.01]]]]:
            self.assertFalse(comparison.equivalent(comparison.describe(a),comparison.describe(b)))

    def test_nominal_historical_match_does_not_discard_a_different_trace(self):
        original={'id':40,'name':'Cap de Carteret','town':'Carteret','km':9.8}
        record={'name':'Cap de Carteret','town':'Carteret','km':10,
                'segments':[[[0,49],[.01,49],[.01,49.01]]]}
        names={(prepare.normal(original['name']),prepare.normal(original['town'])):original}
        shape=comparison.describe([[[0,49.0001],[.01,49.0001],[.01,49.0101]]])
        existing,hints=build.historical_match(record,{},names,{40:shape})
        self.assertIsNone(existing)
        self.assertEqual(hints['historicalNameMatch']['routeId'],40)
        self.assertEqual(hints['historicalNameMatch']['status'],'a-verifier')

    def test_nominal_historical_match_without_geometry_remains_unconfirmed(self):
        original={'id':1,'name':'Les quatre chemins','town':'Commune','km':4}
        record={'name':'Les quatre chemins','town':'Commune','km':3.8,
                'segments':[[[0,49],[.01,49],[.01,49.01]]]}
        names={(prepare.normal(original['name']),prepare.normal(original['town'])):original}
        existing,hints=build.historical_match(record,{},names,{})
        self.assertIsNone(existing)
        self.assertEqual(hints['historicalNameMatch']['status'],'a-verifier')

    def test_same_gpx_url_with_changed_geometry_is_retained_and_documented(self):
        original={'id':40,'name':'Un parcours','town':'Commune','km':10}
        record={'name':'Autre libellé','town':'Commune','km':10,'gpxSource':'https://example.org/current.gpx',
                'segments':[[[0,49],[.01,49],[.01,49.01]]]}
        original_shape=comparison.describe([[[0,49.0001],[.01,49.0001],[.01,49.0101]]])
        existing,hints=build.historical_match(record,{record['gpxSource']:original},{},{40:original_shape})
        self.assertIsNone(existing)
        self.assertEqual(hints['historicalSourceMatch']['geometryComparison'],'differente')
        existing,hints=build.historical_match(record,{record['gpxSource']:original},{},
                                             {40:comparison.describe(record['segments'])})
        self.assertEqual(existing['id'],40)
        self.assertEqual(hints['historicalSourceMatch']['geometryComparison'],'equivalente')

    def test_cached_missing_relief_retries_without_rebuilding_its_map(self):
        record={'sourceId':'retry-test','segments':[[[.001*i,49] for i in range(6)]],
                'route':{'id':1001,'sourceId':'retry-test','name':'Parcours test','gpxSource':'https://example.org/test.gpx',
                         'gpx':'assets/traces/1001.gpx','trace':'assets/traces/1001.geojson','tracePointCount':6}}
        signature=build.rendering_version()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for folder in ['records','assets/traces','assets/profiles']:(root/folder).mkdir(parents=True)
            attempts=[]
            summary={'ascent':10,'descent':15,'profile':'assets/profiles/1001.json'}
            def elevation(route):
                attempts.append(route.get('elevationMethod'))
                if len(attempts)==1:raise TimeoutError('Temporary IGN failure')
                (root/summary['profile']).write_text(json.dumps({'summary':summary}))
            with patch.object(build,'GENERATED',root),patch.object(build,'rendering_version',return_value=signature),\
                 patch.object(build,'build_map') as map_builder,patch.object(build.elevations,'build',side_effect=elevation):
                first=build.build(copy.deepcopy(record))
                self.assertIn('elevationIssue',first)
                second=build.build(copy.deepcopy(record))
                self.assertEqual(len(attempts),2)
                self.assertEqual(map_builder.call_count,1)
                self.assertEqual(second['route']['elevation'],summary)
                self.assertNotIn('elevationIssue',second)
                self.assertNotIn('elevationIssue',second['route'])
                saved=json.loads((root/'records/1001.json').read_text())
                self.assertEqual(saved,second)

    def test_cached_relief_retry_requires_both_local_trace_files(self):
        route={'id':1001,'trace':'assets/traces/1001.geojson','gpx':'assets/traces/1001.gpx'}
        cached={'route':route,'elevationIssue':'Previous failure'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'assets/traces').mkdir(parents=True)
            (root/route['trace']).write_text('{}')
            with patch.object(build,'GENERATED',root),patch.object(build.elevations,'build') as elevation:
                result=build.retry_cached_elevation(cached,{},root/'unused.json')
                elevation.assert_not_called()
                self.assertEqual(result,cached)
                self.assertFalse((root/'unused.json').exists())

    def test_cached_relief_uses_gpx_fallback_only_for_complete_plausible_altitudes(self):
        for heights,expected_attempts in [([10,11,12,13,14,15],2),
                                          ([10,11,None,13,14,15],1),
                                          ([10,11,1501,13,14,15],1)]:
            with self.subTest(heights=heights),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                for folder in ['records','assets/traces','assets/profiles']:(root/folder).mkdir(parents=True)
                route={'id':1001,'trace':'assets/traces/1001.geojson','gpx':'assets/traces/1001.gpx',
                       'tracePointCount':6,'elevationIssue':'Previous failure'}
                for field in ['trace','gpx']:(root/route[field]).write_text('source exists')
                cached={'route':route,'elevationIssue':'Previous failure'}
                segments=[[[.001*i,49]+([z] if z is not None else []) for i,z in enumerate(heights)]]
                methods=[]
                def elevation(r):
                    methods.append(r.get('elevationMethod'))
                    if r.get('elevationMethod')!='gpx':raise TimeoutError('IGN unavailable')
                    (root/'assets/profiles/1001.json').write_text(json.dumps({'summary':{'ascent':5,'descent':0}}))
                with patch.object(build,'GENERATED',root),patch.object(build.elevations,'build',side_effect=elevation):
                    result=build.retry_cached_elevation(cached,{'segments':segments},root/'records/1001.json')
                self.assertEqual(len(methods),expected_attempts)
                if expected_attempts==2:
                    self.assertEqual(methods,[None,'gpx'])
                    self.assertNotIn('elevationIssue',result)
                else:
                    self.assertIn('elevationIssue',result)
                    self.assertNotIn('elevationMethod',result['route'])

    def test_relief_rounding_uses_the_same_precision_as_its_provenance(self):
        for raw,expected in [(87.49999999999997,90),(87.50000000000003,90),(87.499,85),(87.501,90),(0,0)]:
            self.assertEqual(elevations.rounded_relief(raw),expected)

    def test_deduplicated_sources_export_aliases_for_the_four_previously_integrable_ids(self):
        ids=json.loads((Path(__file__).resolve().parent.parent/'catalogue/route-ids.json').read_text())
        mappings=[('ORNE-GEOTREK-32647',2323,1622),('ORNE-GEOTREK-29',2298,1610),
                  ('ORNE-GEOTREK-16',2282,1620),('ORNE-GEOTREK-32',2302,1611)]
        for source,reserved,_ in mappings:self.assertEqual(ids[source],reserved)
        report=[{'sourceId':source,'routeId':target} for source,_,target in mappings]
        routes=[{'id':target} for _,_,target in mappings]
        self.assertEqual(build.catalogue_aliases(report,ids,[{'id':19}],routes),
                         {reserved:target for _,reserved,target in mappings})
        self.assertEqual(build.catalogue_aliases(report,ids,[{'id':19}],[]),{})
        with self.assertRaises(ValueError):
            build.catalogue_aliases([{'sourceId':'protected','routeId':1622}],{'protected':19},[{'id':19}],routes)


if __name__=='__main__':unittest.main()
