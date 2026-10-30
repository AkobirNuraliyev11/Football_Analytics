"""Compare automatic mapping with approximate visually reviewed real-frame points."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from football_intelligence.calibration import transform
from football_intelligence.config import PitchConfig
from football_intelligence.measurement_quality import refine_midfield
from football_intelligence.model_assets import sha256
from football_intelligence.video import iter_frames


def evaluate(source,analysis,tracks,reference,output):
    refs=json.loads(reference.read_text())
    manifest=json.loads((analysis/"manifest.json").read_text())
    if sha256(source)!=refs["source_sha256"] or manifest["source_sha256"]!=refs["source_sha256"]:
        raise ValueError("Reference/source mismatch")
    calibrations={c["frame_index"]:c for c in map(json.loads,(analysis/"calibrations.jsonl").read_text().splitlines())}
    records={r["frame_index"]:r for r in map(json.loads,tracks.read_text().splitlines())}
    wanted={r["frame_index"] for r in refs["landmarks"]+refs["foot_endpoints"]}
    fits={};times={}
    for frame in iter_frames(source):
        if frame.frame_index in wanted:
            fits[frame.frame_index]=refine_midfield(frame.rgb,calibrations[frame.frame_index]["matrix"],
                records[frame.frame_index]["detections"],PitchConfig(**manifest["pitch"]))
            times[frame.frame_index]=frame.timestamp_s
        if frame.frame_index>=max(wanted): break
    errors=[]
    for ref in refs["landmarks"]:
        i=ref["frame_index"]
        before=transform(calibrations[i]["matrix"],[ref["pixel"]])[0]
        after=transform(fits[i].matrix,[ref["pixel"]])[0]
        errors.append(ref|{"before_error_m":float(np.linalg.norm(before-ref["pitch"])),
                           "after_error_m":float(np.linalg.norm(after-ref["pitch"]))})
    endpoints=[]
    for ref in refs["foot_endpoints"]:
        i=ref["frame_index"]
        point=transform(fits[i].matrix,[ref["pixel"]])[0]
        d=next(d for d in records[i]["detections"] if d["track_id"]==ref["track_id"])
        b=d["bbox"];anchor=[(b["x_min"]+b["x_max"])/2,b["y_max"]]
        automatic=transform(fits[i].matrix,[anchor])[0]
        offsets=np.array([[3,0],[-3,0],[0,3],[0,-3]])+ref["pixel"]
        sensitivity=float(np.linalg.norm(transform(fits[i].matrix,offsets)-point,axis=1).max())
        endpoints.append(ref|{"timestamp_s":times[i],"pitch_position":point.tolist(),
            "automatic_anchor_pitch":automatic.tolist(),"anchor_difference_m":float(np.linalg.norm(automatic-point)),
            "three_pixel_sensitivity_m":sensitivity})
    a,b=endpoints
    dt=b["timestamp_s"]-a["timestamp_s"]
    displacement=float(np.linalg.norm(np.array(b["pitch_position"])-a["pitch_position"]))
    automatic=float(np.linalg.norm(np.array(b["automatic_anchor_pitch"])-a["automatic_anchor_pitch"]))
    result={"source_sha256":refs["source_sha256"],"reference_method":refs["method"],
        "landmark_checks":errors,"rmse_before_m":float(np.sqrt(np.mean([r["before_error_m"]**2 for r in errors]))),
        "rmse_after_m":float(np.sqrt(np.mean([r["after_error_m"]**2 for r in errors]))),
        "foot_endpoints":endpoints,"interval_s":dt,"net_displacement_estimate_m":displacement,
        "mean_net_speed_estimate_kmh":displacement/dt*3.6,
        "automatic_anchor_mean_net_speed_kmh":automatic/dt*3.6,
        "three_pixel_speed_sensitivity_kmh":sum(r["three_pixel_sensitivity_m"] for r in endpoints)/dt*3.6,
        "limits":"Net endpoint displacement, not distance traveled or instantaneous speed. Pixel sensitivity is not a confidence interval and excludes calibration/scale/ground-contact error. Same development clip; no independent athlete-speed ground truth."}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x") as handle: json.dump(result,handle,indent=2);handle.write("\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ["source","analysis","tracks","reference","output"]:parser.add_argument(name,type=Path)
    args=parser.parse_args()
    evaluate(args.source,args.analysis,args.tracks,args.reference,args.output)
