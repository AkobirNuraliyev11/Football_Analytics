"""Score paired candidate centers on approximate reviewed visible-ball frames."""
import argparse,json,math
from collections import defaultdict
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.model_assets import sha256


def score(reports, review, threshold=.15):
    if not reports or not 0<=threshold<=1:raise ValueError('Reports and valid threshold required')
    if len({r['source_sha256'] for r in reports})!=1:raise ValueError('Mixed source videos')
    if review.get('source_sha256')!=reports[0]['source_sha256']:
        raise ValueError('Review source fingerprint mismatch')
    labels={}
    for ref in review['frames']:
        if ref['frame_index'] in labels:raise ValueError('Duplicate reviewed frame')
        if ref['status'] not in ('visible','uncertain'):raise ValueError('Unknown review status')
        if ref['status']=='visible':
            if (len(ref['center_px'])!=2 or not all(math.isfinite(v) for v in ref['center_px'])
                    or not math.isfinite(ref['radius_px']) or ref['radius_px']<=0):raise ValueError('Invalid center review')
        labels[ref['frame_index']]=ref
    rows={};modes=set()
    for report in reports:
        for row in report['rows']:
            key=row['mode'],row['frame_index']
            if key in rows:raise ValueError('Duplicate prediction frame/mode')
            rows[key]=row;modes.add(row['mode'])
    result={}
    for mode in sorted(modes):
        counts=dict(visible_frames=0,matched_frames=0,missed_frames=0,off_reference_candidates=0,
                    excluded_uncertain_frames=0)
        for frame,ref in labels.items():
            if (mode,frame) not in rows:raise ValueError('Missing paired prediction row')
            if ref['status']=='uncertain':counts['excluded_uncertain_frames']+=1;continue
            boxes=[d['bbox'] for d in rows[mode,frame]['detections'] if d['confidence']>=threshold]
            distances=[math.dist([(b['x_min']+b['x_max'])/2,(b['y_min']+b['y_max'])/2],ref['center_px']) for b in boxes]
            matched=any(d<=ref['radius_px'] for d in distances)
            counts['visible_frames']+=1;counts['matched_frames']+=matched;counts['missed_frames']+=not matched
            counts['off_reference_candidates']+=sum(d>ref['radius_px'] for d in distances)
        times=[row['seconds'] for (m,_),row in rows.items() if m==mode]
        counts['mean_inference_seconds']=sum(times)/len(times)
        result[mode]=counts
    return {'confidence_threshold':threshold,'modes':result,
            'scope':'Assistant-reviewed centers on development frames. Unknown visibility excluded; '
            'off-reference candidates are not exhaustively verified false positives. '
            'Candidate coverage is not temporal identity accuracy. Timings include warm-up.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--predictions',type=Path,nargs='+',required=True)
    p.add_argument('--review',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--threshold',type=float,default=.15)
    a=p.parse_args();r=score([json.loads(f.read_text()) for f in a.predictions],json.loads(a.review.read_text()),a.threshold)
    r['input_sha256']={str(f):sha256(f) for f in a.predictions+[a.review]}
    with a.output.open('x') as stream:json.dump(r,stream,indent=2)
    print(json.dumps(r['modes'],indent=2))
