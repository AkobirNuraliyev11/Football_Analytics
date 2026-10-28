"""Local video probing and bounded-memory decoding using presentation timestamps."""

from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterator

from .validation import integer


class VideoError(ValueError):
    """An input cannot safely supply timestamped video frames."""


def dependencies():
    try:
        import av
        import numpy as np
    except ImportError as exc:
        raise VideoError('Video support requires: python3 -m pip install -e ".[video]"') from exc
    return av, np


def local_source(path: Path) -> Path:
    path = path.expanduser().resolve(strict=True)
    if not path.is_file():
        raise VideoError("Video source must be a local regular file")
    return path


def select_stream(container, video_stream: int):
    integer("video_stream", video_stream)
    streams = container.streams.video
    if video_stream >= len(streams):
        raise VideoError(f"Video stream ordinal {video_stream} unavailable; found {len(streams)}")
    stream = streams[video_stream]
    if stream.disposition & type(stream.disposition).attached_pic:
        raise VideoError("Selected stream is cover art, not match footage")
    return stream


@dataclass(frozen=True)
class VideoMetadata:
    source: str
    video_stream: int
    stream_index: int
    codec: str
    width: int
    height: int
    time_base: str
    average_rate: str | None
    declared_frame_count: int | None
    declared_duration_s: float | None
    stream_start_s: float | None
    sample_aspect_ratio: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def probe_video(path: Path, video_stream: int = 0) -> VideoMetadata:
    av, _ = dependencies()
    path = local_source(path)
    try:
        with av.open(str(path)) as container:
            stream = select_stream(container, video_stream)
            if stream.time_base is None or stream.time_base <= 0:
                raise VideoError("Video stream has no valid time base")
            return VideoMetadata(
                str(path), video_stream, stream.index, stream.codec_context.name,
                stream.width, stream.height, str(stream.time_base),
                str(stream.average_rate) if stream.average_rate else None,
                stream.frames or None,
                float(stream.duration * stream.time_base) if stream.duration is not None else None,
                float(stream.start_time * stream.time_base) if stream.start_time is not None else None,
                str(stream.sample_aspect_ratio) if stream.sample_aspect_ratio else None)
    except av.FFmpegError as exc:
        raise VideoError(f"Could not inspect video: {exc}") from exc


class PresentationClock:
    """Validate exact rational time before converting elapsed seconds to float."""

    def __init__(self):
        self.origin: Fraction | None = None
        self.previous: Fraction | None = None

    def accept(self, pts: int | None, time_base: Fraction | None) -> tuple[float, float | None]:
        if pts is None or time_base is None or time_base <= 0:
            raise VideoError("Frame is missing a valid presentation timestamp/time base")
        current = pts * time_base
        if self.previous is not None and current <= self.previous:
            raise VideoError("Frame presentation timestamps must strictly increase")
        if self.origin is None:
            self.origin = current
        delta = float(current - self.previous) if self.previous is not None else None
        self.previous = current
        return float(current - self.origin), delta


@dataclass(frozen=True)
class DecodedFrame:
    frame_index: int
    pts: int
    time_base: Fraction
    timestamp_s: float
    delta_s: float | None
    rgb: Any

    def timing_record(self) -> dict[str, Any]:
        return {"frame_index": self.frame_index, "pts": self.pts,
                "time_base": str(self.time_base),
                "source_timestamp_s": float(self.pts * self.time_base),
                "timestamp_s": self.timestamp_s, "delta_s": self.delta_s}


def iter_frames(path: Path, video_stream: int = 0) -> Iterator[DecodedFrame]:
    """Yield native raster RGB frames. No resizing, frame dropping, or FPS resampling.

    Close the generator if stopping early (e.g. with contextlib.closing).
    Rotation/display metadata is not applied: calibration uses this native raster.
    """
    av, _ = dependencies()
    path = local_source(path)
    clock = PresentationClock()
    try:
        with av.open(str(path)) as container:
            stream = select_stream(container, video_stream)
            dimensions = None
            count = 0
            for index, frame in enumerate(container.decode(stream)):
                if frame.is_corrupt:
                    raise VideoError(f"Decoder marked frame {index} corrupt")
                current_dimensions = (frame.width, frame.height)
                if dimensions is not None and dimensions != current_dimensions:
                    raise VideoError("Raster dimensions changed; split the video before ingestion")
                dimensions = current_dimensions
                elapsed, delta = clock.accept(frame.pts, frame.time_base)
                count += 1
                yield DecodedFrame(index, frame.pts, frame.time_base, elapsed, delta,
                                   frame.to_ndarray(format="rgb24"))
            if not count:
                raise VideoError("Selected stream decoded no frames")
    except av.FFmpegError as exc:
        raise VideoError(f"Video decoding failed: {exc}") from exc
