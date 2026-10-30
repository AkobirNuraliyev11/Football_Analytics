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
    download = commands.add_parser("download-models", help="Download published football detection and pitch models")
    download.add_argument("--model-dir", type=Path, default=Path("data/models"))
    analyze = commands.add_parser("analyze-video", help="Automatically detect, track and fit pitch geometry")
    analyze.add_argument("path", type=Path)
    analyze.add_argument("--output", type=Path, required=True)
    analyze.add_argument("--match-id", required=True)
    analyze.add_argument("--model-dir", type=Path, default=Path("data/models"))
    analyze.add_argument("--device", default="cpu")
    analyze.add_argument("--max-frames", type=int)
    analyze.add_argument("--pitch-every", type=int, default=10)
    analyze.add_argument("--config", type=Path)
    telemetry = commands.add_parser("compute-telemetry", help="Compute quality-gated telemetry from frame JSONL")
    telemetry.add_argument("path", type=Path)
    telemetry.add_argument("--output", type=Path, required=True)
    telemetry.add_argument("--config", type=Path)
    review = commands.add_parser("review-measurements", help="Experimental midfield estimates with visible-paint and camera checks")
    review.add_argument("path",type=Path)
    review.add_argument("--analysis",type=Path,required=True)
    review.add_argument("--tracks",type=Path)
    review.add_argument("--output",type=Path,required=True)
    review.add_argument("--max-frames",type=int)
    pose_download=commands.add_parser("download-pose-model",help="Download the pinned optional ankle model")
    pose_download.add_argument("--model-dir",type=Path,default=Path("data/models"))
    feet=commands.add_parser("review-feet",help="Compare experimental pose-guided feet with saved box-anchor estimates")
    feet.add_argument("path",type=Path)
    feet.add_argument("--geometry",type=Path,required=True)
    feet.add_argument("--tracks",type=Path,required=True)
    feet.add_argument("--output",type=Path,required=True)
    feet.add_argument("--pose-model",type=Path,default=Path("data/models/yolo11n-pose.pt"))
    feet.add_argument("--start-s",type=float,default=0)
    feet.add_argument("--max-frames",type=int)
    feet.add_argument("--allow-ankle-proxy",action="store_true",help="Experimental current-ankle anchor with a recently observed shoe offset")
    tactics=commands.add_parser("build-tactics",help="Export quality-gated radar and observed-occupancy heatmaps")
    tactics.add_argument("path",type=Path,help="Saved tracks JSONL")
    tactics.add_argument("--output",type=Path,required=True)
    tactics.add_argument("--review",type=Path,help="Explicit experimental measurement-review directory")
    tactics.add_argument("--config",type=Path)
    tactics.add_argument("--video",type=Path,help="Exact source video for synchronized radar overlay")
    tactics.add_argument("--cell-m",type=float,default=1.)
    tactics.add_argument("--sigma-m",type=float,default=2.)
    tactics.add_argument("--rotate",action="store_true",help="Rotate display 180 degrees; stored coordinates unchanged")
    tactics.add_argument("--preview-start-s",type=float,default=0.)
    tactics.add_argument("--preview-seconds",type=float,default=12.)
    args = parser.parse_args(argv)
    try:
        if args.command == "build-tactics":
            from .tactical_io import build_tactics
            result=build_tactics(args.path,args.output,review=args.review,
                config=AppConfig.load(args.config) if args.config else None,video=args.video,
                cell_m=args.cell_m,sigma_m=args.sigma_m,rotate=args.rotate,
                preview_start_s=args.preview_start_s,preview_seconds=args.preview_seconds)
        elif args.command == "download-pose-model":
            from .feet import download_pose_model
            result=download_pose_model(args.model_dir)
        elif args.command == "review-feet":
            from .foot_review import review_feet
            result=review_feet(args.path,args.geometry,args.tracks,args.output,pose_model=args.pose_model,
                               start_s=args.start_s,max_frames=args.max_frames,allow_ankle_proxy=args.allow_ankle_proxy)
        elif args.command == "review-measurements":
            from .real_measurements import estimate_video
            result=estimate_video(args.path,args.analysis,args.output,tracks=args.tracks,max_frames=args.max_frames)
        elif args.command == "compute-telemetry":
            from .telemetry_io import compute_telemetry
            result = compute_telemetry(args.path,args.output,
                                      config=AppConfig.load(args.config) if args.config else AppConfig())
        elif args.command == "download-models":
            from .model_assets import download_models
            result = download_models(args.model_dir)
        elif args.command == "analyze-video":
            from .analysis import analyze_video
            result = analyze_video(args.path,args.output,match_id=args.match_id,model_dir=args.model_dir,
                                   device=args.device,max_frames=args.max_frames,pitch_every=args.pitch_every,
                                   config=AppConfig.load(args.config) if args.config else AppConfig())
        elif args.command == "calibrate-pitch":
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
    except (OSError, ValueError, KeyError, TypeError) as exc:
        label = ("Configuration error" if args.command in {"default-config", "validate-config"}
                 else "Calibration error" if args.command == "calibrate-pitch"
                 else "Telemetry error" if args.command == "compute-telemetry" else "Video error")
        print(f"{label}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0
