import unittest
import importlib.util


@unittest.skipUnless(importlib.util.find_spec("cv2") and importlib.util.find_spec("numpy"),"Requires calibration extras")
class PenaltyGeometryTests(unittest.TestCase):
    def test_both_ends_recover_shift_and_limit_support(self):
        import numpy as np
        import cv2
        from football_intelligence.calibration import CalibrationError
        from football_intelligence.config import PitchConfig
        from football_intelligence.penalty_geometry import check_penalty_area, markings
        for side, x in [('left',11),('right',94)]:
            rgb=np.zeros((760,1130,3),np.uint8)
            rgb[:]=[60,130,55]
            for axis,level,low,high in markings(PitchConfig(),side):
                ends=np.array([[level,low],[level,high]])
                if axis==1: ends=ends[:,::-1]
                a,b=np.rint(ends*10+40).astype(int)
                cv2.line(rgb,tuple(a),tuple(b),(200,215,195),1,cv2.LINE_AA)
            seed=np.array([[.1,0,-3.6],[0,.1,-4.25],[0,0,1]])
            m=check_penalty_area(rgb,seed,side)
            xy=m.project([x*10+40,380])
            self.assertLess(np.linalg.norm(xy-[x,34]),.12)
            with self.assertRaises(CalibrationError):m.project([565,380])
            rgb[:]=[60,130,55]
            with self.assertRaises(CalibrationError):check_penalty_area(rgb,seed,side)
