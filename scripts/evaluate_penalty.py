"""Data-only check on saved development tracks and a separately labeled camera view."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from football_intelligence.calibration import CalibrationError, transform
from football_intelligence.config import PitchConfig
from football_intelligence.detection import FootballDetector
from football_intelligence.model_assets import sha256
from football_intelligence.penalty_geometry import check_penalty_area
from football_intelligence.tactical_io import input_frames
from football_intelligence.video import iter_frames


def evaluate(source, analysis, check_video, reference, model_dir):
    manifest=json.loads((analysis/'manifest.json').read_text())
    labels=json.loads(reference.read_text())
    if manifest['status']!='completed' or sha256(source)!=manifest['source_sha256'] or sha256(check_video)!=labels['source_sha256']:
        raise ValueError('Source mismatch')
    seeds={r['frame_index']:r for r in map(json.loads,(analysis/'calibrations.jsonl').read_text().splitlines())}
    counts=Counter()
    reasons=Counter()
    for record,frame in zip(input_frames(analysis/'tracks.jsonl'),iter_frames(source)):
        index=record['frame_index']
        if frame.frame_index!=index or abs(frame.timestamp_s-record['timestamp_s'])>1e-6:
            raise ValueError('Frame timing mismatch')
        counts['frames']+=1
        if index not in seeds:
            reasons['missing seed']+=1
            continue
        items=record['detections']
        try:
            mapping=check_penalty_area(frame.rgb,seeds[index]['matrix'],'left',items)
        except CalibrationError as e:
            reasons[str(e)]+=1
            continue
        counts['mapped_frames']+=1
        for item in items:
            if item['kind']!='person' or not item['confirmed']: continue
            anchor=item['image_anchor']
            try: mapping.project([anchor['x'],anchor['y']])
            except CalibrationError: continue
            counts['observed_person_anchors_in_support']+=1
    if counts['frames']!=manifest['processed_frames']: raise ValueError('Incomplete development stream')
    detector=FootballDetector(model_dir)
    holdout={}
    # Fixed in advance: wide view at 0, partial views at 375 and 700.
    for frame in iter_frames(check_video):
        i=frame.frame_index
        if i not in (0,375,700): continue
        row={}
        holdout[str(i)]=row
        try:
            seed=detector.calibrate(frame.rgb,match_id='held-out-view',shot_id=0,frame_index=i)
            if i==labels['frame_index']:
                row['references']=[
                    {'name':name, 'seed_error_m':float(np.linalg.norm(transform(seed.matrix,[px])[0]-truth)),
                     'local_error_m':None} for name,px,truth in labels['points']
                ]
            items=[{'bbox':vars(d.bbox)} for d in detector.detect(frame.rgb)]
            m=check_penalty_area(frame.rgb,seed.matrix,labels['side'],items)
            row.update(status='mapped',paint_p90_m=m.residual_m,supported_lines=m.supported_lines)
            for point,(_,px,truth) in zip(row.get('references',[]),labels['points']):
                try:
                    point['local_error_m']=float(np.linalg.norm(m.project(px)-truth))
                except CalibrationError:
                    pass
        except CalibrationError as e:
            row.update(status='withheld',reason=str(e))
        if i==700:break
    return {'development_source_sha256':manifest['source_sha256'],'held_out_source_sha256':labels['source_sha256'],
            'development':dict(counts),'development_rejections':dict(reasons),'held_out':holdout,
            'scope':'Local field geometry only. Person anchor counts precede contact, identity and motion checks.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','analysis','check_video','reference','model_dir','output'):p.add_argument(k,type=Path)
    a=p.parse_args()
    report=evaluate(a.source,a.analysis,a.check_video,a.reference,a.model_dir)
    with a.output.open('x') as f: json.dump(report,f,indent=2,allow_nan=False)
