"""Compare pose-guided shoes with box anchors using identical saved geometry."""
from collections import Counter
from contextlib import closing
from fractions import Fraction
import json
from pathlib import Path

from .analysis import PreviewWriter,annotate
from .config import AppConfig
from .feet import AnkleDetector,FootLocalizer
from .ingestion import write_manifest
from .measurement_quality import PaintFit,foot_candidate
from .model_assets import sha256
from .telemetry import TelemetryEngine
from .validation import finite,integer
from .video import iter_frames,probe_video


def review_feet(source,geometry,tracks,output,*,pose_model,start_s=0,max_frames=None,detector=None,allow_ankle_proxy=False):
    import cv2
    import numpy as np
    source,geometry,tracks,output=map(Path,(source,geometry,tracks,output))
    finite("start_s",start_s,minimum=0)
    if max_frames is not None:integer("max_frames",max_frames,minimum=1)
    manifest=json.loads((geometry/"manifest.json").read_text())
    if manifest["status"]!="completed" or sha256(source)!=manifest["source_sha256"] or sha256(tracks)!=manifest["tracks_sha256"]:
        raise ValueError("Foot review requires exact source, tracks, and completed geometry")
    quality_path=geometry/"quality.jsonl"
    before={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in [source,tracks,quality_path]}
    config=AppConfig.from_dict(manifest["config"])
    detector=detector or AnkleDetector(pose_model)
    localizer=FootLocalizer(allow_ankle_proxy=allow_ankle_proxy)
    baseline,experimental=TelemetryEngine(config,experimental=True),TelemetryEngine(config,experimental=True)
    meta=probe_video(source)
    output.mkdir(parents=True,exist_ok=False)
    job={"status":"running","source_sha256":manifest["source_sha256"],"tracks_sha256":manifest["tracks_sha256"],
         "quality_sha256":sha256(quality_path),"pose_sha256":detector.fingerprint,"processed_frames":0,
         "start_s":start_s,"max_frames":max_frames,"ground_contact_verified":False,
         "measurement_quality":"experimental_pose_estimate","allow_ankle_proxy":allow_ankle_proxy}
    write_manifest(output/"manifest.json",job)
    statuses=Counter();rejections=Counter();previous_boxes={};previous_shot=None
    try:
        with quality_path.open() as qfile,tracks.open() as tfile,closing(iter_frames(source)) as frames, \
             (output/"feet.partial.jsonl").open("x") as audit, \
             closing(PreviewWriter(output/"preview.partial.mp4",meta.width,meta.height,Fraction(meta.average_rate or "25"))) as writer:
            for qline,tline,frame in zip(qfile,tfile,frames):
                q,old=json.loads(qline),json.loads(tline)
                if q["frame_index"]!=frame.frame_index or old["frame_index"]!=frame.frame_index or abs(q["timestamp_s"]-frame.timestamp_s)>1e-6 or abs(old["timestamp_s"]-frame.timestamp_s)>1e-6:
                    raise ValueError("Foot-review inputs are not synchronized")
                if frame.timestamp_s<start_s:continue
                if job["processed_frames"]==0:job["first_frame_index"]=frame.frame_index;origin=frame.timestamp_s
                items=q["detections"]
                fit=PaintFit(np.array(q["matrix"]),q["geometry"]) if q["matrix"] is not None else None
                # Localize all visible people, including frames without valid field geometry.
                poses=detector.predict(frame.rgb,items)
                feet=localizer.update(frame.rgb,items,poses,timestamp_s=frame.timestamp_s,shot_id=old["shot_id"],fit=fit)
                prepared=[]
                for original in items:
                    item=dict(original);item.pop("telemetry",None)
                    candidate=None;reason=None;foot=feet.get(item["track_id"],{"status":"non_person"})
                    if item["kind"]=="person":statuses[foot["status"]]+=1
                    if fit and foot["status"]=="shoe_candidate":
                        candidate,reason=foot_candidate(frame.rgb,item,items,fit,config.pitch,anchor_px=foot["anchor_px"])
                        previous=previous_boxes.get(item["track_id"])
                        if candidate and previous and previous_shot==old["shot_id"]:
                            b,p=item["bbox"],previous
                            if abs((b["y_max"]-b["y_min"])/(p["y_max"]-p["y_min"])-1)>.15:
                                candidate=None;reason="body_height_discontinuity"
                    else:reason="geometry_unavailable" if fit is None else foot["status"]
                    if candidate:
                        item.update(pitch_position_candidate=candidate["position"],
                            coordinate_reference_id=f"pose-midfield-shot-{old['shot_id']}",
                            calibration_id=f"pose-paint-frame-{frame.frame_index}",
                            measurement_evidence=fit.evidence|candidate|{"anchor_method":foot["anchor_method"],
                                "ankle_confidence":foot["ankle_confidence"]})
                    else:
                        item.update(pitch_position_candidate=None,measurement_evidence={})
                    item["foot_localization"]=foot;item["measurement_rejection"]=reason
                    if item["kind"]=="person" and reason:rejections[reason]+=1
                    prepared.append(item)
                base=baseline.update(old|{"detections":items})
                estimate=experimental.update(old|{"detections":prepared})
                for item,result in zip(prepared,estimate["observations"]):item["telemetry"]=result
                audit.write(json.dumps({"frame_index":frame.frame_index,"timestamp_s":frame.timestamp_s,
                    "baseline":base,"pose_estimates":estimate,"detections":prepared},allow_nan=False)+"\n")
                preview=annotate(frame.rgb,prepared,None,frame.frame_index,old["shot_id"])
                for item in prepared:
                    foot=item["foot_localization"]
                    for p in foot.get("ankles_px",[]):cv2.circle(preview,tuple(round(v) for v in p),3,(70,230,245),-1)
                    if foot["status"]=="shoe_candidate":
                        cv2.circle(preview,tuple(round(v) for v in foot["anchor_px"]),4,(255,205,70),-1)
                cv2.rectangle(preview,(0,0),(meta.width,58),(15,23,36),-1)
                cv2.putText(preview,"FOOT POSITION TRIAL | cyan: ankles | gold: shoe candidate | ground contact unverified",
                            (15,24),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,205,100),2)
                cv2.putText(preview,f"Source time {frame.timestamp_s:.2f}s | experimental estimates only",
                            (15,48),cv2.FONT_HERSHEY_SIMPLEX,.6,(240,245,250),1)
                writer.write(preview,frame.timestamp_s-origin)
                previous_boxes={d["track_id"]:d["bbox"] for d in items};previous_shot=old["shot_id"]
                job["processed_frames"]+=1;job["last_frame_index"]=frame.frame_index
                if max_frames and job["processed_frames"]>=max_frames:break
        if not job["processed_frames"]:raise ValueError("No frames in requested review window")
        remaining=manifest["processed_frames"]-job["first_frame_index"]
        expected=min(remaining,max_frames) if max_frames is not None else remaining
        if job["processed_frames"]!=expected:raise ValueError("Incomplete foot-review inputs")
        for p,signature in before.items():
            if (p.stat().st_size,p.stat().st_mtime_ns)!=signature:raise ValueError("Foot-review input changed")
        comparison={"baseline":baseline.finish(),"pose":experimental.finish(),"foot_status_counts":dict(statuses),
            "candidate_rejections":dict(rejections),"scope":"Same frames and geometry; foot method only changed. No confirmed airborne labels or independently validated speeds."}
        write_manifest(output/"comparison.partial.json",comparison)
        for name in ["feet.jsonl","comparison.json","preview.mp4"]:
            stem,suffix=name.rsplit(".",1);(output/f"{stem}.partial.{suffix}").replace(output/name)
        job.update(status="completed",artifacts=["feet.jsonl","comparison.json","preview.mp4"])
        write_manifest(output/"manifest.json",job)
        return job
    except (Exception,KeyboardInterrupt) as exc:
        job.update(status="failed",error=str(exc) or type(exc).__name__);write_manifest(output/"manifest.json",job)
        raise
