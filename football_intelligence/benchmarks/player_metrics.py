"""Box-based player metrics on exhaustively labeled frames of one recording.

Reference IDs must name real people across frames, not copied prediction IDs.
Team labels must use a fixed reviewed mapping. Unknown/missing labels count as errors.
"""
from collections import Counter
import math
import numpy as np
from scipy.optimize import linear_sum_assignment


def _box(item):
    b=item['bbox'];v=[b[k] for k in ('x_min','y_min','x_max','y_max')]
    if not all(math.isfinite(x) for x in v) or v[2]<=v[0] or v[3]<=v[1]:
        raise ValueError('Invalid evaluation box')
    return np.array(v,dtype=float)


def _iou(a,b):
    intersection=np.maximum(0,np.minimum(a[2:],b[2:])-np.maximum(a[:2],b[:2])).prod()
    return float(intersection/((a[2:]-a[:2]).prod()+(b[2:]-b[:2]).prod()-intersection))


def score_players(frames, iou_threshold=.5):
    if not 0<iou_threshold<=1:raise ValueError('Invalid IoU threshold')
    if not frames:raise ValueError('No labeled frames')
    gt_counts=Counter();pred_counts=Counter();potential=Counter()
    total_gt=total_pred=tp=correct_role=team_total=correct_team=0
    last=-1
    for frame in frames:
        if frame['frame_index']<=last:raise ValueError('Frames must strictly increase')
        last=frame['frame_index']
        if frame.get('annotation_complete') is not True:
            raise ValueError('Exhaustive annotations required in evaluation region')
        truth=frame['references'];pred=frame['predictions']
        for items in (truth,pred):
            if len({i['identity'] for i in items})!=len(items):raise ValueError('Duplicate identity within frame')
        for r in truth:
            if r.get('role') not in ('outfield','official','goalkeeper'):raise ValueError('Reference role missing')
        gb=[_box(x) for x in truth];pb=[_box(x) for x in pred]
        gt_counts.update(r['identity'] for r in truth);pred_counts.update(r['identity'] for r in pred)
        total_gt+=len(truth);total_pred+=len(pred)
        team_total+=sum(r.get('team') in ('A','B') for r in truth)
        scores=np.array([[_iou(a,b) for b in pb] for a in gb]).reshape(len(gb),len(pb))
        for i,j in zip(*np.where(scores>=iou_threshold)):
            potential[truth[i]['identity'],pred[j]['identity']]+=1
        if not gb or not pb:continue
        # Maximize admissible match count first, then IoU; dummies retain misses.
        dummy=min(len(gb),len(pb))+1
        costs=np.where(scores>=iou_threshold,1-scores,1e6)
        rows,cols=linear_sum_assignment(np.column_stack([costs,np.full((len(gb),len(gb)),dummy)]))
        for i,j in zip(rows,cols):
            if j>=len(pb) or scores[i,j]<iou_threshold:continue
            tp+=1
            correct_role+=truth[i]['role']==pred[j].get('role')
            correct_team+=truth[i].get('team') in ('A','B') and truth[i]['team']==pred[j].get('team')
    # Global one-to-one identity assignment over all labeled frames.
    gids=list(gt_counts);pids=list(pred_counts);idtp=0
    if gids and pids:
        overlap=np.array([[potential[g,p] for p in pids] for g in gids])
        rows,cols=linear_sum_assignment(-overlap)
        idtp=int(overlap[rows,cols].sum())
    def ratio(a,b):return a/b if b else None
    return dict(reference_observations=total_gt,predicted_observations=total_pred,
                true_positives=tp,false_positives=total_pred-tp,false_negatives=total_gt-tp,
                precision=ratio(tp,total_pred),recall=ratio(tp,total_gt),
                idtp=idtp,idfp=total_pred-idtp,idfn=total_gt-idtp,
                idf1=ratio(2*idtp,total_gt+total_pred),
                role_accuracy_including_misses=ratio(correct_role,total_gt),
                team_reference_observations=team_total,team_accuracy_including_misses=ratio(correct_team,team_total),
                iou_threshold=iou_threshold,
                scope='Exhaustively labeled evaluation frames only; ignore regions and crowd boxes unsupported. '
                'Unknown labels and missed references count as errors. Does not establish held-out status, '
                'label accuracy, physical measurements or meeting the 86% target on other recordings.')
