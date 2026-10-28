"""Ground-plane homographies, explicit frame scope, and guarded optical-flow updates."""

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
import uuid

from .config import PitchConfig
from .models import AthleteObservation, PitchPoint, PixelPoint
from .validation import finite, identifier, integer


class CalibrationError(ValueError):
    pass


def dependencies():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise CalibrationError('Install calibration support: python3 -m pip install -e ".[calibration]"') from exc
    return cv2, np


@dataclass(frozen=True)
class Landmark:
    name: str
    pixel: PixelPoint
    pitch: PitchPoint

    def __post_init__(self):
        identifier("landmark name", self.name)
        if not isinstance(self.pixel, PixelPoint) or not isinstance(self.pitch, PitchPoint):
            raise CalibrationError("Landmarks require PixelPoint and PitchPoint values")


@dataclass(frozen=True)
class FitConfig:
    ransac_threshold_m: float = 0.75
    min_inlier_ratio: float = 0.6
    max_fit_rmse_m: float = 0.5
    max_validation_rmse_m: float = 1.0
    min_pitch_hull_area_m2: float = 20.0

    def __post_init__(self):
        for name, value in asdict(self).items():
            finite(name, value, minimum=0.000001)
        if self.min_inlier_ratio > 1:
            raise CalibrationError("min_inlier_ratio must be <= 1")


def transform(matrix, points):
    _, np = dependencies()
    points = np.asarray(points, dtype=np.float64)
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise CalibrationError("Homography must be a finite 3x3 matrix")
    if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
        raise CalibrationError("Points must be finite Nx2 coordinates")
    projected = np.column_stack([points, np.ones(len(points))]) @ matrix.T
    if (np.abs(projected[:, 2]) < 1e-10).any():
        raise CalibrationError("Point is too close to the projective horizon")
    result = projected[:, :2] / projected[:, 2, None]
    if not np.isfinite(result).all():
        raise CalibrationError("Projection is non-finite")
    return result


def check_landmarks(landmarks, width, height, pitch):
    names, pixels, locations = set(), set(), set()
    for item in landmarks:
        if item.name in names or (item.pixel.x, item.pixel.y) in pixels or (item.pitch.x_m, item.pitch.y_m) in locations:
            raise CalibrationError("Landmarks must have unique names, pixels, and pitch positions")
        names.add(item.name)
        pixels.add((item.pixel.x, item.pixel.y))
        locations.add((item.pitch.x_m, item.pitch.y_m))
        if not (0 <= item.pixel.x < width and 0 <= item.pixel.y < height):
            raise CalibrationError("Landmark pixel lies outside the native raster")
        if not item.pitch.is_on_pitch(pitch):
            raise CalibrationError("Landmark lies outside the configured pitch")


def arrays(landmarks):
    _, np = dependencies()
    return (np.array([[p.pixel.x, p.pixel.y] for p in landmarks], dtype=np.float64),
            np.array([[p.pitch.x_m, p.pitch.y_m] for p in landmarks], dtype=np.float64))


def check_spread(points, min_area):
    cv2, np = dependencies()
    if len(points) < 4 or cv2.contourArea(cv2.convexHull(points.astype(np.float32))) < min_area:
        raise CalibrationError("Need at least four well-spread, non-collinear landmarks")


