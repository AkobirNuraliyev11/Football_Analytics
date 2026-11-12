import unittest
from football_intelligence.ball_selection import BallSelector


def ball(i,c):return dict(kind='ball',track_id=i,confidence=c)

class BallSelectionTests(unittest.TestCase):
    def test_single_candidate_is_not_delayed_or_verified(self):
        r=BallSelector().update([ball(1,.2)],timestamp_s=0,shot_id=0)
        self.assertEqual(r['selected_track_id'],1)
        self.assertFalse(r['verified'])

    def test_temporal_evidence_rejects_new_weaker_rival(self):
        s=BallSelector()
        for i in range(4):s.update([ball(1,.8)],timestamp_s=i*.04,shot_id=0)
        r=s.update([ball(1,.2),ball(2,.4)],timestamp_s=.16,shot_id=0)
        self.assertEqual(r['selected_track_id'],1)
        self.assertEqual(len(r['candidate_scores']),2)

    def test_close_scores_remain_unresolved(self):
        s=BallSelector()
        for i in range(4):r=s.update([ball(1,.6),ball(2,.59)],timestamp_s=i*.04,shot_id=0)
        self.assertIsNone(r['selected_track_id'])
        self.assertEqual(r['reason'],'competing_candidates')

    def test_missing_and_shot_change_never_invent_a_ball(self):
        s=BallSelector()
        s.update([ball(1,.8)],timestamp_s=0,shot_id=0)
        self.assertIsNone(s.update([],timestamp_s=.04,shot_id=0)['selected_track_id'])
        r=s.update([ball(1,.8),ball(2,.2)],timestamp_s=.08,shot_id=1)
        self.assertIsNone(r['selected_track_id'])
        self.assertEqual(r['reason'],'insufficient_history')

    def test_expired_evidence_does_not_select_competing_ball(self):
        s=BallSelector()
        for i in range(4):s.update([ball(1,.8)],timestamp_s=i*.04,shot_id=0)
        r=s.update([ball(1,.8),ball(2,.2)],timestamp_s=1,shot_id=0)
        self.assertIsNone(r['selected_track_id'])
        with self.assertRaises(ValueError):s.update([],timestamp_s=1,shot_id=0)

    def test_order_does_not_resolve_a_tie(self):
        for items in ([ball(1,.8),ball(2,.8)],[ball(2,.8),ball(1,.8)]):
            s=BallSelector()
            for i in range(3):r=s.update(items,timestamp_s=i*.04,shot_id=0)
            self.assertIsNone(r['selected_track_id'])
