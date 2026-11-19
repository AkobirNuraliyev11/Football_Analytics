import unittest
from football_intelligence.benchmarks.player_metrics import score_players


def person(identity,x=0,team='A'):
    return dict(identity=identity,bbox=dict(x_min=x,y_min=0,x_max=x+10,y_max=20),role='outfield',team=team)


class PlayerMetricsTests(unittest.TestCase):
    def test_perfect_boxes_can_still_have_bad_identity_score(self):
        frames=[dict(frame_index=i,annotation_complete=True,references=[person('a'),person('b',30)],
                     predictions=[person(ids[0]),person(ids[1],30)]) for i,ids in enumerate([('1','2'),('2','1')])]
        r=score_players(frames)
        self.assertEqual(r['precision'],1);self.assertEqual(r['recall'],1)
        self.assertEqual(r['idf1'],.5)

    def test_missed_players_and_unknown_teams_remain_in_denominators(self):
        r=score_players([dict(frame_index=0,annotation_complete=True,
             references=[person('a'),person('b',30)],predictions=[person('1',team='unknown'),person('2',80)])])
        self.assertEqual(r['precision'],.5);self.assertEqual(r['recall'],.5)
        self.assertEqual(r['idf1'],.5);self.assertEqual(r['team_accuracy_including_misses'],0)
        self.assertEqual(r['role_accuracy_including_misses'],.5)

    def test_empty_predictions_are_misses_not_perfect_accuracy(self):
        f=dict(frame_index=0,annotation_complete=True,references=[person('a')],predictions=[])
        r=score_players([f]);self.assertEqual(r['recall'],0);self.assertEqual(r['idf1'],0)
        self.assertIsNone(r['precision'])
        f['annotation_complete']=False
        with self.assertRaises(ValueError):score_players([f])

    def test_duplicate_identity_and_bad_boxes_rejected(self):
        f=dict(frame_index=0,annotation_complete=True,references=[person('a')]*2,predictions=[])
        with self.assertRaises(ValueError):score_players([f])
        f['references']=[person('a')];f['references'][0]['bbox']['x_max']=-1
        with self.assertRaises(ValueError):score_players([f])
