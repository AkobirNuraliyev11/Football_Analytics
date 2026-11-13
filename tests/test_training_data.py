import tempfile,unittest
from pathlib import Path
from football_intelligence.benchmarks.training_data import audit_soccertrack_csv,validate_training_split


class TrainingDataTests(unittest.TestCase):
    def sources(self):
        return [dict(match_id=str(i),split=s,source_sha256=str(i)*64,box_semantics='tight_box',annotation_complete=True)
                for i,s in enumerate(('train','validation','test'))]

    def test_match_and_duplicate_source_leakage_are_rejected(self):
        rows=self.sources();self.assertEqual(validate_training_split(rows)['matches'],3)
        rows[1]['match_id']=rows[0]['match_id']
        with self.assertRaisesRegex(ValueError,'Same match'):validate_training_split(rows)
        rows=self.sources();rows[1]['source_sha256']=rows[0]['source_sha256']
        with self.assertRaisesRegex(ValueError,'Same source'):validate_training_split(rows)

    def test_incomplete_targets_and_missing_partitions_block_training(self):
        rows=self.sources();rows[0]['annotation_complete']=False
        with self.assertRaisesRegex(ValueError,'complete'):validate_training_split(rows)
        rows=self.sources();rows[0]['box_semantics']='center_proxy'
        with self.assertRaisesRegex(ValueError,'tight boxes'):validate_training_split(rows)
        with self.assertRaisesRegex(ValueError,'separate'):validate_training_split(self.sources()[:2])

    def test_repeated_sizes_are_diagnostic_not_automatic_training_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'labels.csv'
            p.write_text('TeamID,0,0,0,0\nPlayerID,1,1,1,1\nAttributes,bb_height,bb_left,bb_top,bb_width\nframe,,,,\n1,39,10,10,39\n2,39,12,10,39\n')
            r=audit_soccertrack_csv(p)
            self.assertEqual(r['classes']['person']['most_common_size_fraction'],1)
            self.assertFalse(r['detector_training_ready'])
            p.write_text(p.read_text().replace('2,39,12','2,nan,12'))
            with self.assertRaises(ValueError):audit_soccertrack_csv(p)
