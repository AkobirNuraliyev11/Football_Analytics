"""Validate the four saved Step 7 trials; no models or new inference required."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.evaluate_trajectories import evaluate


def validate(root):
    import av
    import numpy as np
    cases={}
    for name in ("known-motion","first-experimental","second-experimental","first-strict"):
        directory=root/name
        manifest=json.loads((directory/"manifest.json").read_text())
        summary=json.loads((directory/"occupancy.json").read_text())
        assert manifest["status"]=="completed"
        groups=[]
        for group in summary["groups"]:
            seconds=group["observed_person_seconds"]
            assert math.isclose(np.sum(group["occupancy_seconds"]),seconds,abs_tol=1e-9)
            assert math.isclose(np.sum(group["smoothed_seconds"]),seconds,abs_tol=1e-9)
            assert math.isclose(np.sum(group["probability_mass"]),1 if seconds else 0,abs_tol=1e-9)
            groups.append({k:group[k] for k in ("id","identity","observed_person_seconds","intervals")})
        with av.open(str(directory/"preview.mp4")) as container:
            times=[frame.time for frame in container.decode(video=0)]
        assert len(times)==manifest["preview_frames"]
        rows=[json.loads(line) for line in (directory/"radar.jsonl").read_text().splitlines()]
        expected=[row["timestamp_s"]-manifest["preview_source_start_s"] for row in rows
                  if manifest["preview_start_s"]<=row["timestamp_s"]<manifest["preview_start_s"]+manifest["preview_seconds_limit"]]
        np.testing.assert_allclose(times,expected,atol=1e-6)
        cases[name]={"input_hashes":manifest["input_hashes"],"quality":summary["quality"],
            "frames":manifest["processed_frames"],"coverage":summary["coverage"],"groups":groups,
            "preview_frames":len(times),"preview_last_timestamp_s":times[-1]}
    synthetic=cases["known-motion"]
    tracks=[g for g in synthetic["groups"] if g["identity"]["type"]=="track"]
    assert {g["identity"]["track_id"] for g in tracks}=={1,2}
    assert all(math.isclose(g["observed_person_seconds"],6) for g in tracks)
    assert cases["first-experimental"]["coverage"]["radar_samples"]==83
    assert cases["second-experimental"]["coverage"]["radar_samples"]==0
    assert cases["first-strict"]["coverage"]["radar_samples"]==0
    path=root/"known-motion/radar.jsonl"
    labels={"predictions_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "independent_reference":True,"reference_method":"Analytic constant-velocity fixture, NOT real footage", "samples":[]}
    for i in range(201):
        for track,speed,y in ((1,3,20),(2,6,30)):
            labels["samples"].append({"match_id":"synthetic-demo-not-real-footage", "shot_id":0,
                "frame_index":i,"timestamp_s":i/25,"track_id":track,"coordinate_reference_id":"synthetic-pitch",
                "x_m":10+speed*i/25,"y_m":y,"uncertainty_m":0})
    score=evaluate(path,labels)
    assert score["position_rmse_m"]<1e-10
    assert score["interval_speed_mae_kmh"]<1e-10
    score.pop("samples")
    return {"step":7,"status":"passed","cases":cases,"analytic_reference_evaluation":score,
        "real_video_independent_reference":"Unavailable: no independently measured meter trajectories provided",
        "continuity_decision":"Preserve existing gates; no demonstrated real-video continuity improvement",
        "limits":"Sparse experimental occupancy only; reliable real-video telemetry and pitch control remain unresolved"}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path("data/step-07"))
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    with args.output.open("x") as target:
        json.dump(validate(args.root),target,indent=2,allow_nan=False)
