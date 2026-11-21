"""Targeted classification review on fixed observed crops, not identity/detection accuracy."""
from collections import Counter
import math


def score_classification_review(document, frames, *, source_sha256):
    if document.get('source_sha256') != source_sha256:
        raise ValueError('Reference video fingerprint mismatch')
    references=document.get('observations', [])
    if not references or not document.get('review_method'):
        raise ValueError('Reviewed observations and review method required')
    selected={}
    for ref in references:
        key=(ref['frame_index'],ref['source_track_id'])
        if key in selected:raise ValueError('Duplicate reference crop')
        if ref.get('role') not in {'outfield','official','goalkeeper'}:
            raise ValueError('Reference role required')
        if ref.get('team') not in {'A','B','not_applicable'}:
            raise ValueError('Reference team or explicit not_applicable required')
        if ref['role']=='official' and ref['team']!='not_applicable':
            raise ValueError('Officials cannot have a team reference')
        b=ref['bbox'];coords=[b[k] for k in ('x_min','y_min','x_max','y_max')]
        if not all(math.isfinite(v) for v in coords) or coords[2]<=coords[0] or coords[3]<=coords[1]:
            raise ValueError('Invalid reference crop')
        selected[key]=ref
    predictions={}; seen_frames=set()
    for frame in frames:
        index=frame['frame_index']
        if index in seen_frames:raise ValueError('Duplicate prediction frame')
        seen_frames.add(index)
        keys=set()
        for item in frame['detections']:
            if item.get('kind')!='person':continue
            key=(index,item.get('source_track_id',item['track_id']))
            if key in keys:raise ValueError('Duplicate prediction crop')
            keys.add(key)
            if key not in selected:continue
            # Numeric IDs are lookup keys only. Changed tracking boxes require
            # a separate identity/box evaluation, not reusing these crop labels.
            if any(not math.isfinite(item['bbox'][k]) or abs(item['bbox'][k]-v)>1e-6
                   for k,v in selected[key]['bbox'].items()):
                raise ValueError('Prediction crop differs from reviewed crop')
            predictions[key]=item
    role=Counter(correct=0,wrong=0,unknown=0,missing=0)
    team=Counter(correct=0,wrong=0,unknown=0,missing=0)
    official_total=official_wrong_team=0
    for key,ref in selected.items():
        pred=predictions.get(key)
        for field,counts in [('role',role),('team',team)]:
            if field=='team' and ref['team']=='not_applicable':continue
            value=pred.get(field,'unknown') if pred else None
            counts['missing' if pred is None else 'unknown' if value in (None,'unknown')
                   else 'correct' if value==ref[field] else 'wrong']+=1
        if ref['role']=='official':
            official_total+=1
            official_wrong_team+=bool(pred and pred.get('team') in {'A','B'})
    def metrics(counts):
        total=sum(counts.values())
        return dict(counts,total=total,accuracy_including_unknown_and_missing=counts['correct']/total if total else None)
    return dict(role=metrics(role),team=metrics(team),official_observations=official_total,
                official_wrong_team=official_wrong_team,review_method=document['review_method'],
                source_sha256=source_sha256,acceptance_status='not_certified',
                scope='Selected fixed crops only. No detection, tracking identity, physical speed, '
                      'event, held-out or overall 86% accuracy claim. Unknown/missing remain errors.')
