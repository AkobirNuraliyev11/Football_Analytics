"""Replay saved frame records without decoding video or downloading models."""
import hashlib
import json
from pathlib import Path

from .ingestion import write_manifest
from .telemetry import TelemetryEngine


def compute_telemetry(source: Path, output: Path, *, config=None):
    source = source.resolve(strict=True)
    if not source.is_file():
        raise ValueError("Telemetry input must be a JSONL file")
    engine = TelemetryEngine(config)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": 1, "status": "running", "source": str(source),
                "processed_frames": 0, "config": engine.config.to_dict()}
    write_manifest(output/"manifest.json", manifest)
    try:
        before = source.stat()
        digest = hashlib.sha256()
        with source.open("rb") as stream, (output/"telemetry.partial.jsonl").open("x") as target:
            for line in stream:
                digest.update(line)
                result = engine.update(json.loads(line))
                target.write(json.dumps(result, allow_nan=False)+"\n")
                manifest["processed_frames"] += 1
        if not manifest["processed_frames"]:
            raise ValueError("Telemetry input contains no frames")
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("Telemetry input changed during processing")
        summary = engine.finish()
        write_manifest(output/"telemetry-summary.partial.json", summary)
        for name in ("telemetry.jsonl", "telemetry-summary.json"):
            stem, suffix = name.rsplit(".", 1)
            (output/f"{stem}.partial.{suffix}").replace(output/name)
        manifest.update(status="completed", source_sha256=digest.hexdigest(),
            measurement_status=summary["status"], artifacts=["telemetry.jsonl", "telemetry-summary.json"])
        write_manifest(output/"manifest.json", manifest)
        return manifest
    except (Exception, KeyboardInterrupt) as exc:
        manifest.update(status="failed", error=str(exc) or type(exc).__name__)
        write_manifest(output/"manifest.json", manifest)
        raise
