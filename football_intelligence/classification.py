"""Conservative online kit clustering and temporal role/team classification."""
from dataclasses import asdict, dataclass, field
import math

from .config import PitchConfig
from .validation import finite, integer


@dataclass(frozen=True)
class ClassificationConfig:
    min_bootstrap_tracks: int = 8
    min_cluster_tracks: int = 3
    min_samples: int = 3
    min_cluster_separation: float = 0.16
    max_color_distance: float = 0.22
    min_color_margin: float = 0.06
    switch_duration_s: float = 0.8
    stale_after_s: float = 2.0

    def __post_init__(self):
        for name in ("min_bootstrap_tracks", "min_cluster_tracks", "min_samples"):
            integer(name, getattr(self,name), minimum=2)
        for name in ("min_cluster_separation", "max_color_distance", "min_color_margin",
                     "switch_duration_s", "stale_after_s"):
            finite(name,getattr(self,name),minimum=.001)
        if self.min_bootstrap_tracks < 2*self.min_cluster_tracks:
            raise ValueError("Bootstrap must permit two supported kit clusters")


def torso_feature(rgb, bbox):
    """Median RGB chromaticity ignores uniform exposure changes; black/white ambiguity remains."""
    import numpy as np
    height,width = rgb.shape[:2]
    left,top,right,bottom = (bbox[k] for k in ("x_min","y_min","x_max","y_max"))
    w,h = right-left,bottom-top
    x1,x2 = max(0,int(left+.25*w)),min(width,int(left+.75*w))
    y1,y2 = max(0,int(top+.18*h)),min(height,int(top+.55*h))
    if x2-x1 < 3 or y2-y1 < 4:
        return None
    pixels = rgb[y1:y2,x1:x2].reshape(-1,3).astype(float)
    # Very dark pixels and saturated clipped highlights carry unreliable color.
    pixels = pixels[(pixels.max(axis=1)>25) & (pixels.min(axis=1)<250)]
    if len(pixels)<12:
        return None
    chroma = pixels / np.maximum(pixels.sum(axis=1,keepdims=True),1)
    feature = np.median(chroma,axis=0)
    return feature / max(float(feature.sum()),1e-9)


@dataclass
class TrackClassification:
    last_seen: float
    role_scores: dict = field(default_factory=dict)
    samples: int = 0
    role_last_evidence: float | None = None
    team: str = "unknown"
    team_confidence: float = 0.0
    team_last_evidence: float | None = None
    pending_team: str | None = None
    pending_since: float = 0.0
    pending_count: int = 0


