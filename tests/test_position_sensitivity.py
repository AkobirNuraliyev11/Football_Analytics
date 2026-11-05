import unittest
import importlib.util
from dataclasses import replace

from football_intelligence.calibration import CalibrationError
from football_intelligence.config import AppConfig, AnalyticsConfig
from football_intelligence.position_sensitivity import pixel_square_radius, interval_sensitivity
from football_intelligence.telemetry import TelemetryEngine
from test_telemetry import frame


@unittest.skipUnless(importlib.util.find_spec("numpy"), "Requires calibration extras")
class PixelSensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global np
        import numpy as np

    def test_affine_square_bound_and_interval_units(self):
        matrix = np.diag([.1, .2, 1])
        point, radius = pixel_square_radius(matrix, [10, 10], 3)
        np.testing.assert_allclose(point, [1, 2])
        self.assertAlmostEqual(radius, np.hypot(.3, .6))
        result = interval_sensitivity(matrix, [10, 10], matrix, [20, 10], 2, 3)
        self.assertAlmostEqual(result['nominal_net_speed_kmh'], 1.8)
        self.assertAlmostEqual(result['pixel_only_speed_radius_kmh'], radius*3.6)
        self.assertEqual(result['pixel_only_speed_range_kmh'][0], 0)

    def test_horizon_and_invalid_values_are_rejected(self):
        with self.assertRaises(CalibrationError):
            pixel_square_radius([[1,0,0],[0,1,0],[1,0,0]], [1,0], 3)
        for radius in [-1, float('nan'), True]:
            with self.assertRaises(ValueError):
                pixel_square_radius(np.eye(3), [0,0], radius)
        for duration in [0, -1, float('inf')]:
            with self.assertRaises(ValueError):
                interval_sensitivity(np.eye(3), [0,0], np.eye(3), [1,0], duration)

    def test_projective_bound_contains_perturbed_points(self):
        from football_intelligence.calibration import transform
        matrix = np.array([[.1,.01,2],[0,.15,3],[.001,.002,1]])
        pixel = np.array([120.,80.])
        center, radius = pixel_square_radius(matrix, pixel)
        samples = np.array([pixel+[x,y] for x in np.linspace(-3,3,19) for y in np.linspace(-3,3,19)])
        self.assertLessEqual(np.linalg.norm(transform(matrix,samples)-center,axis=1).max(), radius+1e-12)

    def test_variable_time_window_uses_interpolated_endpoint_radii(self):
        cfg = AppConfig(analytics=replace(AnalyticsConfig(), min_track_duration_s=.5))
        engine = TelemetryEngine(cfg)
        for t, radius in [(0,.1),(.2,.2),(.4,.3),(.6,.4)]:
            row = frame(t, measurement_evidence={'pixel_localization_radius_m':radius})
            result = engine.update(row)['observations'][0]
        # Cutoff=.1, midway between radii .1 and .2. Current radius=.4.
        self.assertAlmostEqual(result['speed_pixel_sensitivity_kmh'], (.15+.4)/.5*3.6)
        self.assertAlmostEqual(result['speed_kmh'], 10.8)
        self.assertAlmostEqual(result['speed_pixel_range_kmh'][0], 6.84)

    def test_missing_endpoint_evidence_stays_unavailable(self):
        engine = TelemetryEngine()
        for i in range(31):
            result = engine.update(frame(i/10))['observations'][0]
        self.assertEqual(result['status'], 'measured')
        self.assertIsNone(result['speed_pixel_range_kmh'])
        self.assertIsNone(result['speed_pixel_sensitivity_kmh'])
