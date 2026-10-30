from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest

from football_intelligence.cli import main
from football_intelligence.config import AppConfig, AnalyticsConfig
from football_intelligence.telemetry import TelemetryEngine
from football_intelligence.telemetry_io import compute_telemetry


def frame(t, x=None, **changes):
    item = {"track_id": 1, "kind": "person", "role": "outfield", "team": "A",
            "confirmed": True, "continuity_safe": True, "measurement_link_eligible": True,
            "classification_conflict": False, "team_changed": False, "continuity_segment": 0,
            "calibration_id": f"cal-{t}", "coordinate_reference_id": "fixture-pitch",
            "ground_contact_reliable": True, "projection_state": "validated_ground_position",
            "pitch_position_candidate": {"x_m": 10+(3*t if x is None else x), "y_m": 20}}
    item.update(changes)
    return {"match_id": "fixture", "shot_id": 0, "frame_index": round(t*1000),
            "timestamp_s": t, "calibration_status": "validated", "detections": [item]}


class TelemetryTests(unittest.TestCase):
    def test_known_motion_variable_timing_and_calibration_ids(self):
        engine = TelemetryEngine()
        times = [0]
        for i in range(20):
            times.append(times[-1]+(.07 if i%2 else .23))
        for t in times:
            result = engine.update(frame(t))
        item = result["observations"][0]
        self.assertAlmostEqual(item["speed_kmh"], 10.8)
        self.assertAlmostEqual(item["observed_distance_m"], 9)
        summary = engine.finish()
        self.assertEqual(len(summary["fragments"]), 1)
        self.assertAlmostEqual(summary["fragments"][0]["observed_duration_s"], 3)
        self.assertEqual(summary["fragments"][0]["sprint_count"], 0)
        self.assertEqual(summary, engine.finish())
        with self.assertRaises(ValueError): engine.update(frame(4))

    def test_zero_speed_is_measured_not_missing(self):
        engine = TelemetryEngine()
        for i in range(31): result = engine.update(frame(i/10, x=0))
        self.assertEqual(result["observations"][0]["speed_kmh"], 0)
        self.assertEqual(engine.finish()["fragments"][0]["observed_distance_m"], 0)

    def test_sprint_duration_two_bursts_and_terminal_truncation(self):
        cfg = AppConfig(analytics=replace(AnalyticsConfig(), smoothing_window_s=.05))
        engine = TelemetryEngine(cfg)
        x=0
        for i in range(61):
            if i: x += .6 if i<=20 or i>40 else .2
            engine.update(frame(i/10, x=x))
        row = engine.finish()["fragments"][0]
        self.assertEqual(row["sprint_count"], 2)
        first, second = row["sprints"]
        self.assertAlmostEqual(first["duration_s"], 2)
        self.assertFalse(first["truncated"])
        self.assertTrue(second["truncated"])
        self.assertAlmostEqual(second["start_s"], 4)
        self.assertAlmostEqual(row["observed_distance_m"], 28)

    def test_short_burst_and_exact_threshold_are_not_sprints(self):
        cfg = AppConfig(analytics=replace(AnalyticsConfig(), smoothing_window_s=.05))
        engine = TelemetryEngine(cfg)
        x=0
        for i in range(41):
            if i: x += .6 if i<=5 else .5
            engine.update(frame(i/10, x=x))
        self.assertEqual(engine.finish()["fragments"][0]["sprint_count"], 0)

    def test_jitter_is_smoothed_in_vector_space(self):
        engine = TelemetryEngine()
        for i in range(101):
            engine.update(frame(i*.04, x=.02*(-1)**i))
        row = engine.finish()["fragments"][0]
        self.assertLess(row["observed_distance_m"], .5)  # Raw jitter path is four meters.

    def test_quality_failures_withhold_and_break_links(self):
        cases = [({"ground_contact_reliable":False}, "ground_contact_unverified"),
                 ({"measurement_link_eligible":False}, "uncertain_association"),
                 ({"team_changed":True}, "classification_discontinuity"),
                 ({"classification_conflict":True}, "classification_discontinuity"),
                 ({"pitch_position_candidate":{"x_m":106,"y_m":20}}, "outside_pitch"),
                 ({"coordinate_reference_id":None}, "missing_coordinate_reference_id")]
        for changes, reason in cases:
            with self.subTest(reason=reason):
                engine=TelemetryEngine()
                for i in range(21): engine.update(frame(i/10))
                result=engine.update(frame(2.1,**changes))["observations"][0]
                self.assertIsNone(result["speed_kmh"])
                self.assertIn(reason,result["reasons"])
                self.assertEqual(engine.update(frame(2.2))["observations"][0]["status"],"warming_up")
                self.assertAlmostEqual(engine.finish()["fragments"][0]["observed_distance_m"],6)

    def test_automatic_candidates_never_become_measurements(self):
        engine=TelemetryEngine()
        for i in range(31):
            f=frame(i/10,ground_contact_reliable=False,projection_state="ground_contact_unverified")
            f["calibration_status"]="fit_unvalidated"
            result=engine.update(f)
        self.assertIsNone(result["observations"][0]["observed_distance_m"])
        summary=engine.finish()
        self.assertEqual(summary["status"],"unavailable")
        self.assertEqual(summary["rejection_counts"]["calibration_unvalidated"],31)

    def test_short_tracks_do_not_enter_leaderboard(self):
        engine=TelemetryEngine()
        for i in range(10): engine.update(frame(i/10,x=.6*i))
        summary=engine.finish()
        self.assertEqual(summary["fragments"],[])
        self.assertEqual(summary["discarded_short_fragments"],1)

    def test_teleport_is_rejected_before_smoothing(self):
        engine=TelemetryEngine()
        for i in range(21): engine.update(frame(i/10))
        item=engine.update(frame(2.1,x=40))["observations"][0]
        self.assertEqual(item["reasons"],["implausible_displacement"])
        self.assertEqual(engine.update(frame(2.2))["observations"][0]["status"],"warming_up")
        self.assertAlmostEqual(engine.finish()["fragments"][0]["top_speed_kmh"],10.8)

    def test_displacement_cap_uses_elapsed_time(self):
        engine=TelemetryEngine()
        engine.update(frame(0,x=0))
        accepted=engine.update(frame(.2,x=2))["observations"][0]
        self.assertNotIn("implausible_displacement",accepted["reasons"])
        rejected=engine.update(frame(.3,x=3.01))["observations"][0]
        self.assertEqual(rejected["reasons"],["implausible_displacement"])

    def test_short_sprints_cannot_join_across_missing_observations(self):
        cfg=AppConfig(analytics=replace(AnalyticsConfig(),min_track_duration_s=.2,smoothing_window_s=.05))
        engine=TelemetryEngine(cfg)
        for i in range(22):
            f=frame(i/10,x=i*.6)
            if i in {7,14}: f["detections"]=[]
            engine.update(f)
        summary=engine.finish()
        self.assertEqual(len(summary["fragments"]),3)
        self.assertEqual(sum(r["sprint_count"] for r in summary["fragments"]),0)

    def test_gap_shot_and_identity_changes_start_new_fragments(self):
        for change in ("gap","shot","segment","reference","team","role","missing"):
            with self.subTest(change=change):
                engine=TelemetryEngine()
                for i in range(21): engine.update(frame(i/10))
                f=frame(2.1)
                if change=="gap": f=frame(2.5)
                if change=="shot": f["shot_id"]=1
                if change=="segment": f["detections"][0]["continuity_segment"]=1
                if change=="reference": f["detections"][0]["coordinate_reference_id"]="other"
                if change=="team": f["detections"][0]["team"]="B"
                if change=="role": f["detections"][0]["role"]="official"
                if change=="missing": f["detections"]=[]
                out=engine.update(f)
                if out["observations"]: self.assertIsNone(out["observations"][0]["speed_kmh"])
                self.assertAlmostEqual(engine.finish()["fragments"][0]["observed_distance_m"],6)

    def test_invalid_sequences_and_positions_fail(self):
        for change in ("duplicate","time","frame","nan","match"):
            with self.subTest(change=change):
                engine=TelemetryEngine()
                engine.update(frame(0))
                f=frame(.1)
                if change=="duplicate": f["detections"]*=2
                if change=="time": f["timestamp_s"]=0
                if change=="frame": f["frame_index"]=0
                if change=="nan": f["detections"][0]["pitch_position_candidate"]["x_m"]=float("nan")
                if change=="match": f["match_id"]="other"
                with self.assertRaises(ValueError): engine.update(f)

    def test_ball_excluded_and_official_kept_separate(self):
        engine=TelemetryEngine()
        for i in range(21):
            f=frame(i/10,role="official",team="unknown")
            ball=deepcopy(f["detections"][0]);ball.update(track_id=2,kind="ball")
            f["detections"].append(ball)
            result=engine.update(f)
        self.assertEqual(result["observations"][1]["reasons"],["non_person"])
        self.assertEqual(engine.finish()["fragments"][0]["role"],"official")

    def test_cli_exports_and_failure_never_publishes_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/"tracks.jsonl";output=root/"run"
            source.write_text("\n".join(json.dumps(frame(i/10)) for i in range(31))+"\n")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["compute-telemetry",str(source),"--output",str(output)]),0)
            summary=json.loads((output/"telemetry-summary.json").read_text())
            self.assertAlmostEqual(summary["fragments"][0]["observed_distance_m"],9)
            with self.assertRaises(FileExistsError):compute_telemetry(source,output)
            source.write_text(json.dumps(frame(0))+"\n{}\n")
            failed=root/"failed"
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["compute-telemetry",str(source),"--output",str(failed)]),2)
            self.assertEqual(json.loads((failed/"manifest.json").read_text())["status"],"failed")
            self.assertFalse((failed/"telemetry.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
