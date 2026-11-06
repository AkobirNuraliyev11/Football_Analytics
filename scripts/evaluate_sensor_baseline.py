"""Conditional sensor comparison using reference geometry and reference-associated identities.

Not end-to-end product validation. Fits identities and a clock offset on seconds 2-5,
then evaluates detector anchors on seconds 10-28. No media is produced.
"""
import argparse
import ast
import csv
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from football_intelligence.benchmarks.sensor_reference import read_gnss, SensorSeries
from football_intelligence.model_assets import sha256


def mapper(path):
    pairs=json.loads(path.read_text())
    src=np.array(list(pairs.values()),float)
    dst=np.array([ast.literal_eval(key) for key in pairs],float)
    center,scale=src.mean(0),src.std(0)
    normalized=(src-center)/scale
    cv2.setRNGSeed(0)
    matrix,mask=cv2.findHomography(normalized,dst,cv2.RANSAC,.5)
    if matrix is None:raise ValueError('Reference geometry unavailable')
    def project(points):
        return cv2.perspectiveTransform(((np.array(points,float)-center)/scale)[None],matrix)[0]
    errors=np.linalg.norm(project(src)-dst,axis=1)
    return project,dict(points=len(src),inliers=int(mask.sum()),median_fit_error_m=float(np.median(errors)),
                        maximum_fit_error_m=float(errors.max()))


def annotations(path,rate):
    rows=list(csv.reader(path.open()))
    result={}
    for col in range(1,len(rows[0]),4):
        if rows[2][col:col+4]!=['bb_height','bb_left','bb_top','bb_width']:
            raise ValueError('Unexpected bounding-box columns')
        key=rows[0][col],rows[1][col]
        points=[]
        for row in rows[4:]:
            h,x,y,w=map(float,row[col:col+4]);points.append(((int(row[0])-1)/rate,(x+w/2,y+h/2)))
        result[key]=SensorSeries(points,max_gap_s=1/rate+1e-6)
    return result


def align(gnss,boxes,project):
    # Establish a single per-team bijection on setup data only. Not per-frame nearest GPS.
    grid=np.arange(2.,5.,.1)
    pairings=[]
    for team in ('0','1'):
        gkeys=sorted(k for k in gnss if k[0]==team)
        bkeys=sorted(k for k in boxes if k[0]==team)
        cost=np.full((len(gkeys),len(bkeys)),1e6)
        for i,g in enumerate(gkeys):
            for j,b in enumerate(bkeys):
                pairs=[(gnss[g].sample(float(t)),boxes[b].sample(float(t))) for t in grid]
                pairs=[(a,b) for a,b in pairs if a is not None and b is not None]
                if len(pairs)>=15:
                    cost[i,j]=np.mean(np.linalg.norm(np.array([a for a,_ in pairs])-project([b for _,b in pairs]),axis=1))
        ii,jj=linear_sum_assignment(cost)
        pairings.extend((gkeys[i],bkeys[j]) for i,j in zip(ii,jj) if cost[i,j]<1e5)
    # Fit time from motion, not from spatial biases of individual wearables.
    scores=[]
    for offset in np.round(np.arange(-1.,3.001,.05),6):
        errors=[]
        for g,b in pairings:
            for t in np.arange(2.,4.5,.1):
                sample=gnss[g].interval(float(t+offset),float(t+offset+.5))
                bb=boxes[b].interval(float(t),float(t+.5))
                if sample is None or bb is None:continue
                gps=np.array(sample);camera=project(bb)
                errors.append(np.linalg.norm((gps[1]-gps[0])-(camera[1]-camera[0]))/.5)
        if len(errors)>=100:scores.append((float(np.median(errors)),float(offset),len(errors)))
    if not scores:raise ValueError('Insufficient independent setup motion')
    scores.sort()
    return pairings,scores[0],scores[:5]


def stats(values):
    return dict(count=len(values),median=float(np.median(values)) if values else None,
                mean=float(np.mean(values)) if values else None,p90=float(np.quantile(values,.9)) if values else None)


