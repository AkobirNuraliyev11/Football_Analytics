from dataclasses import replace
import importlib.util
from pathlib import Path
import unittest

from football_intelligence.calibration import (CalibrationError, Landmark, fit_calibration,
    fit_landmark_file, update_camera, transform)
from football_intelligence.models import PixelPoint, PitchPoint, BoundingBox, AthleteObservation


@unittest.skipUnless(importlib.util.find_spec("cv2") and importlib.util.find_spec("numpy"),
                     "Install .[calibration] for calibration tests")
class CalibrationTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np
        self.context = dict(match_id="test", shot_id=0, frame_index=0, width=1280, height=720)
        # Genuine perspective mapping from known ground meters to raster pixels.
        self.camera = np.array([[8, 1, 100], [.2, 6, 80], [.001, .002, 1.]])
        world = [(0,0), (105,0), (105,68), (0,68), (52.5,0), (52.5,68), (11,34), (94,34)]
        pixels = transform(self.camera, world)
        self.landmarks = [Landmark(str(i), PixelPoint(*map(float, p)), PitchPoint(*w))
                          for i, (p,w) in enumerate(zip(pixels,world))]

    def project(self, cal, point, **overrides):
        return cal.project(point, **(self.context | overrides))

    def test_recovers_perspective_and_independent_validation(self):
        center = transform(self.camera, [[52.5, 34]])[0]
        check = Landmark("center", PixelPoint(*map(float, center)), PitchPoint(52.5, 34))
        cal = fit_calibration(self.landmarks, **self.context, validation_landmarks=[check])
        actual = self.project(cal, check.pixel)
        self.assertAlmostEqual(actual.x_m, 52.5, places=4)
        self.assertAlmostEqual(actual.y_m, 34, places=4)
        self.assertLess(cal.validation_rmse_m, 0.001)
        self.assertEqual(cal.validation_count, 1)

    def test_ransac_rejects_bad_correspondence(self):
        wrong = Landmark("wrong", PixelPoint(500, 200), PitchPoint(2, 64))
        cal = fit_calibration(self.landmarks + [wrong], **self.context)
        self.assertNotIn("wrong", cal.inlier_names)
        self.assertLess(cal.fit_rmse_m, 0.001)
        self.assertIsNone(cal.validation_rmse_m)

    def test_degenerate_and_duplicate_landmarks_fail(self):
        line = [Landmark(str(i), PixelPoint(100+i*50, 100), PitchPoint(i*10, 0)) for i in range(5)]
        for items in [self.landmarks[:3], line, self.landmarks + [self.landmarks[0]]]:
            with self.assertRaises(CalibrationError):
                fit_calibration(items, **self.context)

    def test_stale_or_mismatched_scope_fails(self):
        cal = fit_calibration(self.landmarks, **self.context)
        for override in [{"shot_id": 1}, {"frame_index": 1}, {"width": 640}, {"match_id": "other"}]:
            with self.subTest(override=override), self.assertRaises(CalibrationError):
                self.project(cal, PixelPoint(400, 250), **override)

    def test_extrapolation_and_horizon_fail(self):
        cal = fit_calibration(self.landmarks, **self.context)
        with self.assertRaises(CalibrationError):
            self.project(cal, PixelPoint(1200, 650))
        with self.assertRaises(CalibrationError):
            transform([[1,0,0],[0,1,0],[0,1,-1]], [[0,1]])

    def test_validation_error_rejects_fit(self):
        wrong = Landmark("check", PixelPoint(500, 250), PitchPoint(1, 1))
        with self.assertRaisesRegex(CalibrationError, "Independent validation"):
            fit_calibration(self.landmarks, **self.context, validation_landmarks=[wrong])

    def test_uncertain_ground_contact_clears_old_projection(self):
        cal = fit_calibration(self.landmarks, **self.context)
        obs = AthleteObservation("test", 0, 1, 0, 0, BoundingBox(300,100,320,250), .9,
                                 pitch_position=PitchPoint(10,10), calibration_id="old")
        result = cal.project_observation(obs, width=1280, height=720)
        self.assertIsNone(result.pitch_position)
        self.assertIsNone(result.calibration_id)

    def test_camera_translation_and_cut_reset(self):
        import cv2
        np = self.np
        rng = np.random.default_rng(42)
        old = rng.integers(0, 256, (720,1280,3), dtype=np.uint8)
        new = cv2.warpAffine(old, np.float32([[1,0,3],[0,1,2]]), (1280,720))
        cal = fit_calibration(self.landmarks, **self.context)
        kwargs = dict(match_id="test", shot_id=0, frame_index=1,
                      previous_timestamp_s=0, timestamp_s=.04)
        updated = update_camera(old, new, cal, **kwargs)
        center = transform(self.camera, [[52.5,34]])[0] + [3,2]
        projected = updated.project(PixelPoint(*map(float,center)), **(self.context | {"frame_index":1}))
        self.assertAlmostEqual(projected.x_m, 52.5, delta=.1)
        self.assertAlmostEqual(projected.y_m, 34, delta=.1)
        self.assertEqual(updated.parent_id, cal.calibration_id)
        self.assertIsNone(updated.validation_rmse_m)
        for changes in [{"shot_id":1}, {"timestamp_s":1}, {"frame_index":3}]:
            with self.assertRaises(CalibrationError):
                update_camera(old, new, cal, **(kwargs | changes))

    def test_textureless_camera_update_fails(self):
        blank = self.np.zeros((720,1280,3), dtype=self.np.uint8)
        cal = fit_calibration(self.landmarks, **self.context)
        with self.assertRaises(CalibrationError):
            update_camera(blank, blank, cal, match_id="test", shot_id=0, frame_index=1,
                          previous_timestamp_s=0, timestamp_s=.04)

    def test_shipped_example(self):
        result = fit_landmark_file(Path(__file__).resolve().parents[1]/"examples/calibration-landmarks.json")
        self.assertEqual(result["validation_count"], 2)
        self.assertLess(result["validation_rmse_m"], .001)


if __name__ == "__main__":
    unittest.main()
