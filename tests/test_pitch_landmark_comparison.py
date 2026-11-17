import unittest
from football_intelligence.benchmarks.pitch_landmarks import compare_landmarks


class PitchLandmarkComparisonTests(unittest.TestCase):
    def test_missing_low_confidence_stays_in_denominator(self):
        refs=[dict(frame=0,keypoint_index=0,pixel=[0,0],uncertainty_px=2),
              dict(frame=1,keypoint_index=0,pixel=[0,0],uncertainty_px=2)]
        preds=[dict(mode='a',frame=0,points=[[3,4,.9]]),
               dict(mode='a',frame=1,points=[[0,0,.1]]),
               dict(mode='b',frame=0,points=[[0,0,.9]])]
        r=compare_landmarks(preds,refs)
        self.assertEqual(r['modes']['a']['missing'],1)
        self.assertEqual(r['modes']['b']['missing'],1)
        self.assertEqual(r['modes']['a']['median_error_px'],5)
        self.assertEqual(r['cases'][0]['predictions']['a']['review_uncertainty_interval_px'],[3,7])

    def test_duplicate_or_nonfinite_reviews_are_rejected(self):
        refs=[dict(frame=0,keypoint_index=0,pixel=[0,0],uncertainty_px=2)]
        preds=[dict(mode=m,frame=0,points=[[0,0,1]]) for m in ('a','b')]
        with self.assertRaises(ValueError):compare_landmarks(preds,refs*2)
        with self.assertRaises(ValueError):compare_landmarks(preds*2,refs)
        refs[0]['pixel']=[float('nan'),0]
        with self.assertRaises(ValueError):compare_landmarks(preds,refs)