class TeamRoleClassifier:
    """One instance per match. Frozen team prototypes persist across shot resets."""
    def __init__(self, config=None, pitch=None):
        self.config = config or ClassificationConfig()
        self.pitch = pitch or PitchConfig()
        self.states = {}
        self.bootstrap = {}
        self.centers = None
        self.shot_id = None
        self.previous_time = None
        self.bootstrap_support = None

    def _initialize(self):
        import numpy as np
        cfg=self.config
        samples=[feature for feature,count in self.bootstrap.values() if count>=cfg.min_samples]
        if len(samples)<cfg.min_bootstrap_tracks:
            return
        samples=np.array(samples)
        # Deterministic two-means, seeded at the most separated pair; no random label flips.
        distances=np.linalg.norm(samples[:,None,:]-samples[None,:,:],axis=2)
        i,j=np.unravel_index(distances.argmax(),distances.shape)
        centers=samples[[i,j]].copy()
        for _ in range(30):
            labels=np.linalg.norm(samples[:,None,:]-centers[None,:,:],axis=2).argmin(axis=1)
            if any((labels==k).sum()<cfg.min_cluster_tracks for k in (0,1)):
                return
            new=np.array([np.median(samples[labels==k],axis=0) for k in (0,1)])
            if np.allclose(new,centers,atol=1e-6):
                centers=new
                break
            centers=new
        if np.linalg.norm(centers[0]-centers[1])<cfg.min_cluster_separation:
            return
        # Reject diffuse clusters instead of separating one uniform kit arbitrarily.
        if any(float(np.median(np.linalg.norm(samples[labels==k]-centers[k],axis=1)))>
               cfg.max_color_distance/2 for k in (0,1)):
            return
        order=sorted(range(2),key=lambda k:(-float(centers[k].max()-centers[k].min()),tuple(centers[k])))
        self.centers=centers[order]
        self.bootstrap_support=[int((labels==k).sum()) for k in order]
        self.bootstrap.clear()

    def _color(self, feature):
        import numpy as np
        if self.centers is None or feature is None:
            return "unknown",0.0
        distances=np.linalg.norm(self.centers-feature,axis=1)
        index=int(distances.argmin())
        nearest=float(distances[index])
        margin=float(distances[1-index]-distances[index])
        if nearest>self.config.max_color_distance or margin<self.config.min_color_margin:
            return "unknown",0.0
        # A quality score, not a calibrated probability.
        score=min(1.,margin/.3)*max(0.,1-nearest/self.config.max_color_distance)
        return ("A","B")[index],score

    def _role(self,state,record,feature):
        import numpy as np
        total=sum(state.role_scores.values())
        if (state.samples<self.config.min_samples or total<.5 or state.role_last_evidence is None
            or state.last_seen-state.role_last_evidence>self.config.stale_after_s):
            return "unknown",0.0,"warming_up"
        role=max(state.role_scores,key=state.role_scores.get)
        score=state.role_scores[role]/total
        if score<.75:
            return "unknown",score,"mixed_role_evidence"
        if role=="goalkeeper":
            point=record.get("pitch_position_candidate")
            if point is None or self.centers is None or feature is None:
                return "unknown",score,"goalkeeper_needs_color_and_geometry"
            x,y=point["x_m"],point["y_m"]
            in_box=(0<=x<=16.5 or self.pitch.length_m-16.5<=x<=self.pitch.length_m) and abs(y-self.pitch.width_m/2)<=20.16
            distinct=float(np.linalg.norm(self.centers-feature,axis=1).min())>.12
            if not in_box or not distinct:
                return "unknown",score,"goalkeeper_evidence_incomplete"
        return role,score,"temporal_model_consensus"

    def update(self,rgb,records,*,timestamp_s,shot_id):
        finite("timestamp_s",timestamp_s,minimum=0)
        integer("shot_id",shot_id)
        if self.previous_time is not None and timestamp_s<=self.previous_time:
            raise ValueError("Classification timestamps must strictly increase")
        if self.shot_id!=shot_id or (self.previous_time is not None and timestamp_s-self.previous_time>.25):
            self.states.clear()
            self.bootstrap.clear()
        self.previous_time,self.shot_id=timestamp_s,shot_id
        self.states={k:s for k,s in self.states.items() if timestamp_s-s.last_seen<=self.config.stale_after_s}
        self.bootstrap={k:v for k,v in self.bootstrap.items() if k in self.states}
        features={}
        for record in records:
            if record["kind"]!="person":
                continue
            key=record["track_id"]
            state=self.states.setdefault(key,TrackClassification(timestamp_s))
            state.last_seen=timestamp_s
            candidate=record.get("role_candidate","unknown")
            for role in state.role_scores:
                state.role_scores[role]*=.85
            if candidate in {"outfield","official","goalkeeper"} and record["confidence"]>=.5:
                state.role_scores[candidate]=state.role_scores.get(candidate,0)+record["confidence"]
                state.samples+=1
                state.role_last_evidence=timestamp_s
            feature=features[key]=torso_feature(rgb,record["bbox"])
            role,_,_=self._role(state,record,feature)
            if (self.centers is None and feature is not None and role=="outfield"
                and candidate=="outfield" and record.get("confirmed") and record["confidence"]>=.6
                and record.get("projection_state")!="outside_pitch"):
                if key in self.bootstrap:
                    old,count=self.bootstrap[key]
                    self.bootstrap[key]=(.8*old+.2*feature,count+1)
                elif len(self.bootstrap)<64:
                    self.bootstrap[key]=(feature,1)
        if self.centers is None:
            self._initialize()
        output=[]
        for record in records:
            enriched=dict(record)
            enriched.update(team="unknown",role="unknown",team_confidence=0.,role_confidence=0.,
                            classification_reason="non_person",team_changed=False)
            if record["kind"]=="person":
                state=self.states[record["track_id"]]
                feature=features[record["track_id"]]
                role,role_score,reason=self._role(state,record,feature)
                candidate,score=self._color(feature)
                # A single conflicting referee/keeper candidate blocks team output immediately.
                eligible=(role=="outfield" and record.get("role_candidate")=="outfield"
                          and record.get("projection_state")!="outside_pitch")
                if eligible and candidate!="unknown":
                    if state.pending_team!=candidate:
                        state.pending_team,state.pending_since,state.pending_count=candidate,timestamp_s,1
                    else:
                        state.pending_count+=1
                    if candidate==state.team:
                        state.team_confidence=score
                        state.team_last_evidence=timestamp_s
                    elif (state.pending_count>=self.config.min_samples and
                          (state.team=="unknown" or timestamp_s-state.pending_since>=self.config.switch_duration_s)):
                        enriched["team_changed"]=state.team!="unknown"
                        state.team,state.team_confidence,state.team_last_evidence=candidate,score,timestamp_s
                else:
                    state.pending_team,state.pending_count=None,0
                age=timestamp_s-state.team_last_evidence if state.team_last_evidence is not None else math.inf
                if age>self.config.stale_after_s:
                    state.team="unknown"
                    state.team_confidence=0.0
                enriched.update(role=role,role_confidence=role_score,classification_reason=reason)
                if eligible:
                    enriched.update(team=state.team,team_confidence=state.team_confidence*math.exp(-age)
                                    if math.isfinite(age) else 0.)
            output.append(enriched)
        return output

    def summary(self):
        return {"status":"ready" if self.centers is not None else "insufficient_kit_evidence",
                "config":asdict(self.config),"features":"median_normalized_rgb",
                "team_centers":self.centers.tolist() if self.centers is not None else None,
                "bootstrap_track_support":self.bootstrap_support,
                "labels":"arbitrary persistent A/B; not team names or attacking direction",
                "confidence":"heuristic quality scores, not calibrated probabilities"}
