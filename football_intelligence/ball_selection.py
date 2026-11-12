"""Conservative temporal selection among observed ball candidates, not verification."""
from .validation import finite, integer


class BallSelector:
    def __init__(self, *, min_hits=3, margin=.15, max_gap_s=.25):
        integer('min_hits',min_hits,minimum=1)
        finite('margin',margin,minimum=0)
        finite('max_gap_s',max_gap_s,minimum=.001)
        self.min_hits,self.margin,self.max_gap_s=min_hits,margin,max_gap_s
        self.history={}
        self.previous_time=None
        self.shot=None

    def update(self, records, *, timestamp_s, shot_id):
        finite('timestamp_s',timestamp_s,minimum=0)
        integer('shot_id',shot_id)
        if self.previous_time is not None and timestamp_s<=self.previous_time:
            raise ValueError('Ball selection timestamps must increase')
        if shot_id!=self.shot:
            self.history.clear()
        self.shot=shot_id;self.previous_time=timestamp_s
        self.history={k:v for k,v in self.history.items() if timestamp_s-v[2]<=self.max_gap_s}
        balls=[d for d in records if d['kind']=='ball']
        ids=[d['track_id'] for d in balls]
        if len(set(ids))!=len(ids):raise ValueError('Duplicate ball track ID')
        scores=[]
        for d in balls:
            confidence=d['confidence'];finite('ball confidence',confidence,minimum=0)
            if confidence>1:raise ValueError('Invalid ball confidence')
            identity=d['track_id'];old=self.history.get(identity)
            # Time-based smoothing, so evidence is not strengthened just by FPS.
            alpha=1 if old is None else 1-2**(-(timestamp_s-old[2])/.12)
            score=confidence if old is None else old[0]+alpha*(confidence-old[0])
            hits=1 if old is None else old[1]+1
            self.history[identity]=(score,hits,timestamp_s)
            scores.append((score,identity,hits))
        scores.sort(reverse=True)
        selected=None
        if not scores:reason='no_observed_candidate'
        elif len(scores)==1:selected=scores[0][1];reason='single_observed_candidate'
        elif scores[0][2]<self.min_hits:reason='insufficient_history'
        elif len(scores)>1 and scores[0][0]-scores[1][0]<self.margin:reason='competing_candidates'
        else:selected=scores[0][1];reason='temporal_candidate'
        return {'status':'selected_candidate' if selected is not None else 'unresolved',
                'selected_track_id':selected,'reason':reason,'verified':False,
                'candidate_scores':[{'track_id':i,'score':s,'observations':n} for s,i,n in scores]}
