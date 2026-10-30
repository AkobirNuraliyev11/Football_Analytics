"""Experimental midfield measurements from visible paint and unobstructed feet.

Paint consistency and visibility are evidence for estimates, not proof of metric
accuracy or ground contact. No output from this module promotes strict telemetry.
"""
from dataclasses import dataclass
import math

from .calibration import CalibrationError, transform
from .config import PitchConfig


@dataclass
class PaintFit:
    matrix: object
    evidence: dict
    check_pixels: object = None
    check_labels: object = None


def refine_midfield(rgb, seed_matrix, detections, pitch=None):
    import numpy as np
    from scipy.optimize import least_squares
    pitch = pitch or PitchConfig()
    height, width = rgb.shape[:2]
    center = np.array([pitch.length_m/2, pitch.width_m/2])
    colors = rgb.astype(float)
    white = ((colors.min(2)>100) & (colors.max(2)-colors.min(2)<75)
             & (colors[:,:,1]<1.3*colors[:,:,0]))
    for item in detections:
        b = item["bbox"]
        x1,y1,x2,y2 = [int(b[k]) for k in ("x_min","y_min","x_max","y_max")]
        white[max(0,y1-8):min(height,y2+8),max(0,x1-8):min(width,x2+8)] = False
    ys,xs = np.where(white)
    pixels = np.column_stack([xs,ys])
    if len(pixels)<100:
        raise CalibrationError("Insufficient visible paint")

    def residuals(matrix, pixels):
        xy = transform(matrix,pixels)
        return np.column_stack([np.linalg.norm(xy-center,axis=1)-9.15,
                                xy[:,0]-center[0],xy[:,1]-pitch.width_m])

    xy = transform(seed_matrix,pixels)
    residual = residuals(seed_matrix,pixels)
    labels = np.abs(residual).argmin(1)
    keep = ((np.abs(residual).min(1)<1.5) & (np.abs(xy[:,0]-center[0])<22)
            & (xy[:,1]>0) & (xy[:,1]<pitch.width_m+1)
            & ((labels!=2)|(np.abs(residual[:,2])<.35)))
    pixels,labels = pixels[keep],labels[keep]
    counts = np.bincount(labels,minlength=3)
    if min(counts)<80:
        raise CalibrationError("Need visible center circle, halfway line and near touchline")
    selected = np.concatenate([np.flatnonzero(labels==k)[::max(1,counts[k]//500)] for k in range(3)])
    pixels,labels = pixels[selected],labels[selected]
    # Spatially disjoint tiles: no fitting on the pixels used for the reported check.
    train = ((pixels[:,0]//16+pixels[:,1]//16)%2)==0
    if any(np.count_nonzero((labels==k)&mask)<30 for k in range(3) for mask in [train,~train]):
        raise CalibrationError("Insufficient spatial holdout paint support")
    circle = transform(seed_matrix,pixels[labels==0])-center
    sectors = np.unique(np.floor((np.arctan2(circle[:,1],circle[:,0])+math.pi)/(2*math.pi)*12))
    if len(sectors)<9:
        raise CalibrationError("Center-circle coverage is too narrow")
    scale = np.diag([width,height,1])
    normalized = np.asarray(seed_matrix)@scale
    normalized /= normalized[2,2]
    def matrix(values):
        return np.r_[values,1].reshape(3,3)@np.diag([1/width,1/height,1])
    def errors(values, mask):
        r = residuals(matrix(values),pixels[mask])
        return r[np.arange(np.count_nonzero(mask)),labels[mask]]
    result = least_squares(errors,normalized.ravel()[:8],args=(train,),loss="soft_l1",
                           f_scale=.1,x_scale="jac",max_nfev=100)
    if not result.success or not np.isfinite(result.x).all():
        raise CalibrationError("Paint refinement failed")
    refined = matrix(result.x)
    before,after = np.abs(errors(normalized.ravel()[:8],~train)),np.abs(errors(result.x,~train))
    p90 = float(np.quantile(after,.9))
    if p90>.3 or p90>float(np.quantile(before,.9))+.02:
        raise CalibrationError("Held-out paint residual exceeds threshold")
    # Limit geometry corrections, guard the projective denominator on every support point.
    old_points,new_points = transform(seed_matrix,pixels),transform(refined,pixels)
    denominators = np.column_stack([pixels,np.ones(len(pixels))])@refined[2]
    if (np.linalg.norm(new_points-old_points,axis=1).max()>3 or np.linalg.matrix_rank(refined)<3
        or not ((denominators>1e-8).all() or (denominators<-1e-8).all())):
        raise CalibrationError("Unstable paint refinement")
    return PaintFit(refined,{"status":"line_checked_estimate","method":"midfield_paint_refinement",
        "holdout_pixels":int((~train).sum()),"paint_p90_before_m":float(np.quantile(before,.9)),
        "paint_p90_after_m":p90,"circle_sectors":len(sectors),
        "scale_assumption":"Configured pitch dimensions and regulation 9.15 m circle",
        "scope":"Inside center circle only; paint residual is not athlete-position accuracy"},
        pixels[~train],labels[~train])


def stabilize_camera(previous_rgb,rgb,previous_fit,current_fit,previous_items,current_items,pitch=None):
    """Transport geometry with static field texture, checked against current paint."""
    import cv2
    import numpy as np
    pitch=pitch or PitchConfig()
    height,width=rgb.shape[:2]
    mask=np.zeros((height,width),dtype=np.uint8)
    # Use only the ground area enclosed by the circle, away from people.
    angle=np.linspace(0,2*np.pi,80)
    circle=np.c_[pitch.length_m/2+9.15*np.cos(angle),pitch.width_m/2+9.15*np.sin(angle)]
    polygon=transform(np.linalg.inv(previous_fit.matrix),circle).astype(np.int32)
    cv2.fillPoly(mask,[polygon],255)
    for item in previous_items+current_items:
        b=item["bbox"]
        x1,y1,x2,y2=[int(b[k]) for k in ("x_min","y_min","x_max","y_max")]
        mask[max(0,y1-15):min(height,y2+15),max(0,x1-15):min(width,x2+15)]=0
    old=cv2.cvtColor(previous_rgb,cv2.COLOR_RGB2GRAY)
    new=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    points=cv2.goodFeaturesToTrack(old,250,.01,8,mask=mask)
    if points is None or len(points)<12:
        raise CalibrationError("Insufficient stationary field features")
    moved,forward,_=cv2.calcOpticalFlowPyrLK(old,new,points,None)
    if moved is None:
        raise CalibrationError("Camera flow unavailable")
    returned,backward,_=cv2.calcOpticalFlowPyrLK(new,old,moved,None)
    if returned is None:
        raise CalibrationError("Reverse camera flow unavailable")
    valid=forward.ravel().astype(bool)&backward.ravel().astype(bool)
    valid &= np.linalg.norm((returned-points).reshape(-1,2),axis=1)<.75
    src,dst=points.reshape(-1,2)[valid],moved.reshape(-1,2)[valid]
    if len(src)<12:
        raise CalibrationError("Insufficient consistent field flow")
    camera,inliers=cv2.findHomography(src,dst,cv2.RANSAC,1.0)
    if camera is None or inliers is None or int(inliers.sum())<12 or inliers.mean()<.7:
        raise CalibrationError("Unstable camera motion")
    keep=inliers.ravel().astype(bool)
    if cv2.contourArea(cv2.convexHull(src[keep]))<1000:
        raise CalibrationError("Camera features are too concentrated")
    transported=previous_fit.matrix@np.linalg.inv(camera)
    xy=transform(transported,current_fit.check_pixels)
    residual=np.c_[np.linalg.norm(xy-[pitch.length_m/2,pitch.width_m/2],axis=1)-9.15,
                   xy[:,0]-pitch.length_m/2,xy[:,1]-pitch.width_m]
    # Flow was estimated inside the circle. Check transport on that same supported
    # region; extrapolating it to the near touchline is not a valid drift test.
    local=(current_fit.check_labels!=2)&(np.linalg.norm(xy-[pitch.length_m/2,pitch.width_m/2],axis=1)<10)
    if local.sum()<60:
        raise CalibrationError("Insufficient local paint for camera check")
    paint_p90=float(np.quantile(np.abs(residual[np.arange(len(xy)),current_fit.check_labels][local]),.9))
    if paint_p90>.3:
        raise CalibrationError("Camera transport drifted away from visible paint")
    stationary=np.linalg.norm(transform(previous_fit.matrix,src[keep])-transform(transported,dst[keep]),axis=1)
    p90=float(np.quantile(stationary,.9))
    if p90>.08:
        raise CalibrationError("Excessive stationary-ground motion")
    evidence=current_fit.evidence|{"camera_stable":True,"camera_features":int(keep.sum()),
        "stationary_ground_p90_m":p90,"transported_paint_p90_m":paint_p90}
    return PaintFit(transported,evidence,current_fit.check_pixels,current_fit.check_labels)


def foot_candidate(rgb,item,others,fit,pitch=None,*,anchor_px=None):
    """Conservative visibility screen; deliberately does NOT assert ground contact."""
    import numpy as np
    pitch = pitch or PitchConfig()
    b = item["bbox"]
    x1,y1,x2,y2 = [float(b[k]) for k in ("x_min","y_min","x_max","y_max")]
    height,width = rgb.shape[:2]
    if y2-y1<35 or min(x1,y1,width-x2,height-y2)<5:
        return None,"small_or_clipped_player"
    for other in others:
        if other.get("track_id")==item.get("track_id") or other.get("kind")!="person": continue
        o=other["bbox"]
        # Any other person covering the lower third makes the foot anchor ambiguous.
        if (min(x2,o["x_max"])-max(x1,o["x_min"])>0 and
            min(y2+3,o["y_max"])-max(y1+.65*(y2-y1),o["y_min"])>0):
            return None,"feet_occluded"
    anchor=[(x1+x2)/2,y2] if anchor_px is None else list(map(float,anchor_px))
    if len(anchor)!=2 or not np.isfinite(anchor).all() or not (x1-.1*(y2-y1)<=anchor[0]<=x2+.1*(y2-y1) and y1<=anchor[1]<=y2+.1*(y2-y1)):
        return None,"invalid_foot_anchor"
    if anchor_px is None:
        below=rgb[int(y2)+1:min(height,int(y2)+7),max(0,int(x1)):min(width,int(x2))].astype(float)
    else:
        radius=max(3,int(.08*(y2-y1)))
        below=rgb[int(anchor[1])+2:min(height,int(anchor[1])+7),max(0,int(anchor[0])-radius):min(width,int(anchor[0])+radius+1)].astype(float)
    if not below.size:
        return None,"no_visible_ground"
    grass=(below[:,:,1]>1.1*below[:,:,0])&(below[:,:,1]>1.1*below[:,:,2])
    if grass.mean()<.65:
        return None,"no_visible_ground"
    xy=transform(fit.matrix,[anchor])[0]
    if np.linalg.norm(xy-[pitch.length_m/2,pitch.width_m/2])>9.15:
        return None,"outside_checked_midfield"
    offsets=np.array([[3,0],[-3,0],[0,3],[0,-3]])+anchor
    sensitivity=float(np.linalg.norm(transform(fit.matrix,offsets)-xy,axis=1).max())
    if sensitivity>.5:
        return None,"excessive_pixel_sensitivity"
    return {"position":{"x_m":float(xy[0]),"y_m":float(xy[1])},
            "anchor_px":anchor,"three_pixel_sensitivity_m":sensitivity,
            "ground_evidence":"visible_feet_candidate","ground_contact_verified":False},None
