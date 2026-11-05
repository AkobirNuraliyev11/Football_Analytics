import hashlib
import io
import unittest
import zipfile
from scripts.restore_sensor_sample import verified_payload


class SensorSampleTests(unittest.TestCase):
    def setUp(self):
        self.payload = b'known sensor reference'
        self.record = dict(bytes=len(self.payload), sha256=hashlib.sha256(self.payload).hexdigest())

    def test_pinned_raw_and_single_zip_payloads(self):
        self.assertEqual(verified_payload(self.payload, self.record), self.payload)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            # Filenames are never extracted to the filesystem.
            archive.writestr('../../outside.csv', self.payload)
        self.assertEqual(verified_payload(stream.getvalue(), self.record), self.payload)

    def test_changed_or_oversized_source_is_rejected(self):
        for data in [b'wrong', b'x'*len(self.payload), b'x'*(1024*1024+100)]:
            with self.assertRaises(ValueError):
                verified_payload(data, self.record)

    def test_unexpected_archive_members_are_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('a', self.payload)
            archive.writestr('b', self.payload)
        with self.assertRaises(ValueError):
            verified_payload(stream.getvalue(), self.record)
