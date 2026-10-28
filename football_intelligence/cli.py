"""Configuration and local video ingestion commands."""

import argparse
import json
from pathlib import Path
import sys

from .config import AppConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Football Intelligence project foundation")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("default-config", help="Print default configuration as JSON")
    validate = commands.add_parser("validate-config", help="Validate and print effective configuration")
    validate.add_argument("path", type=Path)
    probe = commands.add_parser("probe-video", help="Inspect a local video stream")
    probe.add_argument("path", type=Path)
    probe.add_argument("--video-stream", type=int, default=0)
    ingest = commands.add_parser("ingest-video", help="Decode video and write timing/shot records")
    ingest.add_argument("path", type=Path)
    ingest.add_argument("--output", type=Path, required=True)
    ingest.add_argument("--match-id", required=True)
    ingest.add_argument("--video-stream", type=int, default=0)
    ingest.add_argument("--cut-threshold", type=float, default=0.30)
    ingest.add_argument("--max-gap-s", type=float, default=0.25)
    calibrate = commands.add_parser("calibrate-pitch", help="Fit pixel-to-meter mapping from landmark JSON")
    calibrate.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "calibrate-pitch":
            from .calibration import fit_landmark_file
            result = fit_landmark_file(args.path)
        elif args.command == "probe-video":
            from .video import probe_video
            result = probe_video(args.path, args.video_stream).to_dict()
        elif args.command == "ingest-video":
            from .ingestion import ingest_video
            from .shots import ShotConfig
            result = ingest_video(args.path, args.output, match_id=args.match_id,
                                  video_stream=args.video_stream,
                                  shot_config=ShotConfig(args.cut_threshold, args.max_gap_s))
        else:
            config = AppConfig.load(args.path) if args.command == "validate-config" else AppConfig()
            result = config.to_dict()
    except (OSError, ValueError) as exc:
        label = ("Configuration error" if args.command in {"default-config", "validate-config"}
                 else "Calibration error" if args.command == "calibrate-pitch" else "Video error")
        print(f"{label}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0
