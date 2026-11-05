"""Compare penalty mappings at pre-labeled points, retaining unavailable predictions."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from football_intelligence.calibration import CalibrationError
from football_intelligence.detection import FootballDetector
from football_intelligence.model_assets import sha256
from football_intelligence.penalty_geometry import _check_paint,check_penalty_area
from football_intelligence.video import iter_frames


def evaluate(video, reference, models):
    labels=json.loads(reference.read_text())
    if sha256(video)!=labels['sha256']:
        raise ValueError("Video differs from labeled source")
    detector=FootballDetector(models)
    report={'source_sha256':labels['sha256'],'frames':{}}
    selected={int(i) for i in labels['frames']} | {375,700}
    for frame in iter_frames(video):
        i=frame.frame_index
        if i not in selected: continue
        row={}
        report['frames'][i]=row
        try:
            seed=detector.calibrate(frame.rgb,match_id='box-validation',shot_id=0,frame_index=i)
            items=[{'bbox':vars(d.bbox)} for d in detector.detect(frame.rgb)]
        except CalibrationError as exc:
            row['seed_failure']=str(exc)
            continue
        for name,method in [('previous',_check_paint),('junction',check_penalty_area)]:
            points=labels['frames'].get(str(i),[])
            result=row[name]={'mapped':False,'reference_errors_m':{key:None for key,_,_ in points}}
            try:
                mapping=method(frame.rgb,seed.matrix,labels['side'],items)
            except CalibrationError as exc:
                result['reason']=str(exc)
                continue
            result.update(mapped=True,paint_p90_m=mapping.residual_m)
            for key,pixel,truth in points:
                try: estimated=mapping.project(pixel)
                except CalibrationError: continue
                result['reference_errors_m'][key]=float(np.linalg.norm(estimated-truth))
        if i==max(selected): break
    if set(report['frames'])!=selected: raise ValueError("Incomplete test video")
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('video','reference','models','output'):p.add_argument(arg,type=Path)
    args=p.parse_args()
    result=evaluate(args.video,args.reference,args.models)
    with args.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
