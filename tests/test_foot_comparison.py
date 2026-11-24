import json
from pathlib import Path
import tempfile
import unittest
from scripts.compare_foot_reviews import compare

class FootComparisonTests(unittest.TestCase):
    def test_mismatched_geometry_is_rejected_before_reporting_improvement(self):
        with tempfile.TemporaryDirectory() as temp:
            paths=[]
            for i in range(2):
                p=Path(temp)/str(i);p.mkdir();paths.append(p)
                (p/'manifest.json').write_text(json.dumps(dict(status='completed',source_sha256='s',tracks_sha256='t',quality_sha256=str(i),processed_frames=1)))
                (p/'comparison.json').write_text(json.dumps(dict(pose=dict(measured_observations=0),foot_status_counts={})))
                (p/'feet.jsonl').write_text(json.dumps(dict(frame_index=0,timestamp_s=0,pose_estimates=dict(observations=[]),baseline=dict(observations=[])))+'\n')
            with self.assertRaisesRegex(ValueError,'geometry differ'):compare(paths)
            m=json.loads((paths[1]/'manifest.json').read_text());m['quality_sha256']='0';(paths[1]/'manifest.json').write_text(json.dumps(m))
            self.assertEqual(compare(paths)['frames'],1)
            r=json.loads((paths[1]/'feet.jsonl').read_text());r['timestamp_s']=.04;(paths[1]/'feet.jsonl').write_text(json.dumps(r)+'\n')
            with self.assertRaisesRegex(ValueError,'windows differ'):compare(paths)
