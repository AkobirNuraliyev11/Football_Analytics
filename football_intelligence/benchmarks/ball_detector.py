"""Opt-in specialist ball detector for evaluation; not the production default."""
from pathlib import Path

from football_intelligence.detection import Detection, detection_tiles, merge_tile_detections
from football_intelligence.model_assets import sha256
from football_intelligence.models import BoundingBox

BALL_SHA256 = '678fbad05134f19c5094cb8d273812ec9c6691228180d46832551ecf99ed2912'
BALL_SOURCE = 'https://github.com/roboflow/sports/blob/main/examples/soccer/setup.sh'
BALL_DRIVE_ID = '1isw4wx-MK9h9LMr36VvIWlJD6ppUvw7V'


class SpecialistBallDetector:
    def __init__(self, path, *, device='cpu'):
        import os
        path = Path(path)
        if sha256(path) != BALL_SHA256:
            raise ValueError('Specialist ball model fingerprint mismatch')
        runtime = path.parent / 'runtime'
        runtime.mkdir(exist_ok=True)
        os.environ.setdefault('YOLO_CONFIG_DIR', str(runtime.resolve()))
        from ultralytics import YOLO
        self.model = YOLO(str(path), task='detect')
        if self.model.names != {0: 'ball'}:
            raise ValueError('Unexpected specialist class schema')
        self.device = device

    def detect(self, rgb, *, tiled=True):
        import numpy as np
        height, width = rgb.shape[:2]
        regions = detection_tiles(width, height, 640) if tiled else [(0,0,width,height)]
        found = []
        for x,y,right,bottom in regions:
            result = self.model.predict(np.ascontiguousarray(rgb[y:bottom,x:right,::-1]),
                                        device=self.device, conf=.15, imgsz=640, verbose=False)[0]
            for box, confidence in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
                left,top,r,b = map(float,box)
                left,top=max(0.,left)+x,max(0.,top)+y
                r,b=min(float(right-x),r)+x,min(float(bottom-y),b)+y
                if r>left and b>top:
                    found.append(Detection(BoundingBox(left,top,r,b),float(confidence),'ball'))
        # Same-kind suppression only. Candidate identity is still unverified.
        return merge_tile_detections(found,iou_threshold=.1)
