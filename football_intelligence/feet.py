"""Optional crop-based ankle localization and conservative visible-shoe screening.

Pose confidence and a shoe silhouette do not establish foot/ground contact.
"""
from pathlib import Path
import math

from .calibration import transform
from .model_assets import sha256

POSE_URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-pose.pt"
POSE_SHA256 = "869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0"


def download_pose_model(directory):
    import urllib.request
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    target=directory/"yolo11n-pose.pt"
    if not target.exists():
        partial=target.with_suffix(".download")
        urllib.request.urlretrieve(POSE_URL,partial)
        if sha256(partial)!=POSE_SHA256:
            raise ValueError("Pose model hash mismatch")
        partial.replace(target)
    if sha256(target)!=POSE_SHA256:
        raise ValueError("Pose model hash mismatch")
    return {"file":str(target),"sha256":POSE_SHA256,"source":POSE_URL}


class AnkleDetector:
    def __init__(self,path,*,device="cpu"):
        import os
        path=Path(path)
        if sha256(path)!=POSE_SHA256:
            raise ValueError("Unexpected pose model hash; refusing to load")
        runtime=path.resolve().parent/"runtime"
        runtime.mkdir(parents=True,exist_ok=True)
        os.environ.setdefault("YOLO_CONFIG_DIR",str(runtime))
        from ultralytics import YOLO
        self.model=YOLO(str(path),task="pose")
        self.device=device
        self.fingerprint=POSE_SHA256

    def predict(self,rgb,items):
        import numpy as np
        crops=[];targets=[];output={}
        height,width=rgb.shape[:2]
        for item in items:
            if item["kind"]!="person":continue
            b=item["bbox"];h=b["y_max"]-b["y_min"]
            if h<35:
                output[item["track_id"]]={"status":"small_player"};continue
            x1=max(0,int(b["x_min"]-.2*h));x2=min(width,math.ceil(b["x_max"]+.2*h))
            y1=max(0,int(b["y_min"]-.12*h));y2=min(height,math.ceil(b["y_max"]+.12*h))
            crops.append(np.ascontiguousarray(rgb[y1:y2,x1:x2,::-1]))
            targets.append((item,x1,y1))
        if not crops:return output
        results=self.model.predict(crops,imgsz=256,conf=.25,device=self.device,verbose=False,rect=False)
        for result,(item,x,y) in zip(results,targets):
            b=item["bbox"]
            boxes=result.boxes.xyxy.cpu().numpy()+np.array([x,y,x,y])
            scores=[]
            for box in boxes:
                intersection=max(0,min(b["x_max"],box[2])-max(b["x_min"],box[0]))*max(0,min(b["y_max"],box[3])-max(b["y_min"],box[1]))
                union=(b["x_max"]-b["x_min"])*(b["y_max"]-b["y_min"])+(box[2]-box[0])*(box[3]-box[1])-intersection
                scores.append(intersection/max(union,1e-9))
            order=np.argsort(scores)[::-1]
            if len(order)==0 or scores[order[0]]<.5:
                output[item["track_id"]]={"status":"pose_not_matched"};continue
            if len(order)>1 and scores[order[0]]-scores[order[1]]<.15:
                output[item["track_id"]]={"status":"pose_assignment_ambiguous"};continue
            points=result.keypoints.data[int(order[0])].cpu().numpy().copy()
            if points.shape!=(17,3) or not np.isfinite(points).all():
                output[item["track_id"]]={"status":"invalid_pose"};continue
            points[:,:2]+=np.array([x,y])
            output[item["track_id"]]={"status":"localized","keypoints":points.tolist(),
                "box_iou":float(scores[order[0]]),"model_sha256":self.fingerprint}
        return output


def visible_shoe(rgb,ankle,body_height):
    """Find a small non-grass component near an ankle; reject merged paint/shadows."""
    import cv2
    import numpy as np
    x,y=ankle;radius=max(4,int(.18*body_height))
    x1=max(0,int(x)-radius);x2=min(rgb.shape[1],int(x)+radius+1)
    y1=max(0,int(y)-max(2,int(.05*body_height)))
    y2=min(rgb.shape[0],int(y)+max(5,int(.15*body_height))+1)
    crop=rgb[y1:y2,x1:x2].astype(float)
    if not crop.size:return None
    grass=((crop[:,:,1]>1.1*crop[:,:,0])&(crop[:,:,1]>1.1*crop[:,:,2])
           &(crop[:,:,1]-crop[:,:,0]>20)&(crop[:,:,1]-crop[:,:,2]>20))
    count,labels,stats,_=cv2.connectedComponentsWithStats((~grass).astype(np.uint8))
    candidates=[]
    for i in range(1,count):
        left,top,w,h,area=stats[i]
        if area<2 or w>=x2-x1-1 or top+h>=y2-y1:
            continue
        ys,xs=np.where(labels==i)
        distance=np.min(np.hypot(xs+x1-x,ys+y1-y))
        if distance>max(2,.04*body_height):continue
        bottom=ys.max()
        if bottom+y1<y-1:continue
        bottom_x=float(np.median(xs[ys>=bottom-1]))+x1
        candidates.append((distance,[bottom_x,float(bottom+y1)]))
    return min(candidates,key=lambda p:p[0])[1] if candidates else None


