"""Automatic image detections and semantic pitch keypoints; no user pixel input."""
from dataclasses import dataclass
from pathlib import Path

from .calibration import CalibrationError, Landmark, fit_calibration
from .config import PitchConfig
from .models import BoundingBox, PixelPoint, PitchPoint, Role
from .validation import finite


@dataclass(frozen=True)
class Detection:
    bbox: BoundingBox
    confidence: float
    kind: str
    role: Role = Role.UNKNOWN

    def __post_init__(self):
        finite("confidence", self.confidence, minimum=0)
        if self.confidence > 1 or self.kind not in {"person", "ball"}:
            raise ValueError("Invalid detection confidence or object kind")
        if not isinstance(self.bbox, BoundingBox) or not isinstance(self.role, Role):
            raise ValueError("Detection requires a validated bounding box and role")


def pitch_keypoint_layout(pitch: PitchConfig):
    """Roboflow 32-keypoint order, using regulation markings on configured pitch.

    Exclude ambiguous penalty-arc/intersection labels. Ordering
    reference: roboflow/sports SoccerPitchConfiguration (see THIRD_PARTY.md).
    """
    length, width = pitch.length_m, pitch.width_m
    if length < 90 or width < 45:
        raise ValueError("Pitch keypoint layout expects a full-size football pitch")
    cy = width / 2
    box_top, box_bottom = cy - 20.16, cy + 20.16
    goal_top, goal_bottom = cy - 9.16, cy + 9.16
    points = [(0,0), (0,box_top), (0,goal_top), (0,goal_bottom), (0,box_bottom), (0,width),
              (5.5,goal_top), (5.5,goal_bottom), (11,cy), (16.5,box_top), None, None,
              (16.5,box_bottom), (length/2,0), (length/2,cy-9.15), (length/2,cy+9.15),
              (length/2,width), (length-16.5,box_top), None, None, (length-16.5,box_bottom),
              (length-11,cy), (length-5.5,goal_top), (length-5.5,goal_bottom),
              (length,0), (length,box_top), (length,goal_top), (length,goal_bottom),
              (length,box_bottom), (length,width), (length/2-9.15,cy), (length/2+9.15,cy)]
    return points


def landmarks_from_keypoints(xyc, width, height, pitch, threshold=0.5):
    import numpy as np
    xyc = np.asarray(xyc)
    if xyc.shape != (32, 3):
        raise ValueError(f"Expected Roboflow 32x3 keypoints, got {xyc.shape}")
    result = []
    for index, (pixel, location) in enumerate(zip(xyc, pitch_keypoint_layout(pitch))):
        x, y, confidence = map(float, pixel)
        if location is not None and np.isfinite(pixel).all() and confidence >= threshold and 0 <= x < width and 0 <= y < height:
            result.append(Landmark(f"pitch-{index+1:02}", PixelPoint(x,y), PitchPoint(*location)))
    return result


