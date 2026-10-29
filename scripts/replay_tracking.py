"""Repeat tracking/classification on retained detections; not a detector benchmark.

Run: python scripts/replay_tracking.py SOURCE OLD_RUN NEW_OUTPUT [--labels JSON]
Old runs retain emitted detections only, so low-confidence discarded detections cannot
be recovered. This diagnostic deliberately leaves model inference and geometry fixed.
"""
import argparse
from contextlib import closing
from dataclasses import asdict
from fractions import Fraction
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.analysis import PreviewWriter, annotate
from football_intelligence.classification import TeamRoleClassifier
from football_intelligence.detection import Detection
from football_intelligence.model_assets import sha256
from football_intelligence.models import BoundingBox, Role
from football_intelligence.tracking import MultiObjectTracker
from football_intelligence.video import iter_frames, probe_video


def replay(source, old_run, output, labels_path=None):
    old_manifest=json.loads((old_run/"manifest.json").read_text())
    if old_manifest["status"]!="completed" or sha256(source)!=old_manifest["source_sha256"]:
        raise ValueError("Replay requires completed records and the exact source video")
    output.mkdir(parents=True,exist_ok=False)
    classifier,tracker=TeamRoleClassifier(),MultiObjectTracker()
    meta=probe_video(source)
    label_document=json.loads(labels_path.read_text()) if labels_path else {}
    if labels_path and label_document.get("source_sha256")!=old_manifest["source_sha256"]:
        raise ValueError("Labels do not match the source fingerprint")
    labels=label_document.get("observations",[])
    expected={(v["frame_index"],v["source_track_id"]):v["team"] for v in labels}
    scores={key:{"correct":0,"wrong":0,"unknown":0} for key in ("before","after")}
    count=0; breaks=0; switches=0; old_ids=set();new_ids=set()
    with (old_run/"tracks.jsonl").open() as old_file, (output/"tracks.jsonl").open("x") as new_file, \
         closing(iter_frames(source)) as frames, closing(PreviewWriter(output/"preview.mp4",meta.width,meta.height,
                                             Fraction(meta.average_rate or "25"))) as writer:
        for line,frame in zip(old_file,frames):
            old=json.loads(line)
            if frame.frame_index!=old["frame_index"] or abs(frame.timestamp_s-old["timestamp_s"])>1e-6:
                raise ValueError("Cached frame timing mismatch")
            detections=[Detection(BoundingBox(**d["bbox"]),d["confidence"],d["kind"],Role(d["role_candidate"]))
                        for d in old["detections"]]
            originals={id(det):original for det,original in zip(detections,old["detections"])}
            records=[]
            for track,confirmed in tracker.update(detections,frame.rgb,timestamp_s=frame.timestamp_s,shot_id=old["shot_id"]):
                record=dict(originals[id(track.detection)])
                record.update(source_track_id=record["track_id"],track_id=track.track_id,confirmed=confirmed,
                    continuity_segment=track.continuity_segment,continuity_safe=track.continuity_safe,
                    association_reason=track.association_reason)
                records.append(record)
            records=classifier.update(frame.rgb,records,timestamp_s=frame.timestamp_s,shot_id=old["shot_id"])
            after={r["source_track_id"]:r for r in records}
            for record in records:
                record["measurement_link_eligible"]=(record["confirmed"] and record["continuity_safe"]
                    and not record["classification_conflict"] and not record["team_changed"])
                breaks+=not record["measurement_link_eligible"]
                switches+=record["team_changed"]
                new_ids.add(record["track_id"])
            for d in old["detections"]:
                old_ids.add(d["track_id"])
                target=expected.get((frame.frame_index,d["track_id"]))
                if target is None:continue
                for key,value in [("before",d["team"]),("after",after.get(d["track_id"],{}).get("team","unknown"))]:
                    scores[key]["unknown" if value=="unknown" else "correct" if value==target else "wrong"]+=1
            current=old|{"detections":records}
            new_file.write(json.dumps(current,allow_nan=False)+"\n")
            supported=SimpleNamespace(landmarks=[]) if old["calibration_status"]=="fit_unvalidated" else None
            writer.write(annotate(frame.rgb,records,supported,frame.frame_index,old["shot_id"]),frame.timestamp_s)
            count+=1
    if count!=old_manifest["processed_frames"] or sum(scores["before"].values())!=len(expected):
        raise ValueError("Replay did not consume all expected frames/labels")
    report={"frames":count,"label_scores":scores,"labels_requested":len(expected),
            "old_track_count":len(old_ids),"new_track_count":len(new_ids),"team_changes":switches,
            "rejected_measurement_links":breaks,"classification":classifier.summary(),
            "scope":"Replay of retained detections; geometry fixed; track counts are not identity accuracy",
            "source_sha256":old_manifest["source_sha256"]}
    (output/"review.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("source","old_run","output"):parser.add_argument(key,type=Path)
    parser.add_argument("--labels",type=Path)
    args=parser.parse_args()
    replay(args.source,args.old_run,args.output,args.labels)
