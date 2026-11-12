import json
from pathlib import Path
import tempfile
import unittest
from scripts.evaluate_ball_candidates import evaluate
from football_intelligence.model_assets import sha256


class BallCandidateReviewTests(unittest.TestCase):
    def test_threshold_tradeoff_counts_rejected_true_candidates(self):
        with tempfile.TemporaryDirectory() as folder:
            tracks=Path(folder)/'tracks.jsonl'
            tracks.write_text(json.dumps({'frame_index':0,'detections':[
                {'track_id':1,'kind':'ball','confidence':.2},
                {'track_id':2,'kind':'ball','confidence':.45}]}))
            review={'tracks_sha256':sha256(tracks),'candidates':[
                {'frame_index':0,'track_id':1,'label':'ball'},
                {'frame_index':0,'track_id':2,'label':'not_ball'}]}
            report=evaluate(tracks,review)
            self.assertEqual(report['thresholds'][1]['rejected_true_candidates'],1)
            self.assertEqual(report['thresholds'][1]['retained_false_candidates'],1)
            self.assertEqual(report['thresholds'][2]['retained_false_candidates'],0)
            review['candidates'].append(review['candidates'][0])
            with self.assertRaisesRegex(ValueError,'Duplicate'):evaluate(tracks,review)
            review['tracks_sha256']='wrong'
            with self.assertRaisesRegex(ValueError,'fingerprint'):evaluate(tracks,review)
