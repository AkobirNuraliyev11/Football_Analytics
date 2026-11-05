"""Recover a local homography from visible L-shaped box corners."""
from itertools import product

import cv2
import numpy as np

from .calibration import CalibrationError, transform


def _stripe_edges(rgb, seed, side, pitch, detections):
    # Restrict the detector to a generous image crop around the projected box.
    end = 0 if side == "left" else pitch.length_m
    sign = 1 if side == "left" else -1
    cy = pitch.width_m/2
    corners = [[end+sign*d,cy+y] for d in (-8,24) for y in (-27,27)]
    region = transform(np.linalg.inv(seed),corners)
    h,w = rgb.shape[:2]
    x0,y0 = np.maximum(np.floor(region.min(0)).astype(int),0)
    x1,y1 = np.minimum(np.ceil(region.max(0)).astype(int),[w,h])
    if x1-x0<24 or y1-y0<24:
        return []
    crop = rgb[y0:y1,x0:x1]
    # On grass a painted line raises all three channels, including the darkest.
    light = crop.min(axis=2).copy()
    for item in detections:
        b=item['bbox']
        cv2.rectangle(light,(int(b['x_min'])-x0,int(b['y_min'])-y0),
                      (int(b['x_max'])-x0,int(b['y_max'])-y0),0,-1)
    lines=cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(light)[0]
    if lines is None:
        return []
    pixel_lines=lines.reshape(-1,2,2)+[x0,y0]
    world=transform(seed,pixel_lines.reshape(-1,2)).reshape(-1,2,2)
    segments=[]
    for p,q in world:
        delta=q-p
        axis=int(np.argmax(abs(delta)))
        if abs(delta[axis])<2 or abs(delta[1-axis])>.32*abs(delta[axis]):
            continue
        segments.append((axis,p,q))
    return segments


def box_seeds(rgb, seed, side, pitch, detections=()):
    """Match directed finite line ends, rejecting unobserved or ambiguous corners."""
    end=0 if side=="left" else pitch.length_m
    sign=1 if side=="left" else -1
    cy=pitch.width_m/2
    segments=_stripe_edges(rgb,seed,side,pitch,detections)
    corners=[]
    target=[]
    for depth,half_width in [(16.5,20.16),(5.5,9.16)]:
        for near in (-1,1):
            expected=np.array([end+sign*depth,cy+near*half_width])
            arms=[[],[]]
            for axis,p,q in segments:
                # Each arm points inward from its junction, toward the goal or the other corner.
                direction=-sign if axis==0 else -near
                tip,tail=(p,q) if (q-p)[axis]*direction>0 else (q,p)
                if np.linalg.norm(tip-expected)<=7:
                    arms[axis].append((tip,tail))
            choices=[]
            for a,b in arms[0]:
                for c,d in arms[1]:
                    if np.linalg.norm(a-c)>1.25:
                        continue
                    u,v=b-a,d-c
                    t,s=np.linalg.solve(np.column_stack([u,-v]),c-a)
                    if abs(t)*np.linalg.norm(u)>1.25 or abs(s)*np.linalg.norm(v)>1.25:
                        continue
                    cross=a+t*u
                    choices.append((np.linalg.norm(cross-expected)+np.linalg.norm(a-c),cross))
            if not choices:
                continue
            choices.sort(key=lambda item:item[0])
            clusters=[]
            for score,point in choices:
                if all(np.linalg.norm(point-other)>.5 for _,other in clusters):
                    clusters.append((score,point))
                if len(clusters)==3:
                    break
            corners.append(clusters)
            target.append(expected)
    if len(corners)<3:
        raise CalibrationError("Fewer than three supported box junctions")
    for choice in sorted(product(*corners),key=lambda group:sum(score for score,_ in group)):
        observed=[point for _,point in choice]
        try:
            correction=_correction(observed,target)
        except (CalibrationError, np.linalg.LinAlgError):
            continue
        if correction is not None:
            yield correction@seed


def _correction(observed,target):
    if len(observed)==3:
        affine=cv2.getAffineTransform(np.float32(observed),np.float32(target))
        correction=np.vstack([affine,[0,0,1]])
    else:
        correction=cv2.getPerspectiveTransform(np.float32(observed),np.float32(target))
    xy=np.array(observed)
    probe=np.vstack([xy,xy.mean(0)])
    for point in probe:
        delta=transform(correction,[point+[.1,0],point+[0,.1]])-transform(correction,[point])
        scale=np.linalg.svd(delta/.1,compute_uv=False)
        if np.linalg.det(delta)<=0 or scale.min()<.55 or scale.max()>1.8:
            return None
    return correction
