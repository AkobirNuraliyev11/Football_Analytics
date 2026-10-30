"""Evaluate visible-shoe point localization on a small reviewed development sample."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from football_intelligence.feet import AnkleDetector,FootLocalizer
from football_intelligence.model_assets import sha256
from football_intelligence.video import iter_frames


def evaluate(source,tracks,reference,case,model,output):
    raw=json.loads(reference.read_text());refs=raw[case]
    if sha256(source)!=refs["source_sha256"]:raise ValueError("Reference source mismatch")
    old=next(r for r in map(json.loads,tracks.read_text().splitlines()) if r["frame_index"]==refs["frame_index"])
    detector=AnkleDetector(model)
    for frame in iter_frames(source):
        if frame.frame_index==refs["frame_index"]:
            poses=detector.predict(frame.rgb,old["detections"])
            feet=FootLocalizer().update(frame.rgb,old["detections"],poses,timestamp_s=frame.timestamp_s,shot_id=old["shot_id"])
            break
    else:raise ValueError("Reference frame not found")
    observations=[]
    for ref in refs["points"]:
        item=next(d for d in old["detections"] if d["track_id"]==ref["track_id"])
        b=item["bbox"];box=[(b["x_min"]+b["x_max"])/2,b["y_max"]]
        foot=feet[ref["track_id"]]
        def error(point):return float(np.linalg.norm(np.array(ref["shoe_pixels"])-point,axis=1).min())
        observations.append(ref|{"box_anchor_px":box,"box_error_px":error(box),"pose_status":foot["status"],
            "pose_anchor_px":foot.get("anchor_px"),"pose_error_px":error(foot["anchor_px"]) if foot["status"]=="shoe_candidate" else None})
    matched=[r for r in observations if r["pose_error_px"] is not None]
    result={"case":case,"source_sha256":refs["source_sha256"],"method":raw["method"],"frame_index":refs["frame_index"],
        "pose_model_sha256":detector.fingerprint,"observations":observations,
        "reviewed_points":len(observations),"pose_points_available":len(matched),
        "box_mean_error_all_px":float(np.mean([r["box_error_px"] for r in observations])),
        "box_mean_error_matched_px":float(np.mean([r["box_error_px"] for r in matched])) if matched else None,
        "pose_mean_error_matched_px":float(np.mean([r["pose_error_px"] for r in matched])) if matched else None,
        "note":"Paired errors use exactly the same available points; unavailable pose points are reported, not dropped silently. This single-frame test does not assess jump detection or identity accuracy."}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x") as handle:json.dump(result,handle,indent=2);handle.write("\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ["source","tracks","reference","case","model","output"]:
        parser.add_argument(name,type=str if name=="case" else Path)
    evaluate(**vars(parser.parse_args()))
