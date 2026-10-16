import importlib
from pathlib import Path
import sys
import unittest

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

    def test_relief_rounding_uses_the_same_precision_as_its_provenance(self):
        for raw,expected in [(87.49999999999997,90),(87.50000000000003,90),(87.499,85),(87.501,90),(0,0)]:
            self.assertEqual(elevations.rounded_relief(raw),expected)


if __name__=='__main__':unittest.main()
