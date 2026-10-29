"""Timestamp-aware multi-object association with motion and torso appearance."""
from dataclasses import asdict, dataclass

from .detection import Detection
from .validation import finite, integer
from .classification import torso_feature


@dataclass
class Track:
    track_id: int
    detection: Detection
    last_seen_s: float
    hits: int
    velocity: object
    appearance: object
    kit_feature: object = None
    continuity_segment: int = 0
    continuity_safe: bool = False
    association_reason: str = "new_track"


def appearance(rgb, bbox):
    import cv2
    import numpy as np
    # Inner upper torso reduces grass contamination. No team assignment here.
    w, h = bbox.x_max - bbox.x_min, bbox.y_max - bbox.y_min
    crop = rgb[int(bbox.y_min+.15*h):int(bbox.y_min+.55*h),
               int(bbox.x_min+.2*w):int(bbox.x_min+.8*w)]
    if not crop.size:
        return np.zeros(64, dtype=float)
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    hist = cv2.calcHist([hsv], [0,1], None, [8,8], [0,180,0,256]).ravel()
    return hist / max(float(np.linalg.norm(hist)), 1e-9)


def box_array(box):
    import numpy as np
    return np.array([box.x_min, box.y_min, box.x_max, box.y_max], dtype=float)


def iou(a, b):
    import numpy as np
    size = np.maximum(0, np.minimum(a[2:], b[2:]) - np.maximum(a[:2], b[:2]))
    intersection = float(size.prod())
    return intersection / max(float((a[2:]-a[:2]).prod() + (b[2:]-b[:2]).prod()) - intersection, 1e-9)


class MultiObjectTracker:
    def __init__(self, *, max_lost_s=1.0, max_gap_s=0.25, min_hits=3):
        finite("max_lost_s", max_lost_s, minimum=.001)
        finite("max_gap_s", max_gap_s, minimum=.001)
        integer("min_hits", min_hits, minimum=1)
        self.max_lost_s, self.max_gap_s, self.min_hits = max_lost_s, max_gap_s, min_hits
        self.tracks = {}
        self.next_id = 1
        self.shot_id = None
        self.previous_time = None

    def update(self, detections, rgb, *, timestamp_s, shot_id):
        import numpy as np
        from scipy.optimize import linear_sum_assignment
        finite("timestamp_s", timestamp_s, minimum=0)
        integer("shot_id", shot_id)
        if self.previous_time is not None and timestamp_s <= self.previous_time:
            raise ValueError("Tracker timestamps must strictly increase")
        if self.shot_id != shot_id or (self.previous_time is not None and timestamp_s-self.previous_time > self.max_gap_s):
            self.tracks.clear()
        self.previous_time, self.shot_id = timestamp_s, shot_id
        self.tracks = {k:t for k,t in self.tracks.items() if timestamp_s-t.last_seen_s <= self.max_lost_s}
        descriptors = [appearance(rgb,d.bbox) for d in detections]
        kits = [torso_feature(rgb,asdict(d.bbox)) if d.kind=="person" else None for d in detections]
        old = list(self.tracks.values())
        costs = np.full((len(old),len(detections)), 1e6)
        for i, track in enumerate(old):
            dt = timestamp_s-track.last_seen_s
            predicted = box_array(track.detection.bbox) + track.velocity * dt
            for j, detection in enumerate(detections):
                if detection.kind != track.detection.kind:
                    continue
                box = box_array(detection.bbox)
                scale = max(float(np.linalg.norm(predicted[2:]-predicted[:2])), 20)
                distance = float(np.linalg.norm((predicted[:2]+predicted[2:]-box[:2]-box[2:])/2)) / scale
                if distance > 1.5:
                    continue
                if (track.hits>=3 and track.kit_feature is not None and kits[j] is not None
                    and np.linalg.norm(track.kit_feature-kits[j])>.20):
                    continue
                visual = 1-float(np.clip(np.dot(track.appearance,descriptors[j]),0,1))
                costs[i,j] = .5*(1-iou(predicted,box)) + .3*min(distance,1) + .2*visual
        matched = {}
        if costs.size:
            # Dummy columns permit a track to remain unmatched rather than force a poor pairing.
            rows, columns = linear_sum_assignment(np.column_stack([costs,np.full((len(old),len(old)),.78)]))
            for i,j in zip(rows,columns):
                if j>=len(detections) or costs[i,j] >= .78:
                    continue
                track, detection = old[i], detections[j]
                dt = timestamp_s-track.last_seen_s
                alternatives=np.concatenate([np.delete(costs[i],j),np.delete(costs[:,j],i)])
                margin=float(alternatives.min()-costs[i,j]) if len(alternatives) else float("inf")
                reason=("reacquired_after_gap" if dt>.12 else "ambiguous_assignment" if margin<.08
                        else "weak_assignment" if costs[i,j]>.6 else "matched")
                track.continuity_safe=reason=="matched"
                track.association_reason=reason
                if not track.continuity_safe:
                    track.continuity_segment+=1
                velocity = (box_array(detection.bbox)-box_array(track.detection.bbox))/dt
                track.velocity = .5*track.velocity+.5*velocity
                track.detection, track.last_seen_s = detection, timestamp_s
                track.hits += 1
                if track.continuity_safe:
                    track.appearance = .8*track.appearance+.2*descriptors[j]
                    track.appearance /= max(float(np.linalg.norm(track.appearance)),1e-9)
                    if kits[j] is not None:
                        track.kit_feature=kits[j] if track.kit_feature is None else .9*track.kit_feature+.1*kits[j]
                matched[j] = track
        for j,detection in enumerate(detections):
            if j not in matched and detection.confidence >= .4:
                track = Track(self.next_id,detection,timestamp_s,1,np.zeros(4),descriptors[j],kits[j])
                self.tracks[track.track_id] = track
                self.next_id += 1
                matched[j] = track
        # Only observed boxes are emitted. Unseen predictions never become telemetry.
        return [(matched[j], matched[j].hits >= self.min_hits) for j in sorted(matched)]