@dataclass(frozen=True)
class Calibration:
    calibration_id: str
    match_id: str
    shot_id: int
    frame_index: int
    width: int
    height: int
    pitch: PitchConfig
    matrix: tuple
    landmarks: tuple[Landmark, ...]
    inlier_names: tuple[str, ...]
    fit_rmse_m: float
    validation_count: int
    validation_rmse_m: float | None
    method: str
    parent_id: str | None = None

    def project(self, point: PixelPoint, *, match_id: str, shot_id: int,
                frame_index: int, width: int, height: int) -> PitchPoint:
        if (match_id, shot_id, frame_index, width, height) != (
                self.match_id, self.shot_id, self.frame_index, self.width, self.height):
            raise CalibrationError("Calibration belongs to a different match, shot, frame, or raster")
        if not (0 <= point.x < width and 0 <= point.y < height):
            raise CalibrationError("Pixel lies outside the calibrated raster")
        # Avoid extrapolation beyond the observed ground region.
        cv2, np = dependencies()
        support, _ = arrays([p for p in self.landmarks if p.name in self.inlier_names])
        if cv2.pointPolygonTest(cv2.convexHull(support.astype(np.float32)), (point.x, point.y), False) < 0:
            raise CalibrationError("Pixel is outside the inlier landmark support region")
        x, y = transform(self.matrix, [[point.x, point.y]])[0]
        return PitchPoint(float(x), float(y))

    def project_observation(self, observation: AthleteObservation, *, width: int, height: int):
        # Never retain an old projection if the present ground contact is uncertain.
        if not observation.ground_contact_reliable:
            return replace(observation, pitch_position=None, calibration_id=None)
        position = self.project(observation.bbox.foot_anchor, match_id=observation.match_id,
                                shot_id=observation.shot_id, frame_index=observation.frame_index,
                                width=width, height=height)
        return replace(observation, pitch_position=position if position.is_on_pitch(self.pitch) else None,
                       calibration_id=self.calibration_id)

    def to_dict(self):
        return {"schema_version": 1, **asdict(self),
                "inlier_count": len(self.inlier_names),
                "rejected_names": [p.name for p in self.landmarks if p.name not in self.inlier_names],
                "coordinate_space": "native_unrotated_raster",
                "scope": "exact_frame_and_inlier_convex_hull",
                "accuracy_note": "Fit residual is not independent measurement accuracy"}


def fit_calibration(landmarks, *, match_id: str, shot_id: int, frame_index: int,
                    width: int, height: int, pitch: PitchConfig | None = None,
                    validation_landmarks=(), config: FitConfig | None = None) -> Calibration:
    cv2, np = dependencies()
    identifier("match_id", match_id)
    for name, value in [("shot_id", shot_id), ("frame_index", frame_index), ("width", width), ("height", height)]:
        integer(name, value, minimum=1 if name in {"width", "height"} else 0)
    pitch, config = pitch or PitchConfig(), config or FitConfig()
    landmarks, validation_landmarks = tuple(landmarks), tuple(validation_landmarks)
    check_landmarks(landmarks + validation_landmarks, width, height, pitch)
    src, dst = arrays(landmarks)
    check_spread(src, 4.0)
    check_spread(dst, config.min_pitch_hull_area_m2)
    matrix, mask = cv2.findHomography(src, dst, cv2.RANSAC, config.ransac_threshold_m,
                                     maxIters=5000, confidence=0.995)
    if matrix is None or mask is None or not np.isfinite(matrix).all():
        raise CalibrationError("Could not estimate a homography")
    keep = mask.ravel().astype(bool)
    if keep.sum() < 4 or keep.mean() < config.min_inlier_ratio:
        raise CalibrationError("Insufficient RANSAC inlier support")
    check_spread(src[keep], 4.0)
    check_spread(dst[keep], config.min_pitch_hull_area_m2)
    if np.linalg.matrix_rank(matrix) < 3:
        raise CalibrationError("Homography is singular")
    # A horizon crossing the supported region makes interpolation unsafe.
    denominators = np.column_stack([src[keep], np.ones(keep.sum())]) @ matrix[2]
    if not ((denominators > 1e-10).all() or (denominators < -1e-10).all()):
        raise CalibrationError("Projective horizon crosses landmark support")
    residuals = np.linalg.norm(transform(matrix, src) - dst, axis=1)
    rmse = float(np.sqrt(np.mean(residuals[keep] ** 2)))
    if rmse > config.max_fit_rmse_m:
        raise CalibrationError("Fit residual exceeds quality threshold")
    validation_rmse = None
    if validation_landmarks:
        check_src, check_dst = arrays(validation_landmarks)
        validation_rmse = float(np.sqrt(np.mean(np.sum((transform(matrix, check_src) - check_dst)**2, axis=1))))
        if validation_rmse > config.max_validation_rmse_m:
            raise CalibrationError("Independent validation residual exceeds quality threshold")
    return Calibration(str(uuid.uuid4()), match_id, shot_id, frame_index, width, height, pitch,
                       tuple(tuple(float(v) for v in row) for row in matrix), landmarks,
                       tuple(p.name for p, valid in zip(landmarks, keep) if valid), rmse,
                       len(validation_landmarks), validation_rmse, "landmark_ransac")


