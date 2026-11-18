import unittest
from scripts.score_ball_detector import score


class BallDetectorScoreTests(unittest.TestCase):
    def test_misses_and_uncertain_visibility_are_distinct(self):
        review={'source_sha256':'same','frames':[dict(frame_index=0,status='visible',center_px=[10,10],radius_px=3),dict(frame_index=1,status='uncertain')]}
        det={'bbox':dict(x_min=9,y_min=9,x_max=11,y_max=11),'confidence':.3}
        rows=[dict(mode=m,frame_index=f,seconds=1,detections=[det] if m=='a' else []) for m in ('a','b') for f in (0,1)]
        reports=[dict(source_sha256='same',rows=rows)]
        r=score(reports,review)['modes']
        self.assertEqual(r['a']['matched_frames'],1)
        self.assertEqual(r['b']['missed_frames'],1)
        self.assertEqual(r['a']['excluded_uncertain_frames'],1)
        self.assertEqual(score(reports,review,.4)['modes']['a']['missed_frames'],1)
        with self.assertRaisesRegex(ValueError,'Mixed source'):
            score(reports+[dict(source_sha256='other',rows=[])],review)
        with self.assertRaisesRegex(ValueError,'Duplicate prediction'):
            score(reports*2,review)
        with self.assertRaisesRegex(ValueError,'Missing paired'):
            score([dict(source_sha256='same',rows=rows[:-1])],review)
