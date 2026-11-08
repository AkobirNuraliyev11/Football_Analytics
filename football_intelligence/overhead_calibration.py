"""Image-only full-pitch calibration for roughly axis-aligned overhead views.

Explicitly abstains on partial views. Pitch dimensions are configured assumptions;
image consistency does not establish athlete ground contact or metric accuracy.
"""
from dataclasses import replace
from itertools import combinations, product
from .calibration import CalibrationError, Landmark, fit_calibration
from .config import PitchConfig
from .models import PixelPoint, PitchPoint
from .pitch_paint import paint_mask, paint_evidence


def _refine_corners(rgb, corners):
    """Fit native-resolution paint ridges around the proposed four boundaries."""
    import cv2
    import numpy as np
    ys,xs=np.where(paint_mask(rgb))
    pixels=np.column_stack([xs,ys]).astype(float)
    lines=[]
    radius=max(3.,rgb.shape[1]/320.)
    for a,b in zip(corners,np.roll(corners,-1,axis=0)):
        delta=b-a;length=np.linalg.norm(delta);direction=delta/length
        relative=pixels-a
        along=relative@direction
        perpendicular=np.abs(relative[:,0]*direction[1]-relative[:,1]*direction[0])
        selected=pixels[(along>0)&(along<length)&(perpendicular<radius)]
        if len(selected)<100:
            raise CalibrationError('Insufficient native boundary paint')
        vx,vy,x,y=cv2.fitLine(selected.astype(np.float32),cv2.DIST_HUBER,0,.01,.01).ravel()
        lines.append(np.array([-vy,vx,vy*x-vx*y],float))
    refined=[]
    for previous,current in zip(np.roll(lines,1,axis=0),lines):
        crossing=np.cross(previous,current)
        if abs(crossing[2])<1e-8:
            raise CalibrationError('Parallel overhead boundaries')
        refined.append(crossing[:2]/crossing[2])
    refined=np.array(refined)
    if np.linalg.norm(refined-corners,axis=1).max()>2*radius:
        raise CalibrationError('Unstable native boundary refinement')
    return refined


def _boundary_candidate(rgb, *, match_id, shot_id, frame_index, pitch=None):
    import cv2
    import numpy as np
    pitch = pitch or PitchConfig()
    height, width = rgb.shape[:2]
    scale = min(1., 1280/width)
    small = cv2.resize(rgb, (round(width*scale), round(height*scale))) if scale < 1 else rgb
    h, w = small.shape[:2]
    mask = paint_mask(small).astype(np.uint8)*255
    segments = cv2.HoughLinesP(mask, 1, np.pi/1800, threshold=80,
                              minLineLength=min(w,h)*.4, maxLineGap=20)
    if segments is None:
        raise CalibrationError('Overhead view needs four visible pitch boundaries')
    horizontal, vertical = [], []
    for x1,y1,x2,y2 in segments.reshape(-1,4).astype(float):
        dx,dy=x2-x1,y2-y1
        if abs(dx) > w*.45 and abs(dy) < .15*abs(dx):
            # y = slope*x + intercept
            horizontal.append((dy/dx, y1-dy/dx*x1))
        if abs(dy) > h*.45 and abs(dx) < .15*abs(dy):
            # x = slope*y + intercept
            vertical.append((dx/dy, x1-dx/dy*y1))
    if len(horizontal)<2 or len(vertical)<2:
        raise CalibrationError('Overhead boundary directions unavailable')
    def groups(lines, midpoint):
        clustered=[]
        for line in sorted(lines,key=lambda v:v[0]*midpoint+v[1]):
            if not clustered or abs(np.mean([v[0]*midpoint+v[1] for v in clustered[-1]])-
                                    (line[0]*midpoint+line[1]))>8:
                clustered.append([])
            clustered[-1].append(line)
        return [np.median(group,axis=0) for group in clustered]
    horizontal,vertical=groups(horizontal,w/2),groups(vertical,h/2)
    if len(horizontal)>8 or len(vertical)>12:
        raise CalibrationError('Too many competing overhead boundary lines')
    def intersect(horizontal,vertical):
        a,b=horizontal;c,d=vertical
        y=(a*d+b)/(1-a*c)
        return [c*y+d,y]
    locations=[(0,0),(pitch.length_m,0),(pitch.length_m,pitch.width_m),(0,pitch.width_m)]
    candidates=[]
    for (top,bottom),(left,right) in product(combinations(horizontal,2),combinations(vertical,2)):
        corners=np.array([intersect(top,left),intersect(top,right),
                          intersect(bottom,right),intersect(bottom,left)])
        if (not np.isfinite(corners).all() or (corners<0).any() or
            (corners[:,0]>=w).any() or (corners[:,1]>=h).any() or
            cv2.contourArea(corners.astype(np.float32)) < .35*w*h):
            continue
        if len(candidates)>=128:
            raise CalibrationError('Too many plausible overhead perimeters')
        matrix=cv2.getPerspectiveTransform(corners.astype(np.float32),np.array(locations,np.float32))
        check=paint_evidence(small,matrix,corners,pitch)
        # Select by midfield only. Penalty-front checks remain outside selection.
        midfield=[check['components'].get(name,{}).get('fraction',0.) for name in ('circle','halfway')]
        candidates.append((min(midfield),check['supported_fraction'],corners))
    if not candidates:
        raise CalibrationError('Overhead perimeter is incomplete or too small')
    candidates.sort(key=lambda v:(v[0],v[1]),reverse=True)
    checks=('circle','halfway','left_penalty_front','right_penalty_front')
    first=None
    for attempt,(_,_,corners) in enumerate(candidates[:8],1):
        corners=corners/scale
        try:
            corners=_refine_corners(rgb,corners)
        except CalibrationError:
            continue
        landmarks=[Landmark(f'boundary-{i}',PixelPoint(*map(float,p)),PitchPoint(*q))
                   for i,(p,q) in enumerate(zip(corners,locations))]
        calibration=fit_calibration(landmarks,match_id=match_id,shot_id=shot_id,
            frame_index=frame_index,width=width,height=height,pitch=pitch)
        evidence=paint_evidence(rgb,calibration.matrix,corners,pitch)
        internal={name:evidence['components'].get(name,{}).get('fraction',0.) for name in checks}
        evidence.update(method='full_pitch_boundaries',internal_marking_support=internal,
                        hypotheses_checked=attempt,
                        orientation='image-left to image-right; physical pitch ends unverified',
                        pitch_dimensions_assumed=True,
                        selection_note='Internal markings select and screen hypotheses; not independent accuracy validation')
        candidate=replace(calibration,method='overhead_boundaries_candidate'),evidence
        if first is None:
            first=candidate
        if evidence['accepted'] and min(internal.values())>=.65:
            return candidate
    if first is None:
        raise CalibrationError('No stable native overhead perimeter')
    return first


def calibrate_overhead(rgb, **scope):
    calibration,evidence = _boundary_candidate(rgb, **scope)
    if not evidence['accepted'] or min(evidence['internal_marking_support'].values()) < .65:
        raise CalibrationError('Overhead perimeter disagrees with internal pitch markings')
    return replace(calibration,method='overhead_boundaries_paint_checked',image_evidence=evidence),evidence
