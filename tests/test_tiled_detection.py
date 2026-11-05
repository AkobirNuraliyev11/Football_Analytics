import importlib.util
import unittest
from football_intelligence.detection import Detection, FootballDetector, detection_tiles, merge_tile_detections
from football_intelligence.models import BoundingBox


class TileMergeTests(unittest.TestCase):
    def test_duplicate_suppression_preserves_distinct_people_and_ball(self):
        a=Detection(BoundingBox(10,10,30,60),.9,'person')
        b=Detection(BoundingBox(11,11,31,61),.8,'person')
        c=Detection(BoundingBox(26,10,46,60),.7,'person')
        ball=Detection(a.bbox,.6,'ball')
        self.assertEqual(merge_tile_detections([b,c,a,ball]),[a,c,ball])

    def test_tiles_cover_4k_frame_and_overlap(self):
        tiles=detection_tiles(3840,2160,1280)
        self.assertEqual(len(tiles),8)
        xs=sorted({x for x,_,_,_ in tiles})
        ys=sorted({y for _,y,_,_ in tiles})
        self.assertEqual((xs[0],ys[0],tiles[-1][2],tiles[-1][3]),(0,0,3840,2160))
        self.assertTrue(all(b-a<=1120 for a,b in zip(xs,xs[1:])))

    @unittest.skipUnless(importlib.util.find_spec('numpy'),'Requires detection extras')
    def test_global_coordinates_and_internal_seam_rejection(self):
        import numpy as np
        detector=FootballDetector.__new__(FootballDetector)
        calls=[]
        def predict(rgb):
            calls.append(rgb.shape)
            if len(calls)==1:
                return [Detection(BoundingBox(318,10,320,50),.99,'person')]
            return [Detection(BoundingBox(20,10,40,50),.9,'person')]
        detector._detect_region=predict
        found=detector.detect(np.zeros((100,480,3),dtype=np.uint8),tile_size=320)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0].bbox,BoundingBox(180,10,200,50))

    @unittest.skipUnless(importlib.util.find_spec('numpy'),'Requires detection extras')
    def test_normal_resolution_uses_original_path(self):
        import numpy as np
        detector=FootballDetector.__new__(FootballDetector)
        calls=[]
        detector._detect_region=lambda rgb:calls.append(rgb.shape) or []
        detector.detect(np.zeros((1080,1920,3),dtype=np.uint8))
        self.assertEqual(calls,[(1080,1920,3)])
        with self.assertRaises(ValueError):detector.detect(np.zeros((10,10,3)),tile_size=100)
