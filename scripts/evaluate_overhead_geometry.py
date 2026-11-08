"""Image-only overhead calibration and stationary-field continuity audit; no media."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.calibration import CalibrationError, transform
from football_intelligence.model_assets import sha256
from football_intelligence.overhead_calibration import calibrate_overhead
from football_intelligence.pitch_paint import paint_mask
from football_intelligence.video import iter_frames

FRAMES = list(range(0,91,3))+[360,390,420,510,600,780,870]


def stationary_check(previous, current, previous_matrix, current_matrix):
    import cv2
    import numpy as np
    # Flow is estimated from pixels independently of both calibration matrices.
    scale=min(1.,1280/previous.shape[1])
    def gray(rgb):
        return cv2.cvtColor(cv2.resize(rgb,(round(rgb.shape[1]*scale),round(rgb.shape[0]*scale))),cv2.COLOR_RGB2GRAY)
    old,new=gray(previous),gray(current)
    field=np.zeros(old.shape,np.uint8)
    corners=transform(np.linalg.inv(previous_matrix),[[2,2],[103,2],[103,66],[2,66]])*scale
    cv2.fillConvexPoly(field,corners.astype(np.int32),255)
    small_rgb=cv2.resize(previous,(old.shape[1],old.shape[0]))
    # Internal field markings supply stationary structure. Avoid using moving
    # athlete corners or repeating turf texture as the dominant motion reference.
    paint=cv2.dilate(paint_mask(small_rgb).astype(np.uint8),np.ones((3,3),np.uint8))
    field[paint==0]=0
    points=cv2.goodFeaturesToTrack(old,500,.02,8,mask=field)
    if points is None or len(points)<30:
        return dict(status='unavailable',reason='insufficient_features')
    moved,forward,_=cv2.calcOpticalFlowPyrLK(old,new,points,None)
    if moved is None:
        return dict(status='unavailable',reason='flow_failed')
    returned,backward,_=cv2.calcOpticalFlowPyrLK(new,old,moved,None)
    if returned is None:
        return dict(status='unavailable',reason='reverse_flow_failed')
    keep=forward.ravel().astype(bool)&backward.ravel().astype(bool)
    keep &= np.linalg.norm((returned-points).reshape(-1,2),axis=1)<.75
    a,b=points.reshape(-1,2)[keep],moved.reshape(-1,2)[keep]
    if len(a)<30:
        return dict(status='unavailable',reason='insufficient_consistent_features')
    cv2.setRNGSeed(0)
    camera,inliers=cv2.findHomography(a,b,cv2.RANSAC,1.)
    if camera is None or inliers is None or inliers.sum()<30 or inliers.mean()<.7:
        return dict(status='unavailable',reason='inconsistent_field_motion')
    a,b=a[inliers.ravel().astype(bool)],b[inliers.ravel().astype(bool)]
    if cv2.contourArea(cv2.convexHull(a.astype(np.float32))) < .2*cv2.contourArea(corners.astype(np.float32)):
        return dict(status='unavailable',reason='concentrated_features')
    errors=np.linalg.norm(transform(previous_matrix,a/scale)-transform(current_matrix,b/scale),axis=1)
    return dict(status='checked',features=len(a),median_stationary_displacement_m=float(np.median(errors)),
                p90_stationary_displacement_m=float(np.quantile(errors,.9)))


def run(root, output, cache):
    import numpy as np
    if output.exists() or cache.exists():
        raise FileExistsError('Use unused output/cache paths')
    spec=json.loads((Path(__file__).resolve().parents[1]/'evaluations/soccertrack-sample.json').read_text())
    source=root/'D_20220220_1_0000_0030.mp4'
    expected=next(v['sha256'] for v in spec['files'] if Path(v['file']).name==source.name)
    if sha256(source)!=expected:
        raise ValueError('Unexpected source')
    records=[];previous=None;previous_calibration=None
    for frame in iter_frames(source):
        if frame.frame_index not in FRAMES:
            continue
        row=dict(frame_index=frame.frame_index,timestamp_s=frame.timestamp_s)
        try:
            calibration,evidence=calibrate_overhead(frame.rgb,match_id='overhead-audit',shot_id=0,frame_index=frame.frame_index)
            row.update(status='paint_checked',calibration=calibration.to_dict(),evidence=evidence)
            if previous_calibration is not None and frame.timestamp_s-previous.timestamp_s<.12:
                row['stationary_check']=stationary_check(previous.rgb,frame.rgb,
                                                        previous_calibration.matrix,calibration.matrix)
        except CalibrationError as exc:
            calibration=None;row.update(status='unavailable',reason=str(exc))
        records.append(row)
        previous,previous_calibration=frame,calibration
        print(f"{frame.frame_index}: {row['status']}",flush=True)
        if frame.frame_index==max(FRAMES):
            break
    if len(records)!=len(FRAMES):
        raise ValueError('Incomplete source')
    with cache.open('x') as stream:
        for row in records:stream.write(json.dumps(row,allow_nan=False)+'\n')
    checks=[r['stationary_check'] for r in records if r.get('stationary_check',{}).get('status')=='checked']
    report=dict(source_sha256=expected,cache_sha256=sha256(cache),requested_frames=FRAMES,
        stationary_feature_policy='visible internal pitch paint; forward/backward flow and robust spatially spread consensus',
        frames=len(records),paint_checked_frames=sum(r['status']=='paint_checked' for r in records),
        rejected_frames=[dict(frame_index=r['frame_index'],reason=r['reason']) for r in records if r['status']=='unavailable'],
        adjacent_reference_checks=30,stationary_checks=len(checks),
        maximum_pair_p90_stationary_displacement_m=max((r['p90_stationary_displacement_m'] for r in checks),default=None),
        median_pair_p90_stationary_displacement_m=float(np.median([r['p90_stationary_displacement_m'] for r in checks])) if checks else None,
        reference_supplied_to_predictions=False,can_certify_real_speed=False,
        limits='Full-pitch roughly axis-aligned overhead view only. Configured 105x68m dimensions. '
               'Same recording; development frames 360/390/420, other frames are within-recording checks. '
               'Stationary field flow assesses temporal consistency, not absolute accuracy or athlete contact. '
               'Image-left/right coordinates do not identify physical pitch ends or attacking direction.')
    with output.open('x') as stream:json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','output','cache'):p.add_argument(name,type=Path)
    a=p.parse_args();run(a.root,a.output,a.cache)
