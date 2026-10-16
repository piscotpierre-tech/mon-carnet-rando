import hashlib
import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
prepare = importlib.import_module('prepare-catalogue')


def track(metadata=b''):
    return b'<gpx>' + metadata + b'<trk><trkseg>' + b''.join(
        f'<trkpt lon="-1.{i:03}" lat="49"><ele>{10+i}</ele></trkpt>'.encode()
        for i in range(6)
    ) + b'</trkseg></trk></gpx>'


class SourceRecoveryTests(unittest.TestCase):
    def test_only_trailing_nul_padding_is_removed(self):
        source = track() + b'\r\n'
        normalized, repairs = prepare.normalize_gpx(source + b'\0' * 25)
        self.assertEqual(normalized, source)
        self.assertEqual(repairs[0]['removedBytes'], 25)
        self.assertEqual(prepare.parse(normalized), prepare.parse(source))
        self.assertEqual(prepare.normalize_gpx(normalized), (normalized, []))

    def test_interior_nuls_and_truncated_documents_are_rejected(self):
        for raw in [track().replace(b'<trk>', b'<trk>\0'), track()[:-6] + b'\0' * 8]:
            with self.assertRaises(ET.ParseError):
                normalized, _ = prepare.normalize_gpx(raw)
                prepare.parse(normalized)

    def test_description_html_breaks_preserve_geometry(self):
        clean = track(b'<desc>Monter<br/>puis tourner.</desc>')
        normalized, repairs = prepare.normalize_gpx(clean.replace(b'<br/>', b'<br>'))
        self.assertEqual(normalized, clean)
        self.assertEqual(repairs[0]['type'], 'description-html-breaks')
        self.assertEqual(prepare.parse(normalized), prepare.parse(clean))
        with self.assertRaises(ET.ParseError):
            normalized, _ = prepare.normalize_gpx(track().replace(b'<trk>', b'<trk><br>'))
            prepare.parse(normalized)

    def test_undeclared_latin1_only_changes_text_encoding(self):
        clean = track('<name>Vallée</name>'.encode())
        normalized, repairs = prepare.normalize_gpx(clean.decode().encode('latin1'))
        self.assertEqual(normalized, clean)
        self.assertEqual(repairs[0]['type'], 'undeclared-latin1')
        declared = b'<?xml version="1.0" encoding="UTF-8"?>' + clean.decode().encode('latin1')
        with self.assertRaises(ET.ParseError):
            normalized, _ = prepare.normalize_gpx(declared)
            prepare.parse(normalized)

    def test_html_errors_and_projected_coordinates_stay_rejected(self):
        for raw in [b'<html><body>Erreur<br>indisponible</body></html>',
                    track().replace(b'lat="49"', b'lat="6921667.9"') + b'\0' * 8]:
            with self.assertRaises((ET.ParseError, AssertionError)):
                normalized, _ = prepare.normalize_gpx(raw)
                prepare.parse(normalized)

    def test_cdata_and_valid_xml_are_untouched(self):
        for raw in [track(), track(b'<desc><![CDATA[Monter<br>puis tourner]]></desc>')]:
            self.assertEqual(prepare.normalize_gpx(raw), (raw, []))

    def test_validation_preserves_original_hash_and_source_bytes(self):
        url = 'https://example.org/padded.gpx'
        raw = track() + b'\0' * 16
        with tempfile.TemporaryDirectory() as folder, patch.object(prepare, 'CACHE', Path(folder)):
            cached = Path(folder) / (hashlib.sha256(url.encode()).hexdigest() + '.gpx')
            cached.write_bytes(raw)
            result = prepare.validate({'gpxSource': url, 'issue': 'old parse failure'})
            self.assertEqual(result['status'], 'trace-verifiee')
            self.assertNotIn('issue', result)
            self.assertEqual(result['gpxSha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(result['validatedGpxSha256'], hashlib.sha256(track()).hexdigest())
            self.assertEqual(cached.read_bytes(), raw)

    def test_public_download_sends_its_documented_source_referer_on_cache_miss(self):
        url = 'https://example.org/gpx/20'
        page = 'https://example.org/parcours/20'
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return track()
        with tempfile.TemporaryDirectory() as folder, patch.object(prepare, 'CACHE', Path(folder)), \
                patch('urllib.request.urlopen', return_value=Response()) as fetch:
            result = prepare.validate({'gpxSource': url, 'sourceDownloadReferer': page})
            self.assertEqual(result['status'], 'trace-verifiee')
            self.assertEqual(fetch.call_args.args[0].get_header('Referer'), page)
        with tempfile.TemporaryDirectory() as folder, patch.object(prepare, 'CACHE', Path(folder)), \
                patch('urllib.request.urlopen') as fetch:
            result = prepare.validate({'gpxSource': url, 'sourceDownloadReferer': 'https://other.example/parcours/20'})
            self.assertEqual(result['status'], 'gpx-inexploitable')
            fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
