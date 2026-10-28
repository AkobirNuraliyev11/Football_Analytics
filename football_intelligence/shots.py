"""Conservative segment boundaries for later tracking/calibration resets."""

from dataclasses import dataclass

from .validation import finite
from .video import DecodedFrame, dependencies


@dataclass(frozen=True)
class ShotConfig:
    cut_threshold: float = 0.30
    max_gap_s: float = 0.25

    def __post_init__(self):
        finite("cut_threshold", self.cut_threshold, minimum=0.001)
        if self.cut_threshold > 1:
            raise ValueError("cut_threshold must be <= 1")
        finite("max_gap_s", self.max_gap_s, minimum=0.001)


class ShotDetector:
    """RGB thumbnail mean absolute difference; candidates, not verified camera cuts."""

    def __init__(self, config: ShotConfig):
        self.config = config
        self.previous = None
        self.shot_id = 0

    def update(self, frame: DecodedFrame) -> dict:
        _, np = dependencies()
        # Fixed 64x36 sample grid keeps costs independent of native resolution.
        rows = np.linspace(0, frame.rgb.shape[0] - 1, 36).astype(int)
        cols = np.linspace(0, frame.rgb.shape[1] - 1, 64).astype(int)
        thumbnail = frame.rgb[rows[:, None], cols].astype(np.float32)
        score = (float(np.mean(np.abs(thumbnail - self.previous))) / 255.0
                 if self.previous is not None else 0.0)
        reasons = []
        if self.previous is None:
            reasons.append("start")
        else:
            if score >= self.config.cut_threshold:
                reasons.append("candidate_cut")
            if frame.delta_s is not None and frame.delta_s > self.config.max_gap_s:
                reasons.append("timestamp_gap")
            if reasons:
                self.shot_id += 1
        self.previous = thumbnail
        return {"shot_id": self.shot_id, "boundary_reasons": reasons,
                "cut_score": score}