def update_camera(previous_rgb, current_rgb, previous: Calibration, *, match_id: str,
                  shot_id: int, frame_index: int, previous_timestamp_s: float,
                  timestamp_s: float, max_gap_s: float = 0.25,
                  max_forward_backward_px: float = 1.5, config: FitConfig | None = None) -> Calibration:
    """Track known ground landmarks one frame forward; fail closed on cuts/gaps/lost support.

    Caller must pass the actual previous frame and Step 2's current shot ID. Optical
    flow can drift even when checks pass; periodic landmark re-anchoring is required.
    """
    cv2, np = dependencies()
    for name, value in [("previous_timestamp_s", previous_timestamp_s), ("timestamp_s", timestamp_s),
                        ("max_gap_s", max_gap_s), ("max_forward_backward_px", max_forward_backward_px)]:
        finite(name, value, minimum=0.000001 if name.startswith("max_") else 0)
    if (match_id, shot_id, frame_index) != (previous.match_id, previous.shot_id, previous.frame_index + 1):
        raise CalibrationError("Camera updates require consecutive frames within the same match and shot")
    if not 0 < timestamp_s - previous_timestamp_s <= max_gap_s:
        raise CalibrationError("Camera update crossed a timestamp gap")
    shape = (previous.height, previous.width, 3)
    for frame in (previous_rgb, current_rgb):
        if frame.shape != shape or frame.dtype != np.uint8:
            raise CalibrationError("Camera update requires native-size uint8 RGB arrays")
    old = cv2.cvtColor(previous_rgb, cv2.COLOR_RGB2GRAY)
    new = cv2.cvtColor(current_rgb, cv2.COLOR_RGB2GRAY)
    anchors = [p for p in previous.landmarks if p.name in previous.inlier_names]
    src, _ = arrays(anchors)
    points = src.astype(np.float32).reshape(-1, 1, 2)
    moved, forward, _ = cv2.calcOpticalFlowPyrLK(old, new, points, None)
    if moved is None or forward is None or not np.isfinite(moved).all():
        raise CalibrationError("Ground landmark optical flow failed")
    returned, backward, _ = cv2.calcOpticalFlowPyrLK(new, old, moved, None)
    if returned is None or backward is None:
        raise CalibrationError("Reverse optical flow failed")
    valid = forward.ravel().astype(bool) & backward.ravel().astype(bool)
    valid &= np.linalg.norm((returned - points).reshape(-1, 2), axis=1) <= max_forward_backward_px
    updated = []
    for anchor, pixel, good in zip(anchors, moved.reshape(-1, 2), valid):
        if good and 0 <= pixel[0] < previous.width and 0 <= pixel[1] < previous.height:
            updated.append(Landmark(anchor.name, PixelPoint(float(pixel[0]), float(pixel[1])), anchor.pitch))
    result = fit_calibration(updated, match_id=match_id, shot_id=shot_id, frame_index=frame_index,
                             width=previous.width, height=previous.height, pitch=previous.pitch, config=config)
    return replace(result, method="optical_flow_ransac", parent_id=previous.calibration_id)


def fit_landmark_file(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    allowed = {"schema_version", "match_id", "shot_id", "frame_index", "width", "height", "pitch",
               "landmarks", "validation_landmarks", "config"}
    if not isinstance(raw, dict) or raw.keys() - allowed or type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        raise CalibrationError("Expected a schema_version 1 landmark object with known fields")
    def parse(items):
        if not isinstance(items, list):
            raise CalibrationError("Landmarks must be a list")
        result = []
        for item in items:
            if not isinstance(item, dict) or set(item) != {"name", "pixel", "pitch"}:
                raise CalibrationError("Each landmark needs name, pixel, and pitch")
            result.append(Landmark(item["name"], PixelPoint(*item["pixel"]), PitchPoint(*item["pitch"])))
        return result
    try:
        calibration = fit_calibration(parse(raw["landmarks"]),
            **{key: raw[key] for key in ("match_id", "shot_id", "frame_index", "width", "height")},
            pitch=PitchConfig(**raw.get("pitch", {})), config=FitConfig(**raw.get("config", {})),
            validation_landmarks=parse(raw.get("validation_landmarks", [])))
        return calibration.to_dict()
    except (KeyError, TypeError) as exc:
        raise CalibrationError(f"Malformed landmark input: {exc}") from exc
