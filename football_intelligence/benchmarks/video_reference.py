"""Detection-anchor agreement with video annotations, excluding calibration error.

Reference-associated identities are not a test of tracker identity continuity.
"""
import numpy as np
from scipy.optimize import linear_sum_assignment
from ..validation import finite, integer


def summarize(values):
    return {'count':len(values),'mean':float(np.mean(values)) if values else None,
            'median':float(np.median(values)) if values else None,
            'p90':float(np.quantile(values,.9)) if values else None}


def score_frames(records, references, project, *, sample_gap_s=.500501, interval_s=1.001001001):
    """Score all declared references, retaining absent detections in the denominator."""
    finite('sample_gap_s',sample_gap_s,minimum=0)
    finite('interval_s',interval_s,minimum=0)
    if sample_gap_s == 0 or interval_s == 0:
        raise ValueError('Benchmark timing limits must be positive')
    history={};reference_history={};errors={kind:[] for kind in ('center','bottom')}
    speeds={kind:[] for kind in errors};pixels=[]
    total=matched=intervals=possible_intervals=0;last_time=None;last_index=None
    for row in records:
        t=row['timestamp_s'];index=row['frame_index']
        finite('timestamp_s',t,minimum=0)
        integer('frame_index',index)
        if last_time is not None and (t<=last_time or index<=last_index):
            raise ValueError('Benchmark frames and timestamps must increase')
        if last_time is not None and t-last_time>sample_gap_s+1e-6:
            history.clear()
            reference_history.clear()
        last_time,last_index=t,index
        truth=references[index];keys=sorted(truth)
        for key in list(reference_history):
            if key not in truth:reference_history.pop(key)
        for key in keys:
            times=reference_history.setdefault(key,[])
            while times and t-times[0]>interval_s+1e-6:times.pop(0)
            if times and abs(t-times[0]-interval_s)<1e-6:possible_intervals+=1
            times.append(t)
        total+=len(keys)
        items=[d['bbox'] for d in row['detections'] if d['kind']=='person']
        centers=np.array([[(b['x_min']+b['x_max'])/2,(b['y_min']+b['y_max'])/2] for b in items])
        assignments={}
        if len(keys) and len(items):
            cost=np.linalg.norm(np.array([truth[k] for k in keys])[:,None]-centers[None,:],axis=2)
            # Permit missing references during assignment. Assigning every row
            # first and thresholding later lets distant clutter steal good pairs.
            ii,jj=linear_sum_assignment(np.column_stack([cost,np.full((len(keys),len(keys)),40.001)]))
            for i,j in zip(ii,jj):
                if j>=len(items):
                    continue
                rivals=np.delete(cost[:,j],i)
                if cost[i,j]<=40 and (not len(rivals) or rivals.min()-cost[i,j]>=10):
                    assignments[keys[i]]=j
        for key in list(history):
            if key not in truth:history.pop(key)
        for key in keys:
            j=assignments.get(key)
            if j is None:
                history.pop(key,None)
                continue
            matched+=1;b=items[j]
            raw=[centers[j],[(b['x_min']+b['x_max'])/2,b['y_max']]]
            predicted=dict(zip(('center','bottom'),project(raw)))
            target=project([truth[key]])[0]
            pixels.append(float(np.linalg.norm(centers[j]-truth[key])))
            for kind in errors:errors[kind].append(float(np.linalg.norm(predicted[kind]-target)))
            past=history.setdefault(key,[])
            while past and t-past[0][0]>interval_s+1e-6:past.pop(0)
            if past and abs(t-past[0][0]-interval_s)<1e-6:
                previous_time,previous_target,previous_predicted=past[0]
                dt=t-previous_time
                expected=float(np.linalg.norm(target-previous_target)/dt*3.6)
                for kind in speeds:
                    actual=float(np.linalg.norm(predicted[kind]-previous_predicted[kind])/dt*3.6)
                    speeds[kind].append(abs(actual-expected))
                intervals+=1
            past.append((t,target,predicted))
    return dict(reference_observations=total,matched_observations=matched,
        unmatched_observations=total-matched,matched_fraction=matched/total if total else None,
        center_discrepancy_px=summarize(pixels),position_discrepancy_m={k:summarize(v) for k,v in errors.items()},
        interval_count=intervals,reference_interval_count=possible_intervals,
        interval_coverage=intervals/possible_intervals if possible_intervals else None,
        net_speed_discrepancy_kmh={k:summarize(v) for k,v in speeds.items()})
