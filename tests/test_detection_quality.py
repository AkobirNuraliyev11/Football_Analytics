import unittest
from football_intelligence.detection_quality import DetectionQuality


class DetectionQualityTests(unittest.TestCase):
    def test_missing_single_and_competing_balls_never_become_verified(self):
        q=DetectionQuality()
        ball=lambda i:dict(kind='ball',track_id=i,confirmed=True)
        self.assertEqual(q.update([])['ball_status'],'missing')
        self.assertFalse(q.update([ball(1)])['verified_ball_available'])
        state=q.update([ball(1),ball(2)])
        self.assertEqual(state['ball_status'],'ambiguous')
        self.assertEqual(state['ball_candidate_ids'],[1,2])
        self.assertEqual(q.summary()['ball_frames'],dict(missing=1,candidate=1,ambiguous=1))

    def test_person_flags_overlap_and_do_not_count_ball(self):
        q=DetectionQuality()
        q.update([dict(kind='person',track_id=1),dict(kind='ball',track_id=2)])
        self.assertEqual(q.summary()['people'],dict(observations=1,unconfirmed=1,
            unsafe_association=1,unknown_team=1,unknown_role=1))
        self.assertEqual(DetectionQuality().summary()['frames'],0)
