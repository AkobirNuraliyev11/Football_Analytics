"""Score existing detections against same-frame publisher video labels, without GNSS alignment."""
import argparse
import csv
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.benchmarks.video_reference import score_frames
from football_intelligence.model_assets import sha256
from scripts.evaluate_sensor_baseline import mapper


def evaluate(root,cache,*,start_s=10.,end_s=28.,frame_multiple=15):
    spec=Path(__file__).resolve().parents[1]/'evaluations/soccertrack-sample.json'
    published=json.loads(spec.read_text())
    pinned={Path(item['file']).name:item for item in published['files']}
    label=root/'D_20220220_1_0000_0030.csv';mapping=root/'drone_keypoints.json'
    proof_path=cache.with_suffix('.manifest.json');proof=json.loads(proof_path.read_text())
    for path in (label,mapping):
        if sha256(path)!=pinned[path.name]['sha256']:raise ValueError('Reference file differs from pinned source')
    if (proof.get('status')!='completed' or proof.get('detections_sha256')!=sha256(cache)
        or proof.get('source_sha256')!=pinned['D_20220220_1_0000_0030.mp4']['sha256']):
        raise ValueError('Need completed cache of pinned video')
    hashes={str(p):sha256(p) for p in (label,mapping,proof_path,cache)}
    records=sorted(map(json.loads,cache.read_text().splitlines()),key=lambda row:row['frame_index'])
    if [r['frame_index'] for r in records]!=sorted(proof['requested_frames']):raise ValueError('Incomplete cached frame set')
    if start_s<0 or end_s<start_s or frame_multiple<1:
        raise ValueError('Invalid evaluation interval or frame multiple')
    records=[r for r in records if start_s<=r['timestamp_s']<=end_s and r['frame_index']%frame_multiple==0]
    if not records:raise ValueError('No evaluation frames')
    with label.open() as f:rows=list(csv.reader(f))
    refs={}
    for row in rows[4:]:
        index=int(row[0])-1
        if index in refs:raise ValueError('Duplicate video annotation frame')
        refs[index]={}
        for col in range(1,len(rows[0]),4):
            if rows[0][col] not in ('0','1'):continue
            if rows[2][col:col+4]!=['bb_height','bb_left','bb_top','bb_width']:raise ValueError('Unexpected reference columns')
            h,x,y,w=map(float,row[col:col+4]);refs[index][(rows[0][col],rows[1][col])]=[x+w/2,y+h/2]
    project,fit=mapper(mapping)
    result=score_frames(records,refs,project)
    if any(sha256(Path(p))!=digest for p,digest in hashes.items()):raise ValueError('Input changed')
    return dict(schema_version=1,reference_kind='publisher_video_annotation',evaluation_scope='detection_anchor_agreement',
        can_certify_real_speed=False,frames=len(records),selected_frame_indices=[r['frame_index'] for r in records],
        tile_size=proof.get('tile_size'),input_sha256=hashes,reference_mapping_fit=fit,**result,
        limits='Uses reference-associated identities and a shared publisher homography. Excludes automatic calibration error, '
               'tracker identity accuracy, ground-contact verification and annotation uncertainty. '
               'Net interval speed only. Small same-match development comparison. Model training overlap unknown. '
               'GNSS is a secondary source comparison, not exact ground truth.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','cache','output'):p.add_argument(name,type=Path)
    p.add_argument('--start-s',type=float,default=10.)
    p.add_argument('--end-s',type=float,default=28.)
    p.add_argument('--frame-multiple',type=int,default=15)
    args=p.parse_args();r=evaluate(args.root,args.cache,start_s=args.start_s,end_s=args.end_s,frame_multiple=args.frame_multiple)
    with args.output.open('x') as f:json.dump(r,f,indent=2,allow_nan=False)
    print(json.dumps({k:r[k] for k in ['frames','matched_observations','reference_observations','position_discrepancy_m','net_speed_discrepancy_kmh']},indent=2))
