"""Locate where experimental real-video observations lose temporal continuity."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.config import AppConfig
from football_intelligence.model_assets import sha256
from football_intelligence.tactical_io import input_frames
from football_intelligence.telemetry import TelemetryEngine


def audit_frames(frames, config=None, *, separate_identity_maturity=False):
    engine = TelemetryEngine(config, experimental=True,separate_identity_maturity=separate_identity_maturity)
    counts, rejection = Counter(), Counter()
    runs, previous = {}, {}
    for frame in frames:
        measured = engine.update(frame)
        counts["frames"] += 1
        now = {}
        for item, value in zip(frame["detections"],measured["observations"]):
            if item["kind"] != "person": continue
            counts["person_observations"] += 1
            if item.get("pitch_position_candidate") is not None:
                counts["position_candidates"] += 1
            if item.get("measurement_rejection"):
                rejection[item["measurement_rejection"]] += 1
            counts[value["status"]] += 1
            key = (frame["shot_id"], item["track_id"])
            fragment = value["fragment_id"]
            if fragment is not None:
                if fragment not in runs:
                    runs[fragment] = {"fragment_id":fragment,"shot_id":frame["shot_id"],
                        "track_id":item["track_id"],"start_s":frame["timestamp_s"],
                        "end_s":frame["timestamp_s"],"samples":0,"mature_samples":0,
                        "end_reason":"end_of_input","end_evidence_rejection":None}
                run = runs[fragment]
                run["end_s"] = frame["timestamp_s"]
                run["samples"] += 1
                run["mature_samples"] += value["status"] == "measured"
                now[key] = fragment
            if key in previous and previous[key] != fragment:
                reason = value["reasons"][0] if value["reasons"] else "fragment_change"
                runs[previous[key]]["end_reason"] = reason
                runs[previous[key]]["end_evidence_rejection"] = item.get("measurement_rejection")
        for key, fragment in previous.items():
            if key not in now and runs[fragment]["end_reason"] == "end_of_input":
                runs[fragment]["end_reason"] = "shot_change" if key[0] != frame["shot_id"] else "missing_observation"
        previous = now
    for run in runs.values(): run["duration_s"] = run["end_s"] - run["start_s"]
    summary = engine.finish()
    counts.setdefault("position_candidates",0)
    counts.setdefault("measured",0)
    return {"maturity_policy":summary["maturity_policy"],"counts":dict(counts),"measurement_rejections":dict(rejection),
        "telemetry_rejections":summary["rejection_counts"],
        "run_end_reasons":dict(Counter(r["end_reason"] for r in runs.values())),
        "run_end_evidence_rejections":dict(Counter(r["end_evidence_rejection"] for r in runs.values() if r["end_evidence_rejection"])),
        "runs_at_least_seconds":{str(t):sum(r["duration_s"]+1e-9>=t for r in runs.values()) for t in (.25,.5,1,2)},
        "runs":sorted(runs.values(),key=lambda r:r["duration_s"],reverse=True),
        "mature_fragments":summary["fragments"],
        "scope":"Eligible runs before/after warmup; overlapping rejection reasons are not additive"}


def audit(tracks, review, *, separate_identity_maturity=False):
    manifest=json.loads((review/"manifest.json").read_text())
    if manifest["status"]!="completed" or manifest["tracks_sha256"]!=sha256(tracks):
        raise ValueError("Need completed review for the exact tracks")
    result=audit_frames(input_frames(tracks,review),AppConfig.from_dict(manifest["config"]),
                        separate_identity_maturity=separate_identity_maturity)
    result.update(source_sha256=manifest["source_sha256"],tracks_sha256=sha256(tracks),
                  quality_sha256=sha256(review/"quality.jsonl"))
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tracks",type=Path)
    parser.add_argument("review",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--separate-identity-maturity",action="store_true")
    args=parser.parse_args()
    result=audit(args.tracks,args.review,separate_identity_maturity=args.separate_identity_maturity)
    with args.output.open("x") as target: json.dump(result,target,indent=2,allow_nan=False)
