from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest

from football_intelligence.cli import main
from football_intelligence.config import AppConfig, PitchConfig
from football_intelligence.models import AthleteObservation, BoundingBox, PitchPoint, Role, Team


class ConfigurationTests(unittest.TestCase):
    def test_shipped_configuration_matches_defaults(self):
        path = Path(__file__).resolve().parents[1] / "configs" / "default.json"
        self.assertEqual(AppConfig.load(path), AppConfig())

    def test_partial_configuration_merges_defaults(self):
        config = AppConfig.from_dict({"analytics": {"sprint_threshold_kmh": 20}})
        self.assertEqual(config.analytics.sprint_threshold_kmh, 20)
        self.assertEqual(config.pitch.length_m, 105)
        self.assertEqual(AppConfig.from_dict(config.to_dict()), config)

    def test_invalid_configuration_is_rejected(self):
        cases = [[], {"unknown": 1}, {"schema_version": True}, {"schema_version": 2},
                 {"pitch": None}, {"pitch": {"width": 68}},
                 {"pitch": {"width_m": 0}}, {"pitch": {"width_m": True}},
                 {"pitch": {"width_m": "68"}}, {"pitch": {"width_m": float("nan")}},
                 {"analytics": {"max_speed_kmh": float("inf")}},
                 {"analytics": {"sprint_threshold_kmh": 36}},
                 {"analytics": {"max_observation_gap_s": 0}},
                 {"analytics": {"highlight_padding_s": -1}}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                AppConfig.from_dict(case)

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"pitch": {"width_m": 68, "width_m": 70}}')
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                AppConfig.load(path)

    def test_cli_emits_machine_readable_config(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["default-config"]), 0)
        self.assertEqual(json.loads(output.getvalue()), AppConfig().to_dict())

    def test_cli_reports_invalid_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"pitch": {"width_m": -1}}')
            error = io.StringIO()
            with redirect_stderr(error):
                self.assertEqual(main(["validate-config", str(path)]), 2)
            self.assertIn("Configuration error", error.getvalue())


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.observation = AthleteObservation(
            match_id="match-001", shot_id=0, track_id=7, frame_index=30,
            timestamp_s=1.0, bbox=BoundingBox(10, 20, 30, 80),
            detection_confidence=0.9)

    def test_anchor_uses_feet_not_center(self):
        anchor = self.observation.bbox.foot_anchor
        self.assertEqual((anchor.x, anchor.y), (20, 80))

    def test_boundaries_are_inclusive_without_clamping(self):
        pitch = PitchConfig()
        for x, y in [(0, 0), (105, 68), (52.5, 34)]:
            self.assertTrue(PitchPoint(x, y).is_on_pitch(pitch))
        for x, y in [(-0.01, 34), (105.01, 34), (50, -0.01), (50, 68.01)]:
            self.assertFalse(PitchPoint(x, y).is_on_pitch(pitch))

    def test_unverified_or_off_pitch_samples_cannot_be_eligible(self):
        self.assertFalse(self.observation.is_planar_sample_eligible(PitchConfig()))
        projected = replace(self.observation, pitch_position=PitchPoint(30, 20), calibration_id="cal-1")
        self.assertFalse(projected.is_planar_sample_eligible(PitchConfig()))
        grounded = replace(projected, ground_contact_reliable=True)
        self.assertTrue(grounded.is_planar_sample_eligible(PitchConfig()))
        self.assertFalse(replace(grounded, pitch_position=PitchPoint(106, 20))
                         .is_planar_sample_eligible(PitchConfig()))

    def test_track_keys_change_across_camera_cuts(self):
        self.assertNotEqual(self.observation.track_key, replace(self.observation, shot_id=1).track_key)

    def test_invalid_observations_are_rejected(self):
        cases = [{"timestamp_s": -1}, {"timestamp_s": float("inf")}, {"track_id": True},
                 {"frame_index": 1.5}, {"detection_confidence": 1.1}, {"bbox": {}},
                 {"match_id": " "}, {"team": "A"}, {"ground_contact_reliable": 1},
                 {"role": Role.OFFICIAL, "team": Team.A},
                 {"pitch_position": PitchPoint(30, 20)}, {"calibration_id": ""}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                replace(self.observation, **case)

    def test_invalid_geometry_is_rejected(self):
        for box in [(10, 10, 10, 30), (20, 10, 10, 30), (0, 0, 20, float("nan"))]:
            with self.subTest(box=box), self.assertRaises(ValueError):
                BoundingBox(*box)
        with self.assertRaises(ValueError):
            PitchPoint(float("inf"), 0)

    def test_observation_serializes_without_custom_encoder(self):
        record = json.loads(json.dumps(self.observation.to_dict(), allow_nan=False))
        self.assertEqual(record["role"], "unknown")
        self.assertIsNone(record["pitch_position"])
        self.assertEqual(record["bbox"]["y_max"], 80)


if __name__ == "__main__":
    unittest.main()
