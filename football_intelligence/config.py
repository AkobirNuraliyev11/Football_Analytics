"""Immutable, strict, versioned configuration in human-readable JSON."""

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

from .validation import finite


@dataclass(frozen=True)
class PitchConfig:
    length_m: float = 105.0
    width_m: float = 68.0

    def __post_init__(self) -> None:
        for name in ("length_m", "width_m"):
            finite(name, getattr(self, name), minimum=0.01)


@dataclass(frozen=True)
class AnalyticsConfig:
    sprint_threshold_kmh: float = 18.0
    max_speed_kmh: float = 36.0
    smoothing_window_s: float = 0.5
    min_track_duration_s: float = 2.0
    min_sprint_duration_s: float = 1.0
    duel_distance_m: float = 1.3
    min_duel_duration_s: float = 0.5
    highlight_padding_s: float = 1.5
    max_observation_gap_s: float = 0.25

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            finite(name, value, minimum=0.0 if name == "highlight_padding_s" else 0.001)
        if self.sprint_threshold_kmh >= self.max_speed_kmh:
            raise ValueError("sprint_threshold_kmh must be less than max_speed_kmh")


@dataclass(frozen=True)
class AppConfig:
    schema_version: int = 1
    pitch: PitchConfig = field(default_factory=PitchConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("Only schema_version 1 is supported")
        if not isinstance(self.pitch, PitchConfig) or not isinstance(self.analytics, AnalyticsConfig):
            raise ValueError("pitch and analytics must be validated configuration objects")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AppConfig":
        def section(value: Any, allowed: set[str], name: str) -> dict[str, Any]:
            if not isinstance(value, dict):
                raise ValueError(f"{name} must be a JSON object")
            unknown = value.keys() - allowed
            if unknown:
                raise ValueError(f"Unknown {name} fields: {', '.join(sorted(unknown))}")
            return value

        section(raw, {"schema_version", "pitch", "analytics"}, "config")
        pitch = section(raw.get("pitch", {}), set(PitchConfig.__dataclass_fields__), "pitch")
        analytics = section(raw.get("analytics", {}), set(AnalyticsConfig.__dataclass_fields__), "analytics")
        return cls(raw.get("schema_version", 1), PitchConfig(**pitch), AnalyticsConfig(**analytics))

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"Duplicate configuration key: {key}")
                result[key] = value
            return result

        return cls.from_dict(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object))
