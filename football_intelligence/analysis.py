"""Step 4 orchestration: automatic boxes, IDs, pitch candidates, and review video."""
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path
import uuid

from .calibration import CalibrationError, update_camera
from .config import PitchConfig
from .detection import FootballDetector
from .ingestion import write_manifest
from .model_assets import sha256
from .models import PixelPoint
from .shots import ShotConfig, ShotDetector
from .tracking import MultiObjectTracker
from .validation import identifier, integer
from .video import iter_frames, local_source, probe_video


class PreviewWriter:
    """Silent H.264 review output preserving presentation timing to microseconds."""
    def __init__(self, path, width, height, rate):
        import av
        self.av = av
        self.container = av.open(str(path), "w", options={"movflags":"+faststart"})
        self.stream = self.container.add_stream("libx264", rate=rate)
        self.stream.width = width + width % 2
        self.stream.height = height + height % 2
        self.stream.pix_fmt = "yuv420p"
        self.stream.options = {"crf":"23", "preset":"veryfast"}
        self.stream.time_base = self.stream.codec_context.time_base = Fraction(1, 1_000_000)
        self.previous_pts = None

    def write(self, rgb, timestamp_s):
        import numpy as np
        rgb = np.pad(rgb, ((0,self.stream.height-rgb.shape[0]),(0,self.stream.width-rgb.shape[1]),(0,0)))
        frame = self.av.VideoFrame.from_ndarray(rgb, format="rgb24")
        frame.pts, frame.time_base = round(timestamp_s*1_000_000), Fraction(1,1_000_000)
        if self.previous_pts is not None and frame.pts <= self.previous_pts:
            raise ValueError("Preview timestamps collapse at microsecond precision")
        self.previous_pts = frame.pts
        for packet in self.stream.encode(frame):
            self.container.mux(packet)

    def close(self):
        try:
            for packet in self.stream.encode():
                self.container.mux(packet)
        finally:
            self.container.close()


def annotate(rgb, records, calibration, frame_index, shot_id):
    import cv2
    output = rgb.copy()
    for record in records:
        box = record["bbox"]
        color = (255,210,60) if record["kind"] == "ball" else (60,220,180)
        p1 = (int(box["x_min"]), int(box["y_min"]))
        p2 = (int(box["x_max"]), int(box["y_max"]))
        cv2.rectangle(output,p1,p2,color,2)
        label = f'{record["kind"]} #{record["track_id"]} {record["confidence"]:.2f}'
        cv2.putText(output,label,(p1[0],max(16,p1[1]-5)),cv2.FONT_HERSHEY_SIMPLEX,.45,color,1)
    if calibration:
        for point in calibration.landmarks:
            if point.name in calibration.inlier_names:
                cv2.circle(output,(round(point.pixel.x),round(point.pixel.y)),4,(70,220,70),-1)
    state = "pitch fit (unvalidated)" if calibration else "pitch unavailable"
    cv2.rectangle(output,(0,0),(output.shape[1],30),(12,20,32),-1)
    cv2.putText(output,f"Frame {frame_index} | shot {shot_id} | {state}",(10,21),
                cv2.FONT_HERSHEY_SIMPLEX,.5,(240,240,240),1)
    return output


