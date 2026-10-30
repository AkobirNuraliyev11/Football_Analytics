"""Replay provenance-checked inputs and publish synchronized Step 7 artifacts."""
from contextlib import ExitStack, closing
from fractions import Fraction
from itertools import zip_longest
import json
from pathlib import Path

from .config import AppConfig
from .ingestion import write_manifest
from .model_assets import sha256
from .tactical import TacticalEngine
from .validation import finite


def input_frames(tracks, review=None):
    """Join reviewed detections to their original frame/shot/match metadata."""
    with ExitStack() as stack:
        source = stack.enter_context(tracks.open())
        evidence = stack.enter_context((review/"quality.jsonl").open()) if review else None
        rows = zip_longest(source,evidence) if evidence else ((line,None) for line in source)
        for line, checked in rows:
            if line is None or (evidence and checked is None):
                raise ValueError("Review and track frame counts differ")
            frame = json.loads(line)
            if checked:
                quality = json.loads(checked)
                if (quality["frame_index"] != frame["frame_index"] or
                        abs(quality["timestamp_s"]-frame["timestamp_s"]) > 1e-6):
                    raise ValueError("Review and tracks are not synchronized")
                if [x["track_id"] for x in quality["detections"]] != [x["track_id"] for x in frame["detections"]]:
                    raise ValueError("Review identities differ from tracks")
                frame["detections"] = quality["detections"]
            yield frame


def build_tactics(tracks, output, *, review=None, config=None, video=None,
                  cell_m=1., sigma_m=2., rotate=False, preview_start_s=0., preview_seconds=12.):
    from .analysis import PreviewWriter
    from .tactical_render import radar_image, export_heatmaps
    import cv2
    tracks, output = Path(tracks).resolve(strict=True), Path(output)
    review = Path(review).resolve(strict=True) if review else None
    finite("preview_start_s",preview_start_s,minimum=0)
    finite("preview_seconds",preview_seconds,minimum=.04)
    paths = [tracks]
    proof = {}
    if review:
        proof = json.loads((review/"manifest.json").read_text())
        if proof.get("status") != "completed" or proof.get("tracks_sha256") != sha256(tracks):
            raise ValueError("Need completed review of these exact tracks")
        if proof.get("measurement_quality") != "experimental_estimate":
            raise ValueError("Unsupported review quality")
        reviewed_config = AppConfig.from_dict(proof["config"])
        if config is not None and config != reviewed_config:
            raise ValueError("Config must match the measurement review")
        config = reviewed_config
        paths += [review/"quality.jsonl", review/"manifest.json"]
    config = config or AppConfig()
    engine = TacticalEngine(config, experimental=review is not None, cell_m=cell_m, sigma_m=sigma_m)
    pitch = config.to_dict()["pitch"]
    if video:
        from .video import iter_frames
        video = Path(video).resolve(strict=True)
        if not proof:
            manifest = tracks.parent/"manifest.json"
            proof = json.loads(manifest.read_text()) if manifest.exists() else {}
            if proof.get("status") != "completed":
                raise ValueError("Video overlay requires completed source analysis")
        if proof.get("source_sha256") != sha256(video):
            raise ValueError("Video differs from the recorded source")
        paths.append(video)
    snapshots = {str(p): (p.stat().st_size,p.stat().st_mtime_ns,sha256(p)) for p in paths}
    output.mkdir(parents=True,exist_ok=False)
    staging = output/"partial"
    staging.mkdir()
    manifest = {"schema_version":1,"status":"running","quality":engine.grade,
        "processed_frames":0,"config":config.to_dict(),
        "input_hashes":{p:values[2] for p,values in snapshots.items()},
        "display_rotation_degrees":180 if rotate else 0,
        "preview_start_s":preview_start_s,"preview_seconds_limit":preview_seconds,
        "preview_audio":False,"preview_frames":0,
        "orientation":"canonical; user display rotation does not establish attacking direction"}
    write_manifest(output/"manifest.json",manifest)
    try:
        with ExitStack() as stack:
            records = stack.enter_context((staging/"radar.jsonl").open("x"))
            frames = stack.enter_context(closing(iter_frames(video))) if video else None
            writer = None
            preview_origin = None
            for frame in input_frames(tracks,review):
                radar = engine.update(frame)
                records.write(json.dumps(radar,allow_nan=False)+"\n")
                manifest["processed_frames"] += 1
                decoded = next(frames,None) if frames else None
                if frames and (decoded is None or decoded.frame_index != frame["frame_index"] or
                               abs(decoded.timestamp_s-frame["timestamp_s"]) > 1e-6):
                    raise ValueError("Source video and radar timestamps differ")
                t = frame["timestamp_s"]
                if preview_start_s <= t < preview_start_s+preview_seconds:
                    image = radar_image(radar,pitch,rotate=rotate)
                    if decoded is not None:
                        rgb = decoded.rgb.copy()
                        panel_width = min(rgb.shape[1]//2,600)
                        panel_height = round(image.shape[0]*panel_width/image.shape[1])
                        if panel_height > rgb.shape[0]-20:
                            panel_height = rgb.shape[0]-20
                            panel_width = round(image.shape[1]*panel_height/image.shape[0])
                        panel = cv2.resize(image,(panel_width,panel_height))
                        rgb[-panel_height-10:-10,-panel_width-10:-10] = panel
                        cv2.rectangle(rgb,(0,0),(rgb.shape[1],42),(15,24,38),-1)
                        cv2.putText(rgb,f"TACTICAL REVIEW | {engine.grade} | positions may be unavailable",
                                    (10,28),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,215,110),1)
                        image = rgb
                    if writer is None:
                        writer = stack.enter_context(closing(PreviewWriter(staging/"preview.mp4",
                            image.shape[1],image.shape[0],Fraction(25))))
                        preview_origin = t
                    writer.write(image,t-preview_origin)
                    manifest["preview_frames"] += 1
                    if manifest["preview_frames"] == 1:
                        if not cv2.imwrite(str(staging/"radar.png"),cv2.cvtColor(image,cv2.COLOR_RGB2BGR)):
                            raise OSError("Failed to write radar image")
            if not manifest["processed_frames"]:
                raise ValueError("Tactical input contains no frames")
        summary = engine.finish()
        for name,before in snapshots.items():
            path = Path(name)
            after = path.stat()
            if (after.st_size,after.st_mtime_ns,sha256(path)) != before:
                raise ValueError("Tactical input changed during processing")
        files = export_heatmaps(summary,staging,rotate=rotate)
        summary["heatmap_images"] = files
        write_manifest(staging/"occupancy.json",summary)
        artifacts = sorted(p.name for p in staging.iterdir())
        for path in staging.iterdir():
            path.replace(output/path.name)
        staging.rmdir()
        manifest.update(status="completed",measurement_status=summary["status"],artifacts=artifacts,
            coverage=summary["coverage"],preview_source_start_s=preview_origin)
        write_manifest(output/"manifest.json",manifest)
        return manifest
    except (Exception,KeyboardInterrupt) as exc:
        manifest.update(status="failed",error=str(exc) or type(exc).__name__)
        write_manifest(output/"manifest.json",manifest)
        raise
