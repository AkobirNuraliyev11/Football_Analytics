import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
from football_intelligence.benchmarks.ball_detector import SpecialistBallDetector


class SpecialistBallTests(unittest.TestCase):
    def test_modified_model_is_rejected_before_loading(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'model.pt';p.write_bytes(b'not the pinned model')
            with self.assertRaisesRegex(ValueError,'fingerprint'):
                SpecialistBallDetector(p)

    def test_tiles_restore_native_coordinates_and_rgb_is_converted(self):
        class Tensor:
            def __init__(self,x):self.x=np.array(x)
            def cpu(self):return self
            def numpy(self):return self.x
        calls=[]
        def predict(image,**kwargs):
            calls.append(image.copy())
            box=[400,20,410,30] if len(calls)==1 else [240,20,250,30]
            return [SimpleNamespace(boxes=SimpleNamespace(xyxy=Tensor([box]),conf=Tensor([.8])))]
        detector=SpecialistBallDetector.__new__(SpecialistBallDetector)
        detector.device='cpu';detector.model=SimpleNamespace(predict=predict)
        rgb=np.zeros((100,800,3),dtype=np.uint8);rgb[:]=[1,2,3]
        detections=detector.detect(rgb)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][0,0].tolist(),[3,2,1])
        self.assertEqual(len(detections),1)
        self.assertEqual(detections[0].bbox.x_min,400)
        self.assertEqual(detections[0].kind,'ball')
