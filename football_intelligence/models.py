"""Per-frame contracts. Track IDs are scoped to a match and camera shot."""

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from .config import PitchConfig
from .validation import finite, identifier, integer


class Role(str, Enum):
    OUTFIELD = "outfield"
    GOALKEEPER = "goalkeeper"
    OFFICIAL = "official"
    UNKNOWN = "unknown"


class Team(str, Enum):
    A = "A"
    B = "B"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PixelPoint:
    x: float
    y: float

    def __post_init__(self) -> None:
        finite("pixel x", self.x)
        finite("pixel y", self.y)


@dataclass(frozen=True)
class PitchPoint:
    x_m: float
    y_m: float

    def __post_init__(self) -> None:
        finite("pitch x", self.x_m)
        finite("pitch y", self.y_m)

    def is_on_pitch(self, pitch: PitchConfig) -> bool:
        # Keep out-of-bounds projections for diagnostics; never clamp them onto a line.
        return 0 <= self.x_m <= pitch.length_m and 0 <= self.y_m <= pitch.width_m


@dataclass(frozen=True)
class BoundingBox:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            finite(name, value)
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("Bounding box must have positive width and height")

    @property
    def foot_anchor(self) -> PixelPoint:
        return PixelPoint((self.x_min + self.x_max) / 2, self.y_max)


@dataclass(frozen=True)
class AthleteObservation:
    match_id: str
    shot_id: int
    track_id: int
    frame_index: int
    timestamp_s: float
    bbox: BoundingBox
    detection_confidence: float
    team: Team = Team.UNKNOWN
    role: Role = Role.UNKNOWN
    pitch_position: PitchPoint | None = None
    calibration_id: str | None = None
    ground_contact_reliable: bool = False

    def __post_init__(self) -> None:
        identifier("match_id", self.match_id)
        for name in ("shot_id", "track_id", "frame_index"):
            integer(name, getattr(self, name))
        finite("timestamp_s", self.timestamp_s, minimum=0)
        finite("detection_confidence", self.detection_confidence, minimum=0)
        if self.detection_confidence > 1:
            raise ValueError("detection_confidence must be <= 1")
        if not isinstance(self.bbox, BoundingBox):
            raise ValueError("bbox must be a BoundingBox")
        if not isinstance(self.team, Team) or not isinstance(self.role, Role):
            raise ValueError("team and role must be enum members")
        if type(self.ground_contact_reliable) is not bool:
            raise ValueError("ground_contact_reliable must be boolean")
        if self.role == Role.OFFICIAL and self.team != Team.UNKNOWN:
            raise ValueError("Officials cannot belong to a playing team")
        if self.pitch_position is not None and not isinstance(self.pitch_position, PitchPoint):
            raise ValueError("pitch_position must be a PitchPoint")
        if self.calibration_id is not None:
            identifier("calibration_id", self.calibration_id)
        if self.pitch_position is not None and self.calibration_id is None:
            raise ValueError("Projected coordinates require calibration provenance")

    @property
    def track_key(self) -> tuple[str, int, int]:
        return self.match_id, self.shot_id, self.track_id

    def is_planar_sample_eligible(self, pitch: PitchConfig) -> bool:
        """Necessary per-sample checks; temporal and calibration quality gates come later."""
        return (self.ground_contact_reliable and self.pitch_position is not None
                and self.pitch_position.is_on_pitch(pitch))

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["team"] = self.team.value
        result["role"] = self.role.value
        return result
