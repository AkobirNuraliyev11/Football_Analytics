"""Annotation diagnostics and recording-level split guards before fine-tuning."""
from collections import Counter, defaultdict
import csv
import math
import re


def audit_soccertrack_csv(path):
    with path.open(newline='') as stream:rows=list(csv.reader(stream))
    if len(rows)<5 or (len(rows[0])-1)%4:raise ValueError('Invalid annotation table')
    columns=[]
    for col in range(1,len(rows[0]),4):
        if rows[2][col:col+4]!=['bb_height','bb_left','bb_top','bb_width']:
            raise ValueError('Unexpected box schema')
        group=rows[0][col]
        if group not in ('0','1','BALL'):raise ValueError('Unmapped annotation class')
        columns.append((col,'ball' if group=='BALL' else 'person'))
    sizes=defaultdict(Counter);last=0
    for row in rows[4:]:
        if len(row)!=len(rows[0]):raise ValueError('Incomplete annotation row')
        frame=int(row[0])
        if frame<=last:raise ValueError('Frame order must increase')
        last=frame
        for col,kind in columns:
            h,x,y,w=map(float,row[col:col+4])
            if not all(math.isfinite(v) for v in (h,x,y,w)) or min(h,w)<=0:
                raise ValueError('Invalid reference box')
            sizes[kind][(w,h)]+=1
    result={}
    for kind,counts in sizes.items():
        shape,n=counts.most_common(1)[0];total=sum(counts.values())
        result[kind]=dict(observations=total,unique_sizes=len(counts),most_common_size_px=list(shape),
                         most_common_size_count=n,most_common_size_fraction=n/total)
    return dict(frames=len(rows)-4,classes=result,
        tight_box_review_required=True,detector_training_ready=False,
        blockers=['Tight image-box semantics have not been visually approved for training',
                  'This table labels team players and ball, not exhaustive person/official instances',
                  'A separate match-level validation/test split has not been supplied'],
        note='Repeated box dimensions are a review flag, not proof of incorrect labels. '
             'These annotations remain useful for their existing center-location diagnostics.')


def validate_training_split(records):
    if not records:raise ValueError('No training sources')
    groups=defaultdict(set);hashes=defaultdict(set);partitions=set()
    for r in records:
        split=r.get('split');match=r.get('match_id');digest=r.get('source_sha256','')
        if split not in ('train','validation','test') or not isinstance(match,str) or not match.strip():
            raise ValueError('Each source needs a match ID and valid split')
        if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):
            raise ValueError('Each source needs a SHA-256 fingerprint')
        if r.get('box_semantics')!='tight_box' or r.get('annotation_complete') is not True:
            raise ValueError('Training requires reviewed tight boxes and complete target annotations')
        groups[match].add(split);hashes[digest].add(split);partitions.add(split)
    if any(len(s)>1 for s in groups.values()):raise ValueError('Same match crosses split boundaries')
    if any(len(s)>1 for s in hashes.values()):raise ValueError('Same source crosses split boundaries')
    if partitions!={'train','validation','test'}:raise ValueError('Need separate train, validation and test sources')
    return {'status':'split_metadata_valid','matches':len(groups),'sources':len(records),
            'note':'Metadata checks only; does not certify label accuracy, rights or absence of model pretraining overlap.'}
