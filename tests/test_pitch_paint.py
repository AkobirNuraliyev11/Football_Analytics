import unittest
import importlib.util
AVAILABLE = all(importlib.util.find_spec(name) for name in ('numpy','cv2'))
if AVAILABLE:
    import numpy as np
    import cv2
from football_intelligence.config import PitchConfig
from football_intelligence.pitch_paint import marking_samples, paint_evidence


@unittest.skipUnless(AVAILABLE, 'Requires calibration extras')
class PitchPaintTests(unittest.TestCase):
    def setUp(self):
        self.pitch=PitchConfig()
        self.rgb=np.full((720,1100,3),(110,155,95),dtype=np.uint8)
        self.matrix=np.array([[.1,0,-2],[0,.1,-2],[0,0,1.]])
        self.support=[[20,20],[1070,20],[1070,700],[20,700]]
        for points in marking_samples(self.pitch).values():
            cv2.polylines(self.rgb,[(points*10+20).astype(np.int32)],False,(235,235,235),2)

    def test_visible_geometry_passes_but_translated_fit_fails(self):
        self.assertTrue(paint_evidence(self.rgb,self.matrix,self.support,self.pitch)['accepted'])
        shifted=self.matrix.copy();shifted[0,2]+=7;shifted[1,2]+=4
        self.assertFalse(paint_evidence(self.rgb,shifted,self.support,self.pitch)['accepted'])

    def test_pale_turf_and_white_screen_do_not_supply_paint(self):
        self.rgb[:]=(130,155,110)
        self.assertFalse(paint_evidence(self.rgb,self.matrix,self.support,self.pitch)['accepted'])
        self.rgb[:]=240
        self.assertFalse(paint_evidence(self.rgb,self.matrix,self.support,self.pitch)['accepted'])

    def test_insufficient_region_abstains(self):
        small=[[550,20],[560,20],[560,50],[550,50]]
        self.assertFalse(paint_evidence(self.rgb,self.matrix,small,self.pitch)['accepted'])
