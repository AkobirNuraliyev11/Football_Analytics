import json
from pathlib import Path
import tempfile
import unittest
from scripts.diagnose_analysis import diagnose


class AnalysisDiagnosisTests(unittest.TestCase):
    def test_counts_local_tracks_separately_across_shots_and_preserves_gaps(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'manifest.json').write_text(json.dumps({'status':'completed','processed_frames':3}))
            person = {'kind':'person','track_id':1,'association_reason':'matched',
                      'projection_state':'ground_contact_unverified'}
            rows = [{'timestamp_s':0,'shot_id':0,'detections':[person,{'kind':'ball'}]},
                    {'timestamp_s':.2,'shot_id':0,'detections':[person]},
                    {'timestamp_s':.24,'shot_id':1,'detections':[person]}]
            (root/'tracks.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            (root/'telemetry-summary.json').write_text(json.dumps(
                {'status':'unavailable','rejection_counts':{'ground_contact_unverified':3}}))
            result = diagnose(root)
            self.assertEqual(result['person_track_count'],2)
            self.assertEqual(result['person_tracks'][0]['gaps_over_0_12s'],1)
            self.assertEqual(result['association_reasons'],{'matched':3})
            self.assertEqual(result['measurement_status'],'unavailable')
            (root/'manifest.json').write_text(json.dumps({'status':'completed','processed_frames':4}))
            with self.assertRaisesRegex(ValueError,'Track records'):
                diagnose(root)
