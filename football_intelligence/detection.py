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

    def detect(self, rgb):
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
