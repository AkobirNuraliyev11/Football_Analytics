import unittest
from scripts.audit_automatic_calibration import geometry_discrepancy


class GeometryDiscrepancyTests(unittest.TestCase):
    def test_rotation_is_distinguished_from_distortion(self):
        reference = [[0, 0], [105, 0], [0, 68]]
        rotated = [[105-x, 68-y] for x, y in reference]
        result = geometry_discrepancy(rotated, reference)
        self.assertEqual(result['symmetry_median_discrepancy_m']['rotate_180'], 0)
        self.assertEqual(result['median_pair_distance_discrepancy_m'], 0)
        distorted = [[x/2, y/2] for x, y in reference]
        result = geometry_discrepancy(distorted, reference)
        self.assertGreater(result['median_pair_distance_discrepancy_m'], 30)

    def test_missing_is_not_zero_error(self):
        self.assertIsNone(geometry_discrepancy([], [])['median_pair_distance_discrepancy_m'])
        self.assertIsNone(geometry_discrepancy([[1, 1]], [[1, 1]])['median_pair_distance_discrepancy_m'])
