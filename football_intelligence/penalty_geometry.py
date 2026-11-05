"""Experimental local paint check. Only the area enclosed by visible markings is supported."""
from dataclasses import dataclass

import cv2
import numpy as np

from .calibration import CalibrationError, transform
from .config import PitchConfig


@dataclass
class PenaltyMap:
    matrix: np.ndarray
    hull: np.ndarray
    residual_m: float
    supported_lines: int

    alternatives: tuple = ()

    def project(self, pixel):
        xy = transform(self.matrix, [pixel])[0]
        inside = cv2.pointPolygonTest(self.hull, tuple(map(float, xy)), False)
        if inside < 0:
            raise CalibrationError("Outside observed penalty-area markings")
        if self.alternatives:
            predictions = np.vstack([xy]+[other.project(pixel) for other in self.alternatives])
            if np.linalg.norm(predictions[:,None]-predictions[None,:],axis=2).max()>.6:
                raise CalibrationError("Competing box alignments disagree at this point")
        return xy


def markings(pitch, side):
    if side not in {"left", "right"}:
        raise ValueError("Expected left or right penalty area")
    cy = pitch.width_m / 2
    def x(depth):
        return depth if side == "left" else pitch.length_m - depth
    # Each tuple holds the constant axis, its value, and the other axis limits.
    lines = [(0, x(0), cy-20.16, cy+20.16)]
    for depth, half_width in [(16.5, 20.16), (5.5, 9.16)]:
        lines.append((0, x(depth), cy-half_width, cy+half_width))
        for y in [cy-half_width, cy+half_width]:
            lines.append((1, y, min(x(0),x(depth)), max(x(0),x(depth))))
    return lines


