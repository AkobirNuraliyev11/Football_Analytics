"""Observed prediction diagnostics, never estimates of detection accuracy."""
from collections import Counter


class DetectionQuality:
    def __init__(self):
        self.frames = 0
        self.ball_states = Counter()
        self.people = Counter()

    def update(self, detections):
        balls = [d for d in detections if d['kind'] == 'ball']
        state = 'missing' if not balls else 'candidate' if len(balls) == 1 else 'ambiguous'
        self.frames += 1
        self.ball_states[state] += 1
        for d in detections:
            if d['kind'] != 'person':
                continue
            self.people['observations'] += 1
            self.people['unconfirmed'] += not d.get('confirmed', False)
            self.people['unsafe_association'] += not d.get('continuity_safe', False)
            self.people['unknown_team'] += d.get('team', 'unknown') == 'unknown'
            self.people['unknown_role'] += d.get('role', 'unknown') == 'unknown'
        return {'ball_status': state, 'ball_candidate_ids': [d['track_id'] for d in balls],
                'verified_ball_available': False}

    def summary(self):
        return {'frames': self.frames,
                'ball_frames': {k: self.ball_states[k] for k in ('missing','candidate','ambiguous')},
                'people': {k: self.people[k] for k in ('observations','unconfirmed','unsafe_association',
                                                     'unknown_team','unknown_role')},
                'scope': 'Prediction diagnostics, not precision or recall. Missing balls may be occluded; '
                         'a single candidate and a confirmed track do not establish a true ball. '
                         'Person flags overlap; officials may have unknown teams.'}
