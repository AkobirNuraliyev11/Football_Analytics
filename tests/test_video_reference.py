import importlib.util
import unittest


@unittest.skipUnless(all(importlib.util.find_spec(n) for n in ('numpy','scipy')), 'Requires detection extras')
class VideoReferenceTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from football_intelligence.benchmarks.video_reference import score_frames
        self.score=score_frames
        self.project=lambda points:np.array(points,dtype=float)*.1
        self.refs={i:{('A','1'):[100+i*5,100]} for i in range(3)}
        self.rows=[dict(frame_index=i,timestamp_s=i*.5,detections=[dict(kind='person',bbox=dict(
            x_min=99+i*5,y_min=99,x_max=101+i*5,y_max=101))]) for i in range(3)]

    def run_score(self):
        return self.score(self.rows,self.refs,self.project,sample_gap_s=.5,interval_s=1.)

    def test_known_motion_and_pixel_meter_units(self):
        self.rows[-1]['detections'][0]['bbox']['x_min']+=2
        self.rows[-1]['detections'][0]['bbox']['x_max']+=2
        result=self.run_score()
        self.assertEqual(result['reference_interval_count'],1)
        self.assertEqual(result['interval_count'],1)
        self.assertAlmostEqual(result['position_discrepancy_m']['center']['mean'],.2/3)
        self.assertAlmostEqual(result['net_speed_discrepancy_kmh']['center']['mean'],.72)

    def test_missing_detection_stays_in_both_denominators(self):
        self.rows[1]['detections']=[]
        result=self.run_score()
        self.assertEqual(result['matched_observations'],2)
        self.assertEqual(result['reference_observations'],3)
        self.assertEqual(result['reference_interval_count'],1)
        self.assertEqual(result['interval_count'],0)
        self.assertIsNone(result['net_speed_discrepancy_kmh']['center']['mean'])

    def test_frame_gap_cannot_create_interval(self):
        self.rows.pop(1)
        result=self.run_score()
        self.assertEqual(result['interval_count'],0)
        self.assertEqual(result['reference_interval_count'],0)

    def test_ambiguous_identity_is_withheld(self):
        for refs in self.refs.values():refs[('A','2')]=refs[('A','1')][:]
        result=self.run_score()
        self.assertEqual(result['reference_observations'],6)
        self.assertEqual(result['matched_observations'],0)
        self.assertEqual(result['reference_interval_count'],2)

    def test_invalid_or_nonmonotonic_time_rejected(self):
        for t in [0,float('nan')]:
            self.rows[1]['timestamp_s']=t
            with self.assertRaises(ValueError):self.run_score()
