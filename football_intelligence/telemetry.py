"""Conservative, timestamp-driven physical measurements on continuous track fragments.

This module consumes evidence; it cannot verify calibration or detect foot contact.
Missing evidence produces null measurements, never an assumed stationary athlete.
"""
from collections import Counter, deque
from dataclasses import dataclass, field
import math

from .config import AppConfig
from .models import PitchPoint
from .validation import finite, identifier, integer


@dataclass
class Fragment:
    fragment_id: int
    key: tuple
    identity: tuple
    start: float
    last: float
    position: PitchPoint
    velocities: deque = field(default_factory=deque)
    distance: float = 0.0
    top_speed: float = 0.0
    sprint_start: float | None = None
    sprint_peak: float = 0.0
    sprints: list = field(default_factory=list)


class TelemetryEngine:
    def __init__(self, config=None):
        self.config = config or AppConfig()
        self.active = {}
        self.fragments = []
        self.rejections = Counter()
        self.last_time = self.last_frame = self.last_shot = self.match_id = None
        self.next_fragment = 1
        self.frames = self.observations = self.measured = self.discarded = 0
        self.closed = False

    def _reasons(self, frame, item):
        reasons = []
        if item.get("kind") != "person":
            return ["non_person"], None
        if item.get("role") not in {"outfield", "goalkeeper", "official"}:
            reasons.append("role_unknown")
        if item.get("confirmed") is not True:
            reasons.append("unconfirmed_track")
        if item.get("continuity_safe") is not True or item.get("measurement_link_eligible") is not True:
            reasons.append("uncertain_association")
        if item.get("classification_conflict") is not False or item.get("team_changed") is not False:
            reasons.append("classification_discontinuity")
        if frame.get("calibration_status") != "validated":
            reasons.append("calibration_unvalidated")
        for name in ("calibration_id", "coordinate_reference_id"):
            if not isinstance(item.get(name), str) or not item[name].strip():
                reasons.append("missing_" + name)
        if item.get("ground_contact_reliable") is not True:
            reasons.append("ground_contact_unverified")
        if item.get("projection_state") != "validated_ground_position":
            reasons.append("projection_unvalidated")
        raw = item.get("pitch_position_candidate")
        point = None
        if raw is None:
            reasons.append("position_unavailable")
        else:
            if not isinstance(raw, dict) or set(raw) != {"x_m", "y_m"}:
                raise ValueError("Pitch position must contain x_m and y_m")
            point = PitchPoint(**raw)
            if not point.is_on_pitch(self.config.pitch):
                reasons.append("outside_pitch")
        return reasons, point

    def _end_sprint(self, state, reason):
        if state.sprint_start is not None:
            duration = state.last - state.sprint_start
            if duration + 1e-9 >= self.config.analytics.min_sprint_duration_s:
                state.sprints.append({"start_s": state.sprint_start, "end_s": state.last,
                    "duration_s": duration, "peak_speed_kmh": state.sprint_peak,
                    "end_reason": reason, "truncated": reason != "below_threshold"})
            state.sprint_start = None
            state.sprint_peak = 0.0

    def _mature(self, state):
        return state.last - state.start + 1e-9 >= self.config.analytics.min_track_duration_s

    def _finish(self, key, reason):
        state = self.active.pop(key, None)
        if state is None:
            return
        self._end_sprint(state, reason)
        if not self._mature(state):
            self.discarded += 1
            return
        continuity, team, role, reference = state.identity
        self.fragments.append({"fragment_id": state.fragment_id,
            "match_id": key[0], "shot_id": key[1], "track_id": key[2],
            "continuity_segment": continuity, "team": team, "role": role,
            "coordinate_reference_id": reference, "start_s": state.start, "end_s": state.last,
            "observed_duration_s": state.last-state.start, "observed_distance_m": state.distance,
            "top_speed_kmh": state.top_speed, "sprint_count": len(state.sprints),
            "sprints": state.sprints, "end_reason": reason})

    def update(self, frame):
        if self.closed:
            raise ValueError("Telemetry engine has already finished")
        t, index, shot, match = (frame[k] for k in ("timestamp_s", "frame_index", "shot_id", "match_id"))
        finite("timestamp_s", t, minimum=0)
        integer("frame_index", index)
        integer("shot_id", shot)
        identifier("match_id", match)
        if self.last_time is not None and (t <= self.last_time or index <= self.last_frame or shot < self.last_shot):
            raise ValueError("Frame indices/timestamps must increase and shots cannot go backwards")
        if self.match_id is not None and match != self.match_id:
            raise ValueError("A telemetry run must contain exactly one match")
        items = frame["detections"]
        if not isinstance(items, list):
            raise ValueError("detections must be a list")
        seen = set()
        for item in items:
            integer("track_id", item["track_id"])
            if item["track_id"] in seen:
                raise ValueError("Duplicate track in frame")
            seen.add(item["track_id"])
        for key in list(self.active):
            if key[1] != shot:
                self._finish(key, "shot_change")
            elif key[2] not in seen:
                self._finish(key, "missing_observation")
        self.last_time, self.last_frame, self.last_shot, self.match_id = t, index, shot, match
        self.frames += 1
        output = []
        cfg = self.config.analytics
        for item in items:
            key = match, shot, item["track_id"]
            reasons, point = self._reasons(frame, item)
            result = {"track_id": key[2], "fragment_id": None, "status": "withheld",
                "reasons": reasons, "speed_kmh": None, "observed_distance_m": None,
                "observed_duration_s": None, "sprint_count": None, "sprinting": None}
            if item.get("kind") == "person":
                self.observations += 1
            if reasons:
                self._finish(key, reasons[0])
                if item.get("kind") == "person":
                    self.rejections.update(reasons)
                output.append(result)
                continue
            integer("continuity_segment", item.get("continuity_segment"))
            identity = (item["continuity_segment"], item.get("team", "unknown"), item["role"],
                        item["coordinate_reference_id"])
            state = self.active.get(key)
            boundary = None
            if state is not None:
                dt = t - state.last
                if state.identity != identity:
                    boundary = "identity_or_reference_change"
                elif dt > cfg.max_observation_gap_s + 1e-9:
                    boundary = "observation_gap"
                elif math.hypot(point.x_m-state.position.x_m, point.y_m-state.position.y_m) / dt * 3.6 > cfg.max_speed_kmh + 1e-9:
                    boundary = "implausible_displacement"
                if boundary:
                    self._finish(key, boundary)
                    self.rejections[boundary] += 1
                    state = None
                    # Do not seed from a suspected teleport: the next good sample must restart.
                    if boundary == "implausible_displacement":
                        result["reasons"] = [boundary]
                        output.append(result)
                        continue
            if state is None:
                state = Fragment(self.next_fragment, key, identity, t, t, point)
                self.next_fragment += 1
                self.active[key] = state
                result.update(fragment_id=state.fragment_id, status="warming_up",
                              reasons=[boundary or "first_eligible_sample"])
                output.append(result)
                continue
            dt = t-state.last
            vx, vy = (point.x_m-state.position.x_m)/dt, (point.y_m-state.position.y_m)/dt
            state.velocities.append((state.last, t, vx, vy))
            cutoff = t-cfg.smoothing_window_s
            while state.velocities and state.velocities[0][1] <= cutoff:
                state.velocities.popleft()
            # Integrate each interval's overlap with the time window, not its frame count.
            wx = wy = duration = 0.0
            for start, end, x, y in state.velocities:
                weight = end-max(start, cutoff)
                wx += x*weight
                wy += y*weight
                duration += weight
            speed = math.hypot(wx/duration, wy/duration)*3.6
            if speed > cfg.sprint_threshold_kmh + 1e-9:
                if state.sprint_start is None:
                    state.sprint_start = state.last
                state.sprint_peak = max(state.sprint_peak, speed)
            else:
                self._end_sprint(state, "below_threshold")
            state.distance += speed/3.6*dt
            state.top_speed = max(state.top_speed, speed)
            state.last, state.position = t, point
            mature = self._mature(state)
            result.update(fragment_id=state.fragment_id, status="measured" if mature else "warming_up",
                          reasons=[] if mature else ["short_track"])
            if mature:
                sprinting = (state.sprint_start is not None and
                    t-state.sprint_start+1e-9 >= cfg.min_sprint_duration_s)
                result.update(speed_kmh=speed, observed_distance_m=state.distance,
                    observed_duration_s=t-state.start, sprint_count=len(state.sprints)+int(sprinting),
                    sprinting=sprinting)
                self.measured += 1
            output.append(result)
        return {"match_id": match, "shot_id": shot, "frame_index": index, "timestamp_s": t,
                "observations": output}

    def finish(self):
        for key in list(self.active):
            self._finish(key, "end_of_input")
        self.closed = True
        return {"schema_version": 1, "status": "available" if self.fragments else "unavailable",
            "config": self.config.to_dict(), "processed_frames": self.frames,
            "person_observations": self.observations, "measured_observations": self.measured,
            "measured_observation_fraction": self.measured/self.observations if self.observations else None,
            "rejection_counts": dict(self.rejections), "discarded_short_fragments": self.discarded,
            "fragments": self.fragments,
            "scope": "Observed continuous fragments, not verified athletes or full-match totals",
            "quality": "Input quality flags are required assertions, not independently verified here",
            "smoothing": "Causal time-weighted mean velocity; distance integrates its magnitude"}
