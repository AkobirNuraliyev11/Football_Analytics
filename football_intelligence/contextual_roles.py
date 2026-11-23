"""Causal kit support for official-role predictions; never certifies identity/contact."""
from collections import deque


def kit_features(rgb, records):
    import numpy as np
    pixels=rgb[::8,::8].reshape(-1,3).astype(float)
    grass=(pixels[:,1]>pixels[:,0]*1.1)&(pixels[:,1]>pixels[:,2]*1.1)
    if grass.sum()<100:return {}
    exposure=float(np.median(pixels[grass,1]))
    if exposure<=25:return {}
    height,width=rgb.shape[:2];result={}
    for r in records:
        if r['kind']!='person':continue
        b=r['bbox'];x,y=b['x_min'],b['y_min'];w,h=b['x_max']-x,b['y_max']-y
        # Tiny, clipped and overlapping torsos are insufficient kit evidence.
        if h<35 or min(x,y,width-b['x_max'],height-b['y_max'])<2:continue
        left,right=x+.25*w,x+.75*w;top,bottom=y+.18*h,y+.55*h
        if any(o['kind']=='person' and o['track_id']!=r['track_id'] and
               min(right,o['bbox']['x_max'])>max(left,o['bbox']['x_min']) and
               min(bottom,o['bbox']['y_max'])>max(top,o['bbox']['y_min']) for o in records):continue
        crop=rgb[int(top):int(bottom),int(left):int(right)]
        if crop.shape[0]<4 or crop.shape[1]<3:continue
        values=crop.reshape(-1,3).astype(float)
        if np.median(values.max(axis=1))<=25:continue
        result[r['track_id']]=np.median(values,axis=0)/exposure
    return result


class ContextualRoles:
    """Learn only from underlying detector consensus, never from own overrides."""
    def __init__(self):
        self.shot=None;self.last=None;self.histories={};self.pending={}

    def update(self,records,features,*,timestamp_s,shot_id):
        import numpy as np
        if self.last is not None and timestamp_s<=self.last:
            raise ValueError('Contextual role timestamps must increase')
        if self.shot!=shot_id or (self.last is not None and timestamp_s-self.last>.25):
            self.histories.clear();self.pending.clear()
        self.shot,self.last=shot_id,timestamp_s
        active={r['track_id']:r.get('continuity_segment') for r in records if r['kind']=='person'}
        self.histories={k:v for k,v in self.histories.items() if timestamp_s-v['last']<=2
                        and (k[0] not in active or k[1]==active[k[0]])}
        for r in records:
            tid=r['track_id'];feature=features.get(tid)
            if (feature is None or r.get('confirmed') is not True or r.get('continuity_safe') is not True
                or r.get('classification_conflict') or r.get('team_changed')):continue
            group=('official' if r.get('role')=='official' and r.get('role_candidate')=='official' else
                   r.get('team') if r.get('role')=='outfield' and r.get('role_candidate')=='outfield' else None)
            if group not in ('official','A','B') or r['confidence']<.8:continue
            key=(tid,r.get('continuity_segment'))
            state=self.histories.get(key)
            if state is None or state['group']!=group:
                state=dict(group=group,values=deque(maxlen=25));self.histories[key]=state
            state['last']=timestamp_s;state['values'].append(feature)
        groups={k:[] for k in ('official','A','B')}
        for state in self.histories.values():
            if len(state['values']) >= (8 if state['group']=='official' else 3):
                groups[state['group']].append(np.median(state['values'],axis=0))
        teams=[np.median(groups[k],axis=0) for k in ('A','B') if len(groups[k])>=3]
        ready=bool(groups['official']) and len(teams)==2
        pending={};output=[]
        for r in records:
            item=dict(r);key=(r['track_id'],r.get('continuity_segment'));feature=features.get(r['track_id'])
            supported=False;score=0.
            if (ready and feature is not None and r['confidence']>=.5
                and r.get('confirmed') is True and r.get('continuity_safe') is True
                and r.get('role')!='goalkeeper' and r.get('role_candidate')!='goalkeeper'):
                official=min(groups['official'],key=lambda c:np.linalg.norm(c-feature))
                distance=float(np.linalg.norm(official-feature))
                team_distance=min(float(np.linalg.norm(c-feature)) for c in teams)
                separation=min(float(np.linalg.norm(official-c)) for c in teams)
                supported=distance<.6*team_distance and distance<.6*separation
                score=max(0.,1-distance/max(team_distance,1e-9))
            old=self.pending.get(key)
            count=old[1]+1 if supported and old and timestamp_s-old[0]<=.12 else int(supported)
            pending[key]=(timestamp_s,count)
            if count>=3:
                item.update(role='official',team='unknown',team_confidence=0.,role_confidence=score,
                            classification_reason='inferred_official_kit_consensus',
                            role_evidence='experimental_contextual_kit')
            output.append(item)
        self.pending=pending
        return output
