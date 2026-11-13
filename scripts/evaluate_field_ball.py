"""Paired ball-region trial on pinned caches, without model inference."""
import csv,json,sys
from pathlib import Path
from dataclasses import asdict
from math import hypot
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.ball_selection import BallSelector
from football_intelligence.benchmarks.field_context import ball_region
from football_intelligence.detection import Detection
from football_intelligence.models import BoundingBox
from football_intelligence.tracking import MultiObjectTracker
from football_intelligence.video import iter_frames
from football_intelligence.model_assets import sha256


def run(output, ball_motion_fraction=0.):
    root=Path('data/soccertrack-reference');cache=root/'detections-tiled-dense.jsonl'
    source=root/'D_20220220_1_0000_0030.mp4';labels=root/'D_20220220_1_0000_0030.csv'
    geometry=Path('data/overhead-geometry-final.jsonl')
    spec=json.loads(Path('evaluations/soccertrack-sample.json').read_text())
    pins={Path(r['file']).name:r['sha256'] for r in spec['files']}
    proof=json.loads(cache.with_suffix('.manifest.json').read_text())
    if sha256(source)!=pins[source.name] or sha256(labels)!=pins[labels.name] or sha256(cache)!=proof['detections_sha256'] or proof['status']!='completed':
        raise ValueError('Benchmark provenance mismatch')
    rows={r['frame_index']:r for r in map(json.loads,cache.read_text().splitlines())}
    fits={r['frame_index']:r for r in map(json.loads,geometry.read_text().splitlines())}
    if sorted(rows)!=list(range(0,91,3)):raise ValueError('Unexpected dense frames')
    tracker=MultiObjectTracker(ball_motion_fraction=ball_motion_fraction);selectors={k:BallSelector() for k in ('before','field_context')}
    predictions=[]
    for frame in iter_frames(source):
        if frame.frame_index not in rows:continue
        row=rows[frame.frame_index];fit=fits[frame.frame_index]
        if abs(row['timestamp_s']-frame.timestamp_s)>1e-6 or abs(fit['timestamp_s']-frame.timestamp_s)>1e-6:raise ValueError('Timing mismatch')
        detections=[Detection(BoundingBox(**d['bbox']),d['confidence'],d['kind']) for d in row['detections']]
        tracked=[dict(track_id=t.track_id,kind=t.detection.kind,confidence=t.detection.confidence,bbox=asdict(t.detection.bbox))
                 for t,_ in tracker.update(detections,frame.rgb,timestamp_s=frame.timestamp_s,shot_id=0)]
        contextual=[d for d in tracked if d['kind']!='ball' or ball_region(d['bbox'],fit['calibration'],frame_index=frame.frame_index,width=frame.rgb.shape[1],height=frame.rgb.shape[0])!='outside_supported_pitch']
        selected={}
        for key,items in [('before',tracked),('field_context',contextual)]:
            result=selectors[key].update(items,timestamp_s=frame.timestamp_s,shot_id=0)
            selected[key]=next((d['bbox'] for d in items if d['track_id']==result['selected_track_id']),None)
        predictions.append(dict(frame_index=frame.frame_index,timestamp_s=frame.timestamp_s,selected=selected,raw=row['detections'],tracked=tracked))
        if frame.frame_index==90:break
    # Annotation data enters only after prediction and selection.
    table=list(csv.reader(labels.open()));col=table[0].index('BALL')
    scores={k:dict(correct=0,wrong=0,unresolved=0) for k in selectors}
    misses=0
    refs={}
    for p in predictions:
        r=table[p['frame_index']+4];h,x,y,w=map(float,r[col:col+4]);truth=(x+w/2,y+h/2)
        if h<=0 or w<=0:raise ValueError('Missing ball reference')
        def distance(b):return hypot((b['x_min']+b['x_max'])/2-truth[0],(b['y_min']+b['y_max'])/2-truth[1])
        misses+=not any(distance(d['bbox'])<=10 for d in p['raw'] if d['kind']=='ball')
        for key,b in p['selected'].items():scores[key]['unresolved' if b is None else 'correct' if distance(b)<=10 else 'wrong']+=1
        refs[p['frame_index']]={}
        for c in range(1,len(table[0]),4):
            if table[0][c] in ('0','1'):
                hh,xx,yy,ww=map(float,r[c:c+4]);refs[p['frame_index']][(table[0][c],table[1][c])]=[xx+ww/2,yy+hh/2]
    from football_intelligence.benchmarks.tracking_reference import score_tracking
    funnel={}
    for key in ('raw','tracked'):
        scoring=[dict(frame_index=p['frame_index'],timestamp_s=p['timestamp_s'],detections=[
            d|dict(track_id=p['frame_index']*1000+j,confirmed=False,continuity_safe=False,continuity_segment=0)
            for j,d in enumerate(p[key])]) for p in predictions]
        funnel[key]=score_tracking(scoring,refs)['matched_observations']
    report=dict(person_observation_funnel=funnel,ball_motion_fraction=ball_motion_fraction,frames=len(predictions),ball_center_tolerance_px=10,ball_raw_missed_frames=misses,selection=scores,
        player_reference_observations=sum(map(len,refs.values())),player_raw_matched_observations=funnel['raw'],
        hashes={str(p):sha256(p) for p in (source,labels,cache,geometry)},
        scope='Same-recording development diagnostic, publisher image annotations. No labels enter prediction. '
              'Player funnel uses symmetric 40px/10px matching. Region screen requires current paint-checked overhead geometry. No physical accuracy or held-out claim.')
    with output.open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2))

if __name__=='__main__':run(Path(sys.argv[1]),float(sys.argv[2]) if len(sys.argv)>2 else 0.)