def evaluate(root,cache):
    files=[root/'G_20200220_1_0000_0030.csv',root/'gnss_keypoints.json',root/'drone_keypoints.json',
           root/'D_20220220_1_0000_0030.csv',cache]
    proof_path=cache.with_suffix('.manifest.json')
    proof=json.loads(proof_path.read_text())
    expected=json.loads((Path(__file__).resolve().parents[1]/'evaluations/soccertrack-sample.json').read_text())
    expected_video=next(r['sha256'] for r in expected['files'] if r['file'].endswith('.mp4'))
    if proof.get('status')!='completed' or proof.get('detections_sha256')!=sha256(cache) or proof.get('source_sha256')!=expected_video:
        raise ValueError('Need completed detector cache for the pinned source')
    files.append(proof_path)
    hashes={str(p):sha256(p) for p in files}
    gp,gfit=mapper(files[1]);bp,bfit=mapper(files[2]);origin,raw=read_gnss(files[0])
    gps={k:SensorSeries(list(zip(s.times,gp(s.points))),s.max_gap_s) for k,s in raw.items()}
    # Preserve removed conflicts as explicit boundaries after geographic conversion.
    for k in gps:gps[k].conflicts=raw[k].conflicts
    boxes=annotations(files[3],29.97)
    pairing,best,alternatives=align(gps,boxes,bp)
    offset=best[1];lookup={b:g for g,b in pairing}
    records=sorted((json.loads(line) for line in cache.read_text().splitlines()),key=lambda r:r['frame_index'])
    records=[r for r in records if 10 <= r['timestamp_s'] <= 28 and r['frame_index']%15==0]
    if len({r['frame_index'] for r in records})!=len(records):raise ValueError('Duplicate cached frame')
    positions={'bottom':[],'center':[]};counts=dict(reference_observations=0,sensor_available=0,detector_matched=0,detected_people_total=0)
    history={};speed={'bottom':[],'center':[]}
    annotation_sensor=[];detector_annotation=[]
    for row in records:
        t=row['timestamp_s'];keys=sorted(lookup)
        truth=[boxes[k].sample(t) for k in keys]
        if any(p is None for p in truth):raise ValueError('Annotation timestamp unavailable')
        detections=[d['bbox'] for d in row['detections'] if d['kind']=='person']
        counts['detected_people_total']+=len(detections)
        centers=np.array([[(d['x_min']+d['x_max'])/2,(d['y_min']+d['y_max'])/2] for d in detections])
        matched={}
        if len(centers):
            cost=np.linalg.norm(np.array(truth)[:,None]-centers[None,:],axis=2)
            ii,jj=linear_sum_assignment(cost)
            for i,j in zip(ii,jj):
                # A reference identity only attaches to a nearby unambiguous detection.
                rivals=np.delete(cost[:,j],i)
                if cost[i,j]<=40 and (not len(rivals) or rivals.min()-cost[i,j]>=10):matched[keys[i]]=detections[j]
        for key in keys:
            counts['reference_observations']+=1
            sensor=gps[lookup[key]].sample(t+offset)
            if sensor is not None:counts['sensor_available']+=1
            d=matched.get(key);predicted=None
            if d is not None and sensor is not None:
                counts['detector_matched']+=1
                anchors=[[(d['x_min']+d['x_max'])/2,d['y_max']],[(d['x_min']+d['x_max'])/2,(d['y_min']+d['y_max'])/2]]
                mapped=bp(anchors);predicted=dict(zip(('bottom','center'),mapped))
                annotated=bp([boxes[key].sample(t)])[0]
                annotation_sensor.append(float(np.linalg.norm(annotated-sensor)))
                detector_annotation.append(float(np.linalg.norm(predicted['center']-annotated)))
                for kind in positions:positions[kind].append(float(np.linalg.norm(predicted[kind]-sensor)))
            entry=dict(time=t,predicted=predicted)
            old=history.setdefault(key,[])
            # Half-second sampling, require all intervening detections and sensor samples.
            if len(old)>=2:
                a,middle=old[-2:];dt=t-a['time']
                if abs(dt-30/29.97)<1e-6 and predicted is not None and a['predicted'] is not None and middle['predicted'] is not None:
                    pair=gps[lookup[key]].interval(a['time']+offset,t+offset)
                    if pair is not None:
                        expected=float(np.linalg.norm(np.array(pair[1])-pair[0])/dt*3.6)
                        for kind in speed:
                            actual=float(np.linalg.norm(predicted[kind]-a['predicted'][kind])/dt*3.6)
                            speed[kind].append(abs(actual-expected))
            old.append(entry)
    if any(sha256(Path(p))!=digest for p,digest in hashes.items()):raise ValueError('Input changed')
    return dict(reference_kind='secondary_gnss_comparison',comparison_is_accuracy_test=False,validation_status='diagnostic_only',can_certify_real_speed=False,input_sha256=hashes,setup_seconds=[2,5],evaluation_seconds=[10,28],frames=len(records),
        alignment=dict(video_to_gnss_relative_offset_s=offset,setup_median_velocity_difference_mps=best[0],setup_pairs=best[2],
                       leading_offset_candidates=alternatives,identity_pairs=[dict(sensor=g,video=b) for g,b in pairing],status='provisional_not_independently_clock_verified'),
        reference_fits=dict(gnss=gfit,drone=bfit),coverage=counts,
        paired_reference_disagreement_m=stats(annotation_sensor),
        paired_detector_center_to_annotation_m=stats(detector_annotation),
        position_discrepancy_m={k:stats(v) for k,v in positions.items()},interval_speed_discrepancy_kmh={k:stats(v) for k,v in speed.items()},
        scope='Conditional diagnostic using provided reference geometry and annotation-associated identities. '
              'Clock inferred only on setup segment. GNSS-derived box annotations used for alignment and identity only. '
              'Predicted positions come from detector boxes. Sensor error, clock error, camera drift and wearable/foot offsets remain. '
              'Not an end-to-end accuracy certification or validated ground-contact result.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','detections','output'):p.add_argument(name,type=Path)
    a=p.parse_args();result=evaluate(a.root,a.detections)
    with a.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:result[k] for k in ['frames','coverage','position_discrepancy_m','interval_speed_discrepancy_kmh']},indent=2))
