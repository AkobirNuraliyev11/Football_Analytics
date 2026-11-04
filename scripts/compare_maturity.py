"""Compare maturity policies on identical, hash-checked experimental observations."""
import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.config import AppConfig
from football_intelligence.model_assets import sha256
from football_intelligence.tactical_io import input_frames
from football_intelligence.telemetry import TelemetryEngine
from scripts.audit_continuity import audit


def synthetic_check():
    cases=[]
    for speed in (0,3,6):
        engines=[TelemetryEngine(experimental=True),
                 TelemetryEngine(experimental=True,separate_identity_maturity=True)]
        values=[{},{}]
        for i in range(151):
            t=i*.04
            point={"x_m":10+speed*t+.05*math.sin(i*1.7),"y_m":20}
            item={"track_id":1,"kind":"person","role":"outfield","team":"A","confirmed":True,
                "continuity_safe":True,"measurement_link_eligible":True,"classification_conflict":False,
                "team_changed":False,"continuity_segment":0,"calibration_id":"analytic",
                "coordinate_reference_id":"analytic-pitch", "pitch_position_candidate":None if i in (60,95,130) else point,
                "measurement_evidence":{"status":"line_checked_estimate","ground_evidence":"visible_feet_candidate","camera_stable":True}}
            frame={"match_id":"synthetic-not-real-video","shot_id":0,"frame_index":i,"timestamp_s":t,"detections":[item]}
            for k,engine in enumerate(engines):
                result=engine.update(frame)["observations"][0]
                if result["status"]=="measured":values[k][i]=result["speed_kmh"]
        assert all(values[1][i]==value for i,value in values[0].items())
        assert all(i not in values[1] for i in (60,95,130))
        rmse=[math.sqrt(sum((v-speed*3.6)**2 for v in rows.values())/len(rows)) for rows in values]
        # Two endpoint errors of at most 5 cm over a complete 0.5 s window.
        assert max(rmse) <= .1/.5*3.6+1e-9
        cases.append({"true_speed_kmh":speed*3.6,"baseline_samples":len(values[0]),"candidate_samples":len(values[1]),
                      "baseline_speed_rmse_kmh":rmse[0],"candidate_speed_rmse_kmh":rmse[1]})
    return {"source":"Analytic constant velocity, 25 Hz, six seconds, 5 cm sinusoidal jitter (sin(frame*1.7)), missing positions at frames 60/95/130. NOT real-video accuracy.","cases":cases}


def compare(tracks,review):
    manifest=json.loads((review/"manifest.json").read_text())
    if manifest["status"]!="completed" or manifest["tracks_sha256"]!=sha256(tracks):
        raise ValueError("Need a completed review of the exact tracks")
    config=AppConfig.from_dict(manifest["config"])
    baseline=TelemetryEngine(config,experimental=True)
    candidate=TelemetryEngine(config,experimental=True,separate_identity_maturity=True)
    added=[];common=0
    for frame in input_frames(tracks,review):
        a,b=baseline.update(frame),candidate.update(frame)
        for old,new in zip(a["observations"],b["observations"]):
            if old["status"]=="measured":
                assert new["status"]=="measured", "Candidate lost an existing measurement"
                assert old["speed_kmh"]==new["speed_kmh"], "Shared speed changed"
                assert old["observed_distance_m"]==new["observed_distance_m"], "Shared fragment distance changed"
                common+=1
            elif new["status"]=="measured":
                added.append({"frame_index":frame["frame_index"],"timestamp_s":frame["timestamp_s"],
                              "track_id":new["track_id"],"speed_kmh":new["speed_kmh"]})
    summaries={"baseline":baseline.finish(),"candidate":candidate.finish()}
    for summary in summaries.values(): summary.pop("fragments")
    result={"source_sha256":manifest["source_sha256"],"tracks_sha256":sha256(tracks),
        "quality_sha256":sha256(review/"quality.jsonl"),"summaries":summaries,
        "shared_measurements_unchanged":common,"additional_measurements":len(added),
        "first_additional_samples":added[:20],
        "baseline_audit":audit(tracks,review),
        "candidate_audit":audit(tracks,review,separate_identity_maturity=True),
        "interpretation":"Observation eligibility and gaps are unchanged. Only publication maturity differs. Additional estimates are not independent accuracy validation."}
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tracks",type=Path,nargs="?")
    parser.add_argument("review",type=Path,nargs="?")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--synthetic",action="store_true",help="Run the independent analytic jitter/gap fixture instead")
    args=parser.parse_args()
    if not args.synthetic and (args.tracks is None or args.review is None):
        parser.error("tracks and review are required unless --synthetic is set")
    result=synthetic_check() if args.synthetic else compare(args.tracks,args.review)
    with args.output.open("x") as target: json.dump(result,target,indent=2,allow_nan=False)