class FootLocalizer:
    def __init__(self,*,allow_ankle_proxy=False):
        self.previous={}
        self.time=None
        self.shot=None
        self.allow_ankle_proxy=allow_ankle_proxy
        self.offsets={}

    def update(self,rgb,items,poses,*,timestamp_s,shot_id,fit=None):
        import numpy as np
        if self.time is not None and timestamp_s<=self.time:
            raise ValueError("Foot-localizer timestamps must increase")
        if self.shot!=shot_id or (self.time is not None and timestamp_s-self.time>.12):
            self.previous={}
            self.offsets={}
        result={};current={k:v for k,v in self.previous.items() if v["cooldown"]>timestamp_s}
        for item in items:
            if item["kind"]!="person":continue
            key=item["track_id"];pose=poses.get(key,{"status":"pose_unavailable"})
            out=dict(pose);out["ground_contact_verified"]=False
            result[key]=out
            if pose.get("status")!="localized":continue
            points=np.array(pose["keypoints"],dtype=float)
            if points.shape!=(17,3) or not np.isfinite(points).all():
                out["status"]="invalid_pose";continue
            b=item["bbox"];h=b["y_max"]-b["y_min"]
            if min(points[[11,12,13,14,15,16],2])<.5:
                out["status"]="legs_not_visible";continue
            ankles=points[[15,16],:2];hips=points[[11,12],:2].mean(axis=0)
            if (np.any(ankles[:,1]<hips[1]+.2*h) or np.any(ankles[:,1]>b["y_max"]+.08*h)
                or np.any(ankles[:,0]<b["x_min"]-.1*h) or np.any(ankles[:,0]>b["x_max"]+.1*h)):
                out["status"]="implausible_leg_geometry";continue
            shoes=[visible_shoe(rgb,p,h) for p in ankles]
            out["ankles_px"]=ankles.tolist();out["shoes_px"]=shoes
            offset_key=(shot_id,key,item.get("continuity_segment"))
            histories=self.offsets.setdefault(offset_key,[[],[]])
            for side in range(2):
                histories[side]=[v for v in histories[side] if timestamp_s-v[0]<=.5]
                if shoes[side] is not None and points[15+side,2]>=.8:
                    delta=(np.array(shoes[side])-ankles[side])/h
                    if 0<=delta[1]<=.08 and abs(delta[0])<=.15:
                        histories[side].append((timestamp_s,delta.tolist()))
            method="pose_guided_lower_visible_shoe"
            if all(p is not None for p in shoes):
                selected=max(shoes,key=lambda p:p[1])
            elif self.allow_ankle_proxy:
                lower=int(ankles[:,1].argmax())
                history=histories[lower]
                if shoes[lower] is not None and abs(ankles[0,1]-ankles[1,1])>.03*h:
                    selected=shoes[lower]
                elif (len(history)>=3 and min(points[[13,14,15,16],2])>=.8):
                    offsets=np.array([v[1] for v in history])
                    if np.linalg.norm(np.std(offsets,axis=0))>.04:
                        out["status"]="unstable_shoe_offset";continue
                    selected=(ankles[lower]+np.median(offsets,axis=0)*h).tolist()
                    method="current_ankle_recent_shoe_offset"
                    out["shoe_offset_samples"]=len(history)
                    out["shoe_offset_oldest_age_s"]=timestamp_s-history[0][0]
                else:
                    out["status"]="shoe_not_separable";continue
            else:
                out["status"]="shoe_not_separable";continue
            old=self.previous.get(key)
            same_segment=old is not None and old["segment"]==item.get("continuity_segment")
            cooldown=old["cooldown"] if same_segment else -1
            if same_segment and timestamp_s-old["time"]<=.12 and fit is not None and old["matrix"] is not None:
                expected=transform(np.linalg.inv(fit.matrix),transform(old["matrix"],np.vstack([old["ankles"],old["hips"]])))
                rise=expected[:,1]-np.r_[ankles[:,1],hips[1]]
                # A veto, not an airborne classifier: fast movement away from the camera can also trigger it.
                rate=rise/h/(timestamp_s-old["time"])
                if min(rate)>1.8:
                    cooldown=timestamp_s+.3
                    out["motion_warning"]="possible_airborne_or_vertical_motion"
            current[key]={"ankles":ankles,"hips":hips,"matrix":fit.matrix if fit else None,
                "time":timestamp_s,"segment":item.get("continuity_segment"),"cooldown":cooldown}
            if timestamp_s<cooldown:
                out["status"]="vertical_motion_cooldown";continue
            out.update(status="shoe_candidate",anchor_px=selected,
                anchor_method=method,ankle_confidence=float(min(points[[15,16],2])))
        self.previous=current;self.time=timestamp_s;self.shot=shot_id
        segments={item["track_id"]:item.get("continuity_segment") for item in items}
        self.offsets={k:v for k,v in self.offsets.items() if k[1] in segments and k[2]==segments[k[1]] and any(v)}
        return result
