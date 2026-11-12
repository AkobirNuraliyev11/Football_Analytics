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


    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'Requires detection extras')
    def test_full_frame_suppresses_duplicate_roles_without_removing_ball_or_neighbour(self):
        import numpy as np
        from types import SimpleNamespace
        from football_intelligence.models import Role
        class Tensor:
            def __init__(self, values): self.values = np.array(values)
            def cpu(self): return self
            def numpy(self): return self.values
        boxes = SimpleNamespace(
            xyxy=Tensor([[10,10,30,60], [10.2,10,30.2,60], [20,10,40,60], [10,10,30,60]]),
            conf=Tensor([.8,.9,.75,.7]), cls=Tensor([0,1,0,2]))
        detector = FootballDetector.__new__(FootballDetector)
        detector.device = 'cpu'
        detector.players = SimpleNamespace(names={0:'player',1:'referee',2:'ball'},
                                          predict=lambda *args, **kwargs:[SimpleNamespace(boxes=boxes)])
        found = detector.detect(np.zeros((100,200,3), dtype=np.uint8))
        self.assertEqual(len(found),3)
        self.assertEqual(sum(d.kind=='person' for d in found),2)
        self.assertEqual(found[0].role,Role.OFFICIAL)
        self.assertEqual(sum(d.kind=='ball' for d in found),1)

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
