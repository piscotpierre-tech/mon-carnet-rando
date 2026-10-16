import copy
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
collect = importlib.import_module('collect-seine-maritime')
prepare = importlib.import_module('prepare-catalogue')
build = importlib.import_module('build-catalogue')
elevations = importlib.import_module('build-elevations')
recovery = importlib.import_module('recover-short-pdesi')

# The five coordinates published for OBJECTID 13592; no resampling fixture.
POINTS = [[1.1208383192081, 49.9382263218285], [1.11902730857198, 49.9382430187864],
          [1.11779535315237, 49.938355362578], [1.11613029928903, 49.9385350007626],
          [1.11590920587645, 49.9385365020091]]


class ShortGeometryTests(unittest.TestCase):
    def test_five_point_gr21_portion_is_valid_without_changing_coordinates(self):
        geometry = {'type': 'LineString', 'coordinates': copy.deepcopy(POINTS)}
        validated = collect.validate_geometry(geometry)
        self.assertEqual(validated['segments'], [POINTS])
        self.assertEqual(validated['pointCount'], 5)
        self.assertEqual(validated['geometryKm'], .355)
        self.assertEqual(validated['officialLocation'], POINTS[0])

    def test_minimum_is_two_points_per_line_not_six_total(self):
        valid = collect.validate_geometry({'type': 'LineString', 'coordinates': [POINTS[0], POINTS[-1]]})
        self.assertEqual(valid['pointCount'], 2)
        for geometry in [
            {'type': 'LineString', 'coordinates': [POINTS[0]]},
            {'type': 'MultiLineString', 'coordinates': [[POINTS[0]], POINTS]},
            {'type': 'LineString', 'coordinates': [POINTS[0], POINTS[0]]},
            {'type': 'LineString', 'coordinates': [[0, 0], POINTS[-1]]},
        ]:
            with self.subTest(geometry=geometry), self.assertRaises(AssertionError):
                collect.validate_geometry(geometry)

    def test_export_and_profile_reader_accept_the_original_five_points(self):
        route = {'sourceId': recovery.SOURCE_ID, 'name': 'Portion du GR21 sur chemin du Camp de César',
                 'gpxSource': collect.DATASET, 'trace': 'assets/traces/2067.geojson', 'gpx': 'assets/traces/2067.gpx'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'assets/traces').mkdir(parents=True)
            with patch.object(build, 'GENERATED', root), patch.object(elevations, 'ROOT', root):
                build.write_geometry(route, [POINTS])
                self.assertEqual(prepare.parse((root / route['gpx']).read_bytes()),
                                 [[[round(p[0], 7), round(p[1], 7)] for p in POINTS]])
                for field in ['trace', 'gpx']:
                    segments, _ = elevations.geometry(route[field])
                    self.assertEqual(segments, [POINTS])
                self.assertEqual(collect.validate_geometry({'type': 'LineString', 'coordinates': POINTS})['pointCount'], 5)

    def test_targeted_recovery_keeps_the_initial_snapshot_and_other_records(self):
        feature = {'properties': {'OBJECTID': 13592, 'Nom_iti': 'Portion du GR21 sur chemin du Camp de César',
                                 'Type': 'gr', 'Pedestre': 'oui', 'SHAPE_Leng': 356.416690679},
                   'geometry': {'type': 'LineString', 'coordinates': POINTS}}
        raw = json.dumps({'features': [feature]}).encode()
        previous = {'sourceId': recovery.SOURCE_ID, 'name': feature['properties']['Nom_iti'],
                    'sourceFormat': 'GeoJSON', 'sourceFeatureId': 13592, 'sourceDatasetUrl': collect.URL,
                    'sourceDatasetSha256': hashlib.sha256(raw).hexdigest(), 'status': 'trace-inexploitable', 'issue': ''}
        other = {'sourceId': 'unrelated-source', 'status': 'sans-gpx-publie'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'catalogue/snapshots').mkdir(parents=True)
            cache = root / 'cache'
            cache.mkdir()
            cached = cache / hashlib.sha256(collect.URL.encode()).hexdigest()
            cached.write_bytes(raw)
            original = root / 'catalogue/snapshots/cd76.json.gz'
            original.write_bytes(gzip.compress(json.dumps([previous, other]).encode(), mtime=0))
            original_bytes = original.read_bytes()
            inventory_path = root / 'catalogue/inventaire-complementaire.json'
            inventory_path.write_text(json.dumps({'records': [previous, other]}))
            with patch('urllib.request.urlopen', side_effect=AssertionError('Recovery must be offline')):
                result, changed = recovery.recover(root=root, cache_dir=cache)
                self.assertEqual(result['segments'], [POINTS])
                self.assertEqual(len(changed), 2)
                snapshot_bytes = (root / recovery.OVERLAY).read_bytes()
                _, repeated_changes = recovery.recover(root=root, cache_dir=cache)
            self.assertEqual(repeated_changes, [])
            self.assertEqual(original.read_bytes(), original_bytes)
            self.assertEqual((root / recovery.OVERLAY).read_bytes(), snapshot_bytes)
            updated = json.loads(inventory_path.read_text())
            self.assertEqual(updated['records'][1], other)
            self.assertEqual(updated['records'][0]['sourceDatasetSha256'], previous['sourceDatasetSha256'])
            self.assertNotIn('issue', updated['records'][0])


if __name__ == '__main__':
    unittest.main()