def _check_paint(rgb, seed, side, detections=(), pitch=None, *, adaptive=False):
    """Check a seed against local stripe centers, reserving alternating 2 m strips."""
    pitch = pitch or PitchConfig()
    h, w = rgb.shape[:2]
    inverse = np.linalg.inv(seed)
    offsets = np.linspace(-1.2, 1.2, 49)
    supported = []
    for axis, level, low, high in markings(pitch, side):
        along = np.arange(low+.4, high-.4, .35)
        shape = (len(along), len(offsets))
        world = np.empty((*shape, 2))
        world[:,:,axis] = level + offsets
        world[:,:,1-axis] = along[:,None]
        pixels = transform(inverse, world.reshape(-1,2)).reshape(*shape,2)
        if adaptive:
            # Perspective can send a ground-axis probe almost along the painted stripe.
            # Sample across its image normal with grass on both sides of the paint.
            centers = pixels[:,len(offsets)//2]
            tangent = centers[-1]-centers[0]
            normal = np.array([-tangent[1],tangent[0]]) / np.linalg.norm(tangent)
            pixels = centers[:,None,:] + np.linspace(-6,6,len(offsets))[None,:,None]*normal
            sampled_world = transform(seed,pixels.reshape(-1,2)).reshape(*shape,2)
        px, py = pixels[:,:,0], pixels[:,:,1]
        good = ((px>=1)&(px<w-2)&(py>=1)&(py<h-2)).all(axis=1)
        for item in detections:
            b = item["bbox"]
            good &= ~((px>=b["x_min"]-2)&(px<=b["x_max"]+2)&
                      (py>=b["y_min"]-2)&(py<=b["y_max"]+2)).any(axis=1)
        colors = cv2.remap(rgb,px.astype("f"),py.astype("f"),cv2.INTER_LINEAR).astype(float)
        points, blocks = [], []
        for i in np.flatnonzero(good):
            profile = colors[i]
            edges = np.vstack((profile[:4],profile[-4:]))
            # A paint stripe must rise above the grass on both sides.
            if np.median(edges[:,1]-edges[:,0]) < 6:
                continue
            light = profile.min(axis=1)
            background = max(np.median(light[:4]), np.median(light[-4:]))
            contrast = 18
            if adaptive:
                noise = max(np.std(light[:4]),np.std(light[-4:]))
                contrast = max(8.,4*noise)
            hot = np.flatnonzero(light > background+contrast)
            if not len(hot) or hot[0]<4 or hot[-1]>44 or np.any(np.diff(hot)>1):
                continue
            if hot[-1]-hot[0] > (16 if adaptive else 9):
                continue
            weights = light[hot]-background
            if adaptive:
                point = np.average(sampled_world[i,hot],axis=0,weights=weights)
                if abs(point[axis]-level)>1.2:
                    continue
            else:
                center = np.average(offsets[hot],weights=weights)
                point = [0.,0.]
                point[axis], point[1-axis] = level+center, along[i]
            points.append(point)
            blocks.append(int((along[i]-low)//2))
        if len(points)<7 or len(set(blocks))<3:
            continue
        pts = np.array(points)
        train = np.array(blocks)%2 == 0
        if train.sum()>=4 and (~train).sum()>=3:
            supported.append((axis, level, pts, train))
    if any(sum(line[0]==axis for line in supported)<2 for axis in (0,1)):
        raise CalibrationError("Need two visible markings in each pitch direction")
    correction = np.eye(3)
    for axis in (0,1):
        rows = [(level, pts[train]) for a,level,pts,train in supported if a==axis]
        pts = np.concatenate([p for _,p in rows])
        expected = np.concatenate([np.full(len(p),level) for level,p in rows])
        design = np.column_stack([pts,np.ones(len(pts))])
        coef,_,rank,_ = np.linalg.lstsq(design,expected,rcond=None)
        if rank<3:
            raise CalibrationError("Degenerate local paint support")
        correction[axis] = coef
    all_pts = np.concatenate([p for _,_,p,_ in supported])
    fitted = transform(correction,all_pts)
    if np.linalg.norm(fitted-all_pts,axis=1).max()>1.2 or np.linalg.det(correction[:2,:2])<=0:
        raise CalibrationError("Unstable local correction")
    error = max(np.quantile(abs(transform(correction,p[~t])[:,a]-level),.9)
                for a,level,p,t in supported)
    if error>.30:
        raise CalibrationError("Local paint check failed")
    hull = cv2.convexHull(fitted.astype("f"))
    if cv2.contourArea(hull)<35:
        raise CalibrationError("Insufficient enclosed paint support")
    return PenaltyMap(correction@seed,hull,float(error),len(supported))


def check_penalty_area(rgb, seed, side, detections=(), pitch=None):
    """Keep the original paint check and recover displaced seeds using observed junctions."""
    from .box_alignment import box_seeds
    pitch = pitch or PitchConfig()
    try:
        return _check_paint(rgb, seed, side, detections, pitch)
    except CalibrationError:
        pass
    accepted = []
    for improved in box_seeds(rgb, seed, side, pitch, detections):
        try:
            accepted.append(_check_paint(rgb, improved, side, detections, pitch, adaptive=True))
        except CalibrationError:
            continue
    if not accepted:
        raise CalibrationError("No junction alignment passed the reserved paint check")
    accepted.sort(key=lambda candidate:candidate.residual_m)
    best = accepted[0]
    if len(accepted)==1:
        return best
    # A difference in an extrapolated corner need not invalidate the interior.
    # Require shared, independently checked support at each returned position.
    vertices=best.hull.reshape(-1,2)
    low=np.ceil(vertices.min(0)).astype(int)
    high=np.floor(vertices.max(0)).astype(int)
    grid=np.array([[x,y] for x in range(low[0],high[0]+1) for y in range(low[1],high[1]+1)])
    if len(grid)<35:
        raise CalibrationError("Insufficient common support")
    pixels=transform(np.linalg.inv(best.matrix),grid)
    valid=np.ones(len(grid),bool)
    predictions=[]
    for candidate in accepted:
        points=transform(candidate.matrix,pixels)
        valid &= np.array([cv2.pointPolygonTest(candidate.hull,tuple(p),False)>=0 for p in points])
        for previous in predictions:
            valid &= np.linalg.norm(points-previous,axis=1)<=.6
        predictions.append(points)
    if valid.sum()<35:
        raise CalibrationError("Insufficient area of alignment agreement")
    best.alternatives=tuple(accepted[1:])
    return best
