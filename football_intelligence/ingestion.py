"""Stream frame timing to JSONL and atomically publish a job status manifest."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from .shots import ShotConfig, ShotDetector
from .video import VideoError, dependencies, iter_frames, local_source, probe_video


def write_manifest(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def ingest_video(source: Path, output: Path, *, match_id: str,
                 video_stream: int = 0, shot_config: ShotConfig | None = None) -> dict:
    from .validation import identifier

    identifier("match_id", match_id)
    config = shot_config or ShotConfig()
    source = local_source(source)
    metadata = probe_video(source, video_stream)
    av, np = dependencies()
    # Refuse existing output directories: never overwrite previous runs or source files.
    output.mkdir(parents=True, exist_ok=False)
    manifest_path = output / "manifest.json"
    manifest = {"schema_version": 1, "job_id": str(uuid.uuid4()), "match_id": match_id,
                "status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
                "video": metadata.to_dict(), "shot_config": asdict(config),
                "decoder": {"pyav": av.__version__, "numpy": np.__version__},
                "coordinate_space": "native_unrotated_raster",
                "timestamp_origin": "first_decoded_frame",
                "frame_records": None, "decoded_frames": 0}
    write_manifest(manifest_path, manifest)
    try:
        before = source.stat()
        digest = hashlib.sha256()
        with source.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        manifest["source_sha256"] = digest.hexdigest()
        detector = ShotDetector(config)
        min_delta = max_delta = None
        with (output / "frames.partial.jsonl").open("x", encoding="utf-8") as handle:
            for frame in iter_frames(source, video_stream):
                record = frame.timing_record() | detector.update(frame)
                handle.write(json.dumps(record, allow_nan=False) + "\n")
                manifest["decoded_frames"] += 1
                if frame.delta_s is not None:
                    min_delta = min(min_delta, frame.delta_s) if min_delta is not None else frame.delta_s
                    max_delta = max(max_delta, frame.delta_s) if max_delta is not None else frame.delta_s
                if frame.frame_index == 0:
                    manifest["source_origin_s"] = record["source_timestamp_s"]
                manifest["last_frame_timestamp_s"] = frame.timestamp_s
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise VideoError("Source changed during ingestion; output cannot be trusted")
        (output / "frames.partial.jsonl").replace(output / "frames.jsonl")
        manifest.update(status="completed", frame_records="frames.jsonl",
                        shot_count=detector.shot_id + 1,
                        min_frame_interval_s=min_delta, max_frame_interval_s=max_delta,
                        completed_at=datetime.now(timezone.utc).isoformat())
        write_manifest(manifest_path, manifest)
        return manifest
    except (Exception, KeyboardInterrupt) as exc:
        manifest.update(status="failed", error=str(exc) or type(exc).__name__)
        write_manifest(manifest_path, manifest)
        raise
