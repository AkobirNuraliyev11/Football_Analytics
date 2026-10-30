"""Quality-gated radar and time-weighted occupancy, independent of video rendering."""
from collections import Counter
import hashlib
import json
import math

from .config import AppConfig
from .telemetry import TelemetryEngine
from .validation import finite


def gaussian_density(grid, sigma_cells):
    """Separable Gaussian, normalized per source cell to conserve boundary mass."""
    import numpy as np
    finite("sigma_cells", sigma_cells, minimum=.01)
    def kernel(size):
        delta = np.arange(size)[:, None] - np.arange(size)[None, :]
        weights = np.exp(-.5 * (delta / sigma_cells) ** 2)
        weights[abs(delta) > 4 * sigma_cells] = 0
        return weights / weights.sum(axis=0, keepdims=True)
    return kernel(grid.shape[0]) @ grid @ kernel(grid.shape[1]).T


class TacticalEngine:
    """Never interpolates missing points or joins different identity fragments.

    Only mature telemetry samples enter radar. Occupancy weights the endpoints
    of each eligible consecutive interval equally (trapezoidal integration).
    """
    def __init__(self, config=None, *, experimental=False, cell_m=1.0, sigma_m=2.0):
        import numpy as np
        self.config = config or AppConfig()
        finite("cell_m", cell_m, minimum=.5)
        finite("sigma_m", sigma_m, minimum=.1)
        self.cell_m, self.sigma_m = cell_m, sigma_m
        self.telemetry = TelemetryEngine(self.config, experimental=experimental)
        self.grade = "experimental_estimate" if experimental else "input_validated"
        self.shape = (math.ceil(self.config.pitch.width_m/cell_m),
                      math.ceil(self.config.pitch.length_m/cell_m))
        if self.shape[0] * self.shape[1] > 100000:
            raise ValueError("Occupancy grid is too large")
        self.groups = {}
        self.previous = {}
        self.statuses, self.breaks = Counter(), Counter()
        self.first_time = self.last_time = None
        self.person_samples = self.radar_samples = 0
        self.np = np

    def _groups(self, frame, dot):
        # Cross-shot end identity and team labels are not guaranteed by tracking.
        scope = {"match_id": frame["match_id"], "shot_id": frame["shot_id"],
                 "coordinate_reference_id": dot["coordinate_reference_id"]}
        identity = scope | {"type": "track", "track_id": dot["track_id"],
            "continuity_segment": dot["continuity_segment"], "team": dot["team"], "role": dot["role"]}
        identities = [identity]
        if dot["role"] in {"outfield", "goalkeeper"} and dot["team"] in {"A", "B"}:
            identities.append(scope | {"type": "team", "team": dot["team"]})
        for identity in identities:
            key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
            if key not in self.groups:
                self.groups[key] = {"identity": identity, "grid": self.np.zeros(self.shape),
                                    "observed_person_seconds": 0.0, "intervals": 0}
            yield self.groups[key]

    def _cell(self, dot):
        return (min(self.shape[0]-1, int(dot["y_m"]/self.cell_m)),
                min(self.shape[1]-1, int(dot["x_m"]/self.cell_m)))

    def update(self, frame):
        result = self.telemetry.update(frame)
        t = frame["timestamp_s"]
        if self.first_time is None:
            self.first_time = t
        dots, current = [], {}
        for item, measured in zip(frame["detections"], result["observations"]):
            if item.get("kind") != "person":
                continue
            self.person_samples += 1
            self.statuses[measured["status"]] += 1
            if measured["status"] != "measured":
                self.breaks.update(measured["reasons"])
                continue
            dot = {k: item[k] for k in ("track_id", "continuity_segment", "role",
                                        "coordinate_reference_id")}
            dot.update(item["pitch_position_candidate"])
            dot.update(team=item.get("team", "unknown"), fragment_id=measured["fragment_id"],
                       quality=self.grade)
            dots.append(dot)
            key = (frame["shot_id"], dot["track_id"], dot["fragment_id"])
            groups = list(self._groups(frame, dot))
            previous = self.previous.get(key)
            if previous is not None:
                dt = t - self.last_time
                # Telemetry already checks gaps and displacement; keep this explicit too.
                if dt <= self.config.analytics.max_observation_gap_s + 1e-9:
                    for group in groups:
                        group["grid"][self._cell(previous)] += dt / 2
                        group["grid"][self._cell(dot)] += dt / 2
                        group["observed_person_seconds"] += dt
                        group["intervals"] += 1
            current[key] = dot
        self.radar_samples += len(dots)
        self.previous, self.last_time = current, t
        return {k: result[k] for k in ("match_id", "shot_id", "frame_index", "timestamp_s")} | {
            "quality": self.grade, "positions": dots,
            "status": "available" if dots else "unavailable",
            "orientation": "canonical; attacking direction unknown", "interpolation": "none"}

    def finish(self):
        telemetry = self.telemetry.finish()
        groups = []
        for key, group in sorted(self.groups.items()):
            grid, total = group["grid"], group["observed_person_seconds"]
            smooth = gaussian_density(grid, self.sigma_m/self.cell_m)
            probability = smooth/total if total > 0 else self.np.zeros(self.shape)
            groups.append({"id": key, "identity": group["identity"],
                "observed_person_seconds": total, "intervals": group["intervals"],
                "status": "available" if total > 0 else "no_continuous_intervals",
                "occupancy_seconds": grid.tolist(), "smoothed_seconds": smooth.tolist(),
                "probability_mass": probability.tolist()})
        return {"schema_version": 1, "quality": self.grade,
            "status": "available" if any(g["observed_person_seconds"] > 0 for g in groups) else "unavailable",
            "pitch": self.config.to_dict()["pitch"], "cell_m": self.cell_m, "sigma_m": self.sigma_m,
            "grid_shape": list(self.shape), "groups": groups,
            "coverage": {"person_samples": self.person_samples, "radar_samples": self.radar_samples,
                "sample_fraction": self.radar_samples/self.person_samples if self.person_samples else None,
                "input_span_s": self.last_time-self.first_time if self.first_time is not None else 0,
                "statuses": dict(self.statuses), "reasons": dict(self.breaks)},
            "telemetry": telemetry,
            "scope": "Observed occupancy only; not pitch control, full-match totals, or verified athletes",
            "time_weighting": "Half interval duration at each eligible endpoint; no gaps, tails, or warmup"}
