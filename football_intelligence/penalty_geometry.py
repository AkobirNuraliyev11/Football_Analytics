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

    def project(self, pixel):
        xy = transform(self.matrix, [pixel])[0]
        inside = cv2.pointPolygonTest(self.hull, tuple(map(float, xy)), False)
        if inside < 0:
            raise CalibrationError("Outside observed penalty-area markings")
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


def check_penalty_area(rgb, seed, side, detections=(), pitch=None):
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
            hot = np.flatnonzero(light > background+18)
            if not len(hot) or hot[0]<4 or hot[-1]>44 or hot[-1]-hot[0]>9 or np.any(np.diff(hot)>1):
                continue
            center = np.average(offsets[hot],weights=light[hot]-background)
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
