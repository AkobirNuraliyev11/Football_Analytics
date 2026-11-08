import importlib.util
import unittest
from unittest.mock import Mock
from football_intelligence.calibration import CalibrationError, transform, update_camera
from football_intelligence.config import PitchConfig
from football_intelligence.overhead_calibration import calibrate_overhead
from football_intelligence.pitch_paint import marking_samples


@unittest.skipUnless(all(importlib.util.find_spec(n) for n in ('numpy','cv2')), 'Requires calibration extras')
class OverheadCalibrationTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        import cv2
        self.np,self.cv2=np,cv2
        self.pitch=PitchConfig()
        self.rgb=np.full((760,1160,3),(80,145,70),dtype=np.uint8)
        self.camera=np.array([[10.,.12,40],[.05,10.,30],[.00003,.00002,1.]])
        for path in marking_samples(self.pitch).values():
            cv2.polylines(self.rgb,[transform(self.camera,path).astype(np.int32)],False,(235,235,235),2)
        self.scope=dict(match_id='test',shot_id=0,frame_index=0,pitch=self.pitch)

    def test_recovers_full_pitch_without_reference_coordinates(self):
        c,e=calibrate_overhead(self.rgb,**self.scope)
        world=self.np.array([[30,20],[52.5,34],[80,50]])
        measured=transform(c.matrix,transform(self.camera,world))
        self.assertLess(float(self.np.linalg.norm(measured-world,axis=1).max()),.3)
        self.assertEqual(c.validation_count,0)
        self.assertTrue(e['accepted'])
        self.assertTrue(c.image_evidence['pitch_dimensions_assumed'])

    def test_blank_partial_and_boundary_only_views_abstain(self):
        blank=self.np.full_like(self.rgb,(80,145,70))
        boundary=blank.copy()
        corners=transform(self.camera,[[0,0],[105,0],[105,68],[0,68]]).astype(self.np.int32)
        self.cv2.polylines(boundary,[corners],True,(235,235,235),2)
        for rgb in (blank,self.rgb[:,:850],boundary):
            with self.assertRaises(CalibrationError):
                calibrate_overhead(rgb,**self.scope)

    def test_camera_update_rechecks_current_image_and_does_not_keep_stale_fit(self):
        c,_=calibrate_overhead(self.rgb,**self.scope)
        moved=self.cv2.warpAffine(self.rgb,self.np.array([[1.,0,7],[0,1.,5]]),(1160,760),borderValue=(80,145,70))
        new=update_camera(self.rgb,moved,c,match_id='test',shot_id=0,frame_index=1,
                          previous_timestamp_s=0,timestamp_s=.04)
        p=transform(self.camera,[[52.5,34]])+[7,5]
        self.assertLess(float(self.np.linalg.norm(transform(new.matrix,p)-[52.5,34])),.3)
        with self.assertRaises(CalibrationError):
            update_camera(self.rgb,self.np.zeros_like(self.rgb),c,match_id='test',shot_id=0,frame_index=1,
                          previous_timestamp_s=0,timestamp_s=.04)

    def test_detector_uses_image_geometry_without_pitch_model_inference(self):
        from football_intelligence.detection import FootballDetector
        detector=FootballDetector.__new__(FootballDetector)
        detector.pitch_model=Mock()
        c=detector.calibrate(self.rgb,**self.scope)
        self.assertEqual(c.method,'overhead_boundaries_paint_checked')
        detector.pitch_model.predict.assert_not_called()

    def test_surrounding_white_rectangle_is_not_the_pitch_boundary(self):
        self.cv2.rectangle(self.rgb,(8,8),(1145,745),(235,235,235),2)
        c,_=calibrate_overhead(self.rgb,**self.scope)
        point=transform(self.camera,[[30,20]])
        self.assertLess(float(self.np.linalg.norm(transform(c.matrix,point)-[30,20])),.3)
