"""Review-only real-video estimates; strict validated telemetry is never overwritten."""
from contextlib import closing
from fractions import Fraction
import json
from pathlib import Path

from .analysis import PreviewWriter, annotate
from .calibration import CalibrationError
from .config import AppConfig, PitchConfig
from .ingestion import write_manifest
from .measurement_quality import refine_midfield, stabilize_camera, foot_candidate
from .model_assets import sha256
from .telemetry import TelemetryEngine
from .validation import integer
from .video import iter_frames, probe_video


def estimate_video(source, analysis, output, *, tracks=None, max_frames=None):
    import cv2
    source,analysis,output=Path(source),Path(analysis),Path(output)
    if max_frames is not None: integer("max_frames",max_frames,minimum=1)
    manifest=json.loads((analysis/"manifest.json").read_text())
    source_before=source.stat()
    source_hash=sha256(source)
    if manifest["status"]!="completed" or manifest["source_sha256"]!=source_hash:
        raise ValueError("Review needs completed analysis and the exact source video")
    tracks=Path(tracks) if tracks else analysis/"tracks.jsonl"
    tracks_before=tracks.stat()
    if tracks.resolve()!=(analysis/"tracks.jsonl").resolve():
        review=json.loads((tracks.parent/"review.json").read_text())
        if review["source_sha256"]!=source_hash or review["frames"]!=manifest["processed_frames"]:
            raise ValueError("Replacement tracks do not match the analysis source/length")
    config=AppConfig(pitch=PitchConfig(**manifest["pitch"]))
    engine=TelemetryEngine(config,experimental=True)
    calibrations={c["frame_index"]:c for c in map(json.loads,(analysis/"calibrations.jsonl").read_text().splitlines())}
    meta=probe_video(source)
    output.mkdir(parents=True,exist_ok=False)
    job={"status":"running","source_sha256":source_hash,"tracks_sha256":sha256(tracks),
         "calibrations_sha256":sha256(analysis/"calibrations.jsonl"),"processed_frames":0,
         "measurement_quality":"experimental_estimate","config":config.to_dict(),
         "ground_contact_verified":False,"max_frames":max_frames}
    write_manifest(output/"manifest.json",job)
    previous=previous_items=previous_fit=previous_shot=None
    try:
        with tracks.open() as cached, closing(iter_frames(source)) as frames, \
             (output/"estimates.partial.jsonl").open("x") as values, \
             (output/"quality.partial.jsonl").open("x") as quality, \
             closing(PreviewWriter(output/"preview.partial.mp4",meta.width,meta.height,
                                   Fraction(meta.average_rate or "25"))) as writer:
            for line,frame in zip(cached,frames):
                old=json.loads(line)
                if old["frame_index"]!=frame.frame_index or abs(old["timestamp_s"]-frame.timestamp_s)>1e-6:
                    raise ValueError("Video and saved detections are not synchronized")
                items=old["detections"]
                cal=calibrations.get(frame.frame_index)
                fit=None;reason=None
                try:
                    consecutive=(previous_fit is not None and previous_shot==old["shot_id"]
                        and frame.frame_index==previous.frame_index+1
                        and frame.timestamp_s-previous.timestamp_s<=.12)
                    if cal is not None and (cal["width"],cal["height"],cal["shot_id"],cal["match_id"])!=(meta.width,meta.height,old["shot_id"],old["match_id"]):
                        raise ValueError("Calibration scope mismatch")
                    seeds=[("model",cal["matrix"])] if cal else []
                    if consecutive: seeds.append(("previous_checked_frame",previous_fit.matrix))
                    failure="No seed pitch fit"
                    for origin,seed in seeds:
                        try:
                            fit=refine_midfield(frame.rgb,seed,items,config.pitch)
                            fit.evidence["seed_origin"]=origin
                            break
                        except CalibrationError as exc:
                            failure=str(exc)
                    if fit is None: raise CalibrationError(failure)
                    if consecutive:
                        fit=stabilize_camera(previous.rgb,frame.rgb,previous_fit,fit,previous_items,items,config.pitch)
                    else:
                        fit.evidence["camera_stable"]=False
                except CalibrationError as exc:
                    fit=None;reason=str(exc)
                prepared=[]
                for original in items:
                    item=dict(original)
                    item.pop("telemetry",None)
                    evidence={};candidate=None;foot_reason=None
                    if fit and item["kind"]=="person":
                        candidate,foot_reason=foot_candidate(frame.rgb,item,items,fit,config.pitch)
                        # Abrupt body-height change can indicate clipping, crouching or a jump.
                        last=next((p for p in (previous_items or []) if p["track_id"]==item["track_id"]),None)
                        if candidate and last and previous_shot==old["shot_id"]:
                            b,p=item["bbox"],last["bbox"]
                            if abs((b["y_max"]-b["y_min"])/(p["y_max"]-p["y_min"])-1)>.15:
                                candidate=None;foot_reason="body_height_discontinuity"
                    if candidate:
                        evidence=fit.evidence|candidate
                        item.update(pitch_position_candidate=candidate["position"],
                                    coordinate_reference_id=f"midfield-estimate-shot-{old['shot_id']}",
                                    calibration_id=f"paint-frame-{frame.frame_index}")
                    else:
                        item["pitch_position_candidate"]=None
                    item["measurement_evidence"]=evidence
                    item["measurement_rejection"]=foot_reason or reason
                    prepared.append(item)
                measured=engine.update(old|{"detections":prepared})
                for item,result in zip(prepared,measured["observations"]):
                    item["telemetry"]=result
                values.write(json.dumps(measured,allow_nan=False)+"\n")
                quality.write(json.dumps({"frame_index":frame.frame_index,"timestamp_s":frame.timestamp_s,
                    "geometry":fit.evidence if fit else None,"geometry_rejection":reason,
                    "matrix":fit.matrix.tolist() if fit else None,"detections":prepared},allow_nan=False)+"\n")
                preview=annotate(frame.rgb,prepared,None,frame.frame_index,old["shot_id"])
                cv2.rectangle(preview,(0,0),(meta.width,56),(20,27,40),-1)
                cv2.putText(preview,"EXPERIMENTAL ESTIMATES | center-circle area only | ground contact not verified",
                            (15,23),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,205,100),2)
                cv2.putText(preview,f"Frame {frame.frame_index} | " + ("paint checked" if fit else "geometry unavailable"),
                            (15,46),cv2.FONT_HERSHEY_SIMPLEX,.5,(240,240,240),1)
                writer.write(preview,frame.timestamp_s)
                previous,previous_items,previous_fit,previous_shot=frame,items,fit,old["shot_id"]
                job["processed_frames"]+=1
                if max_frames and job["processed_frames"]>=max_frames: break
        expected=min(manifest["processed_frames"],max_frames or manifest["processed_frames"])
        if job["processed_frames"]!=expected: raise ValueError("Incomplete source or track records")
        for path,before in [(source,source_before),(tracks,tracks_before)]:
            after=path.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                raise ValueError("Review input changed during processing")
        summary=engine.finish()
        write_manifest(output/"summary.partial.json",summary)
        artifacts=["estimates.jsonl","quality.jsonl","summary.json","preview.mp4"]
        for name in artifacts:
            stem,suffix=name.rsplit(".",1)
            (output/f"{stem}.partial.{suffix}").replace(output/name)
        job.update(status="completed",measurement_status=summary["status"],artifacts=artifacts)
        write_manifest(output/"manifest.json",job)
        return job
    except (Exception,KeyboardInterrupt) as exc:
        job.update(status="failed",error=str(exc) or type(exc).__name__)
        write_manifest(output/"manifest.json",job)
        raise
