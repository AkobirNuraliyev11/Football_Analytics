import unittest
import importlib.util
from football_intelligence.benchmarks.field_context import ball_region


@unittest.skipUnless(importlib.util.find_spec('numpy') and importlib.util.find_spec('cv2'),'Requires calibration extras')
class FieldContextTests(unittest.TestCase):
    def test_region_requires_fresh_paint_checked_geometry(self):
        c=dict(method='overhead_boundaries_paint_checked',image_evidence={'accepted':True},
               frame_index=3,width=200,height=100,matrix=[[1,0,0],[0,1,0],[0,0,1]],
               pitch={'length_m':105,'width_m':68})
        b=dict(x_min=150,x_max=155,y_min=10,y_max=15)
        def check(fit,index=3):return ball_region(b,fit,frame_index=index,width=200,height=100)
        self.assertEqual(check(c),'outside_supported_pitch')
        self.assertEqual(check(c,4),'unknown')
        self.assertEqual(check(c|{'method':'semantic'}),'unknown')
        self.assertEqual(check(c|{'image_evidence':{'accepted':False}}),'unknown')
        self.assertEqual(check(None),'unknown')
        self.assertEqual(check(c|{'matrix':[[0,0,0]]}),'unknown')

    def test_padded_boundary_is_not_clamped(self):
        c=dict(method='overhead_boundaries_paint_checked',image_evidence={'accepted':True},
               frame_index=0,width=200,height=100,matrix=[[1,0,0],[0,1,0],[0,0,1]],
               pitch={'length_m':105,'width_m':68})
        self.assertEqual(ball_region(dict(x_min=105,x_max=107,y_min=20,y_max=22),c,
                         frame_index=0,width=200,height=100),'near_pitch')