class FootballDetector:
    inference_policy = "1280-pixel overlapping tiles above 2560-pixel inputs; full-frame otherwise"

    def __init__(self, model_dir: Path, *, device="cpu"):
        from .model_assets import MODELS, EXPECTED_SHA256, sha256
        import os
        import json
        # Keep runtime settings inside the project model directory.
        runtime = model_dir.resolve() / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("YOLO_CONFIG_DIR", str(runtime))
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ValueError('Install detection support: pip install -e ".[detection]"') from exc
        self.device = device
        paths = {k: model_dir / filename for k, (filename, _) in MODELS.items()}
        if not all(p.is_file() for p in paths.values()):
            raise ValueError("Models missing; run download-models first")
        manifest_path = model_dir / "model-manifest.json"
        if not manifest_path.is_file():
            raise ValueError("Model provenance manifest missing; run download-models first")
        manifest = json.loads(manifest_path.read_text())
        self.fingerprints = {k: sha256(p) for k,p in paths.items()}
        if any(self.fingerprints[k] != manifest["models"][k]["sha256"] or
               self.fingerprints[k] != EXPECTED_SHA256[k] for k in paths):
            raise ValueError("Model content changed since download; refusing to load")
        self.players = YOLO(str(paths["players"]), task="detect")
        self.pitch_model = YOLO(str(paths["pitch"]), task="pose")
        supported = {"ball", "goalkeeper", "player", "referee"}
        if set(self.players.names.values()) != supported:
            raise ValueError(f"Unexpected player model labels: {self.players.names}")

    def detect(self, rgb, *, tile_size=None):
        """Preserve small athletes in high-resolution inputs with overlapping crops.

        None selects 1280-pixel tiles above 2560 pixels. Zero reproduces the
        original full-frame path for comparisons. No user pixel input is needed.
        """
        height, width = rgb.shape[:2]
        if tile_size is None:
            tile_size = 1280 if max(height, width) > 2560 else 0
        if type(tile_size) is not int or tile_size < 0 or 0 < tile_size < 320:
            raise ValueError("tile_size must be zero or an integer of at least 320")
        if not tile_size or max(height, width) <= tile_size:
            return self._detect_region(rgb)
        candidates = []
        for x, y, right, bottom in detection_tiles(width, height, tile_size):
            for d in self._detect_region(rgb[y:bottom, x:right]):
                b = d.bbox
                # Cropping a person at an internal seam corrupts its foot anchor.
                # Overlap lets another tile observe the complete box.
                if ((x > 0 and b.x_min <= 2) or (y > 0 and b.y_min <= 2) or
                    (right < width and b.x_max >= right-x-2) or
                    (bottom < height and b.y_max >= bottom-y-2)):
                    continue
                candidates.append(Detection(BoundingBox(b.x_min+x,b.y_min+y,b.x_max+x,b.y_max+y),
                                            d.confidence,d.kind,d.role))
        return merge_tile_detections(candidates)

    def _detect_region(self, rgb):
        import numpy as np
        height, width = rgb.shape[:2]
        # Ultralytics NumPy inputs are BGR, while our decoder contract is RGB.
        result = self.players.predict(np.ascontiguousarray(rgb[:,:,::-1]), device=self.device,
                                      conf=0.15, imgsz=1280, verbose=False)[0]
        detections = []
        roles = {"player": Role.OUTFIELD, "referee": Role.OFFICIAL, "goalkeeper": Role.GOALKEEPER}
        for xyxy, confidence, label in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy(), result.boxes.cls.cpu().numpy()):
            name = self.players.names[int(label)]
            left, top, right, bottom = map(float, xyxy)
            left, right = max(0., left), min(float(width), right)
            top, bottom = max(0., top), min(float(height), bottom)
            if right > left and bottom > top:
                detections.append(Detection(BoundingBox(left,top,right,bottom), float(confidence),
                                            "ball" if name == "ball" else "person", roles.get(name, Role.UNKNOWN)))
        return detections

    def calibrate(self, rgb, *, match_id, shot_id, frame_index, pitch=None):
        import numpy as np
        pitch = pitch or PitchConfig()
        from .overhead_calibration import calibrate_overhead
        try:
            calibration, _ = calibrate_overhead(rgb, match_id=match_id, shot_id=shot_id,
                                              frame_index=frame_index, pitch=pitch)
            return calibration
        except CalibrationError:
            # Partial and broadcast views retain the semantic-model candidate path.
            pass
        height, width = rgb.shape[:2]
        result = self.pitch_model.predict(np.ascontiguousarray(rgb[:,:,::-1]), device=self.device,
                                          conf=0.25, imgsz=640, verbose=False)[0]
        if result.keypoints is None or len(result.keypoints.data) == 0:
            raise CalibrationError("No pitch keypoints detected")
        # Highest-confidence pitch instance; class schema is enforced by keypoint count.
        index = int(result.boxes.conf.argmax())
        landmarks = landmarks_from_keypoints(result.keypoints.data[index].cpu().numpy(), width, height, pitch)
        # More than the algebraic minimum is required for automatic initialization.
        if len(landmarks) < 6:
            raise CalibrationError("Fewer than six confident unambiguous pitch landmarks")
        calibration = fit_calibration(landmarks, match_id=match_id, shot_id=shot_id, frame_index=frame_index,
                                      width=width, height=height, pitch=pitch)
        if len(calibration.inlier_names) < 6:
            raise CalibrationError("Automatic calibration needs at least six consistent landmarks")
        return calibration


def detection_tiles(width, height, size):
    """Evenly cover the image with at least 160 pixels of overlap where possible."""
    from math import ceil
    def origins(length):
        if length <= size:
            return [0]
        count = ceil((length-size)/(size-160))+1
        return [round(i*(length-size)/(count-1)) for i in range(count)]
    return [(x,y,min(x+size,width),min(y+size,height))
            for y in origins(height) for x in origins(width)]


def merge_tile_detections(items):
    """Confidence-first, kind-specific overlap suppression across crop boundaries."""
    kept = []
    for item in sorted(items,key=lambda d:d.confidence,reverse=True):
        a = item.bbox
        duplicate = False
        for old in kept:
            if old.kind != item.kind:
                continue
            b = old.bbox
            intersection = max(0,min(a.x_max,b.x_max)-max(a.x_min,b.x_min))*max(0,min(a.y_max,b.y_max)-max(a.y_min,b.y_min))
            union = (a.x_max-a.x_min)*(a.y_max-a.y_min)+(b.x_max-b.x_min)*(b.y_max-b.y_min)-intersection
            if intersection/union > .5:
                duplicate = True
                break
        if not duplicate:
            kept.append(item)
    return kept
