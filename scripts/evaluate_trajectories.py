"""Score radar positions against separately supplied, independently labeled meter positions.

No labels are inferred from the homography under evaluation. This utility measures
position and interval displacement-speed error, not smoothed telemetry speed error.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.validation import finite, integer, identifier


def evaluate(predictions, labels):
    payload=predictions.read_bytes()
    if labels.get("predictions_sha256") != hashlib.sha256(payload).hexdigest():
        raise ValueError("Labels must identify the exact prediction file")
    if labels.get("independent_reference") is not True:
        raise ValueError("Reference must be independent of the evaluated projection")
    identifier("reference_method",labels.get("reference_method"))
    samples=labels.get("samples")
    if not isinstance(samples,list) or not samples:
        raise ValueError("Reference needs labeled samples")
    predictions_by_key={}
    for line in payload.splitlines():
        frame=json.loads(line)
        for point in frame["positions"]:
            key=(frame["match_id"],frame["shot_id"],frame["frame_index"],point["track_id"])
            if key in predictions_by_key: raise ValueError("Duplicate prediction")
            predictions_by_key[key]=(frame,point)
    rows=[];seen=set();previous={};speed_errors=[]
    for sample in samples:
        for name in ("shot_id","frame_index","track_id"): integer(name,sample[name])
        for name in ("match_id","coordinate_reference_id"): identifier(name,sample[name])
        for name in ("timestamp_s","uncertainty_m"): finite(name,sample[name],minimum=0)
        for name in ("x_m","y_m"): finite(name,sample[name])
        key=tuple(sample[k] for k in ("match_id","shot_id","frame_index","track_id"))
        if key in seen: raise ValueError("Duplicate reference sample")
        seen.add(key)
        group=key[:2]+(key[3],sample["coordinate_reference_id"])
        last=previous.get(group)
        if last and sample["timestamp_s"]<=last[0]["timestamp_s"]:
            raise ValueError("Reference samples must increase per track")
        prediction=predictions_by_key.get(key)
        row={"match_id":key[0],"shot_id":key[1],"frame_index":key[2],"track_id":key[3],
             "available":prediction is not None,"position_error_m":None,"uncertainty_m":sample["uncertainty_m"]}
        if prediction:
            frame,point=prediction
            if abs(frame["timestamp_s"]-sample["timestamp_s"])>1e-6:
                raise ValueError("Reference timestamp differs from prediction")
            if point["coordinate_reference_id"]!=sample["coordinate_reference_id"]:
                raise ValueError("Reference coordinate system differs")
            row["position_error_m"]=math.hypot(point["x_m"]-sample["x_m"],point["y_m"]-sample["y_m"])
            if last and last[1] and last[1][1]["fragment_id"]==point["fragment_id"]:
                before,old=last[0],last[1][1]
                dt=sample["timestamp_s"]-before["timestamp_s"]
                expected=math.hypot(sample["x_m"]-before["x_m"],sample["y_m"]-before["y_m"])/dt*3.6
                actual=math.hypot(point["x_m"]-old["x_m"],point["y_m"]-old["y_m"])/dt*3.6
                speed_errors.append(abs(actual-expected))
        previous[group]=(sample,prediction)
        rows.append(row)
    errors=[row["position_error_m"] for row in rows if row["available"]]
    return {"reference_method":labels["reference_method"],"reference_independence":"asserted by label supplier, not verified by scorer",
        "labeled_samples":len(rows),"available_samples":len(errors),"availability":len(errors)/len(rows),
        "position_mae_m":sum(errors)/len(errors) if errors else None,
        "position_rmse_m":math.sqrt(sum(e*e for e in errors)/len(errors)) if errors else None,
        "paired_interval_count":len(speed_errors),
        "interval_speed_mae_kmh":sum(speed_errors)/len(speed_errors) if speed_errors else None,
        "scope":"Matched visible positions and same-fragment labeled intervals; not full-path or sprint accuracy",
        "samples":rows}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions",type=Path)
    parser.add_argument("labels",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=evaluate(args.predictions,json.loads(args.labels.read_text()))
    with args.output.open("x") as target:
        json.dump(result,target,indent=2,allow_nan=False)
