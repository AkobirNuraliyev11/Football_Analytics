import unittest
from copy import deepcopy
from football_intelligence.benchmarks.classification_reference import score_classification_review


class ClassificationReviewTests(unittest.TestCase):
    def fixture(self):
        b=dict(x_min=0,y_min=0,x_max=20,y_max=40)
        refs=dict(source_sha256='source',review_method='Human crop review',observations=[
            dict(frame_index=0,source_track_id=1,bbox=b,role='official',team='not_applicable'),
            dict(frame_index=0,source_track_id=2,bbox=b,role='outfield',team='B')])
        return refs,[dict(frame_index=0,detections=[dict(track_id=1,kind='person',bbox=b,role='outfield',team='B')])]

    def test_wrong_role_official_team_and_missing_player_count(self):
        refs,frames=self.fixture()
        r=score_classification_review(refs,frames,source_sha256='source')
        self.assertEqual(r['role']['wrong'],1);self.assertEqual(r['role']['missing'],1)
        self.assertEqual(r['team']['accuracy_including_unknown_and_missing'],0)
        self.assertEqual(r['official_wrong_team'],1)
        frames[0]['detections'][0].update(role='unknown',team='unknown')
        r=score_classification_review(refs,frames,source_sha256='source')
        self.assertEqual(r['role']['unknown'],1)
        self.assertEqual(r['role']['accuracy_including_unknown_and_missing'],0)

    def test_changed_source_box_and_duplicate_reference_rejected(self):
        refs,frames=self.fixture()
        with self.assertRaises(ValueError):score_classification_review(refs,frames,source_sha256='other')
        altered=deepcopy(frames);altered[0]['detections'][0]['bbox']['x_max']=21
        with self.assertRaises(ValueError):score_classification_review(refs,altered,source_sha256='source')
        altered[0]['detections'][0]['bbox']['x_max']=float('nan')
        with self.assertRaises(ValueError):score_classification_review(refs,altered,source_sha256='source')
        refs['observations'].append(refs['observations'][0])
        with self.assertRaises(ValueError):score_classification_review(refs,frames,source_sha256='source')

    def test_duplicate_frame_or_prediction_rejected(self):
        refs,frames=self.fixture()
        with self.assertRaises(ValueError):score_classification_review(refs,frames*2,source_sha256='source')
        frames[0]['detections']*=2
        with self.assertRaises(ValueError):score_classification_review(refs,frames,source_sha256='source')