def analyze_video(source: Path, output: Path, *, match_id: str, model_dir=Path("data/models"),
                  device="cpu", max_frames=None, pitch_every=10, detector=None,
                  pitch: PitchConfig | None = None):
    """Pipeline has injectable detector for deterministic integration tests."""
    identifier("match_id",match_id)
    integer("pitch_every",pitch_every,minimum=1)
    if max_frames is not None:
        integer("max_frames",max_frames,minimum=1)
    pitch = pitch or PitchConfig()
    source = local_source(source)
    metadata = probe_video(source)
    detector = detector or FootballDetector(model_dir,device=device)
    output.mkdir(parents=True,exist_ok=False)
    manifest = {"schema_version":1,"job_id":str(uuid.uuid4()),"match_id":match_id,"status":"running",
                "created_at":datetime.now(timezone.utc).isoformat(),"video":metadata.to_dict(),
                "pitch":asdict(pitch),"pitch_dimensions_assumed":True,"max_frames":max_frames,
                "pitch_every":pitch_every,"device":device,"processed_frames":0,
                "frames_with_pitch_fit":0,"preview_audio":False,"model_hashes":detector.fingerprints,
                "metric_telemetry_enabled":False,
                "orientation":"model-canonical; cross-shot physical-end identity unverified"}
    write_manifest(output/"manifest.json",manifest)
    try:
        source_before = source.stat()
        manifest["source_sha256"] = sha256(source)
        shots, tracker = ShotDetector(ShotConfig()), MultiObjectTracker()
        calibration, previous = None, None
        preview = PreviewWriter(output/"preview.partial.mp4", metadata.width,metadata.height,
                                Fraction(metadata.average_rate) if metadata.average_rate else Fraction(25))
        with closing(preview), closing(iter_frames(source)) as frames, \
             (output/"tracks.partial.jsonl").open("x") as track_file, \
             (output/"calibrations.partial.jsonl").open("x") as calibration_file:
            for frame in frames:
                shot = shots.update(frame)
                scope = dict(match_id=match_id,shot_id=shot["shot_id"],frame_index=frame.frame_index)
                reason = None
                if shot["boundary_reasons"]:
                    calibration = None
                try:
                    if calibration is None or frame.frame_index % pitch_every == 0:
                        calibration = detector.calibrate(frame.rgb,**scope,pitch=pitch)
                    else:
                        calibration = update_camera(previous.rgb,frame.rgb,calibration,**scope,
                            previous_timestamp_s=previous.timestamp_s,timestamp_s=frame.timestamp_s)
                except CalibrationError as exc:
                    calibration = None
                    reason = str(exc)
                if calibration:
                    manifest["frames_with_pitch_fit"] += 1
                    calibration_file.write(json.dumps(calibration.to_dict(),allow_nan=False)+"\n")
                records = []
                for track,confirmed in tracker.update(detector.detect(frame.rgb),frame.rgb,
                                                      timestamp_s=frame.timestamp_s,shot_id=shot["shot_id"]):
                    detection = track.detection
                    box = detection.bbox
                    # The ball center is an image anchor only; never ground-project an airborne ball.
                    anchor = box.foot_anchor if detection.kind == "person" else PixelPoint(
                        (box.x_min+box.x_max)/2,(box.y_min+box.y_max)/2)
                    position, projection_state = None, "calibration_unavailable"
                    if detection.kind == "ball":
                        projection_state = "ball_depth_unknown"
                    elif calibration:
                        try:
                            point = calibration.project(anchor,**scope,width=metadata.width,height=metadata.height)
                            if point.is_on_pitch(pitch):
                                position,projection_state = asdict(point),"ground_contact_unverified"
                            else:
                                projection_state = "outside_pitch"
                        except CalibrationError:
                            projection_state = "outside_calibrated_support"
                    records.append({"track_id":track.track_id,"confirmed":confirmed,"kind":detection.kind,
                        "role_candidate":detection.role.value,"team":"unknown","bbox":asdict(box),
                        "confidence":detection.confidence,"image_anchor":asdict(anchor),
                        "pitch_position_candidate":position,"projection_state":projection_state,
                        "ground_contact_reliable":False,
                        "calibration_id":calibration.calibration_id if position else None})
                record = frame.timing_record() | shot | {"match_id":match_id,"detections":records,
                    "calibration_status":"fit_unvalidated" if calibration else "unavailable",
                    "calibration_reason":reason}
                track_file.write(json.dumps(record,allow_nan=False)+"\n")
                preview.write(annotate(frame.rgb,records,calibration,frame.frame_index,shot["shot_id"]),frame.timestamp_s)
                manifest["processed_frames"] += 1
                previous = frame
                if max_frames is not None and manifest["processed_frames"] >= max_frames:
                    break
        source_after = source.stat()
        if (source_before.st_size,source_before.st_mtime_ns) != (source_after.st_size,source_after.st_mtime_ns):
            raise ValueError("Source changed during analysis")
        for name in ("tracks.jsonl","calibrations.jsonl","preview.mp4"):
            stem,suffix = name.rsplit(".",1)
            (output/f"{stem}.partial.{suffix}").replace(output/name)
        manifest.update(status="completed",shot_count=shots.shot_id+1,
                        artifacts=["tracks.jsonl","calibrations.jsonl","preview.mp4"],
                        completed_at=datetime.now(timezone.utc).isoformat())
        write_manifest(output/"manifest.json",manifest)
        return manifest
    except (Exception,KeyboardInterrupt) as exc:
        manifest.update(status="failed",error=str(exc) or type(exc).__name__)
        write_manifest(output/"manifest.json",manifest)
        raise
