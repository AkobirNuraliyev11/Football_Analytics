"""Replay temporal ball selection on retained observations without inference."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.ball_selection import BallSelector
from football_intelligence.model_assets import sha256


def replay(tracks,review):
    if sha256(tracks)!=review['tracks_sha256']:raise ValueError('Tracks hash mismatch')
    selector=BallSelector();predictions={};states={};observed={};count=0;competing=0;selected=0
    for row in map(json.loads,tracks.read_text().splitlines()):
        result=selector.update(row['detections'],timestamp_s=row['timestamp_s'],shot_id=row['shot_id'])
        observed[row['frame_index']]={d['track_id'] for d in row['detections'] if d['kind']=='ball'}
        predictions[row['frame_index']]=result['selected_track_id']
        states[row['frame_index']]=result['reason']
        count+=1;selected+=result['selected_track_id'] is not None
        competing+=len(result['candidate_scores'])>1
    labels=review['candidates'];seen=set();cases=[]
    for label in labels:
        key=(label['frame_index'],label['track_id'])
        if key in seen or label['label'] not in ('ball','not_ball'):raise ValueError('Invalid/duplicate label')
        if key[0] not in observed or key[1] not in observed[key[0]]:raise ValueError('Reviewed ball candidate missing')
        seen.add(key)
        cases.append(label|{'selected':predictions[key[0]]==key[1],'selection_reason':states[key[0]]})
    return {'tracks_sha256':sha256(tracks),'frames':count,'frames_with_competing_candidates':competing,
        'frames_with_selection':selected,'reviewed_candidates':cases,
        'retained_true_candidates':sum(c['selected'] and c['label']=='ball' for c in cases),
        'retained_false_candidates':sum(c['selected'] and c['label']=='not_ball' for c in cases),
        'unselected_true_candidates':sum(not c['selected'] and c['label']=='ball' for c in cases),
        'scope':'Selection on retained detections. Assistant-reviewed development examples; '
                'not whole-frame precision/recall, held-out validation or verified ball identity.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('tracks','review','output'):p.add_argument(n,type=Path)
    a=p.parse_args();result=replay(a.tracks,json.loads(a.review.read_text()))
    result['review_sha256']=sha256(a.review)
    with a.output.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
