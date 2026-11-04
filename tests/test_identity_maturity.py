import unittest
from football_intelligence.telemetry import TelemetryEngine
from test_telemetry import frame


def reviewed(t, **kwargs):
    f=frame(t,**kwargs)
    f["detections"][0]["measurement_evidence"]={"status":"line_checked_estimate",
        "ground_evidence":"visible_feet_candidate","camera_stable":True}
    return f


class IdentityMaturityTests(unittest.TestCase):
    def test_noisy_known_motion_keeps_shared_values_and_bounded_error(self):
        from scripts.compare_maturity import synthetic_check
        result=synthetic_check()
        self.assertTrue(all(c["candidate_samples"]>c["baseline_samples"] for c in result["cases"]))

    def test_reacquired_geometry_keeps_identity_age_but_needs_full_window(self):
        baseline=TelemetryEngine(experimental=True)
        candidate=TelemetryEngine(experimental=True,separate_identity_maturity=True)
        for i in range(36):
            f=reviewed(i/10)
            if i<25: f["detections"][0]["pitch_position_candidate"]=None
            a=baseline.update(f)["observations"][0]
            b=candidate.update(f)["observations"][0]
            if i<30: self.assertNotEqual(b["status"],"measured")
            if i>=30:
                self.assertEqual(b["status"],"measured")
                self.assertAlmostEqual(b["speed_kmh"],10.8)
                self.assertAlmostEqual(b["observed_distance_m"],(i/10-2.5)*3)
            self.assertNotEqual(a["status"],"measured")
        row=candidate.finish()["fragments"][0]
        self.assertEqual(row["start_s"],2.5)
        self.assertEqual(row["identity_start_s"],0)
        self.assertAlmostEqual(row["observed_distance_m"],3)

    def test_ghost_is_still_excluded(self):
        engine=TelemetryEngine(experimental=True,separate_identity_maturity=True)
        for i in range(20):
            self.assertNotEqual(engine.update(reviewed(i/10))["observations"][0]["status"],"measured")
        self.assertFalse(engine.finish()["fragments"])

    def test_missing_detection_and_identity_changes_reset_age(self):
        for mode in ("missing","unsafe","team","segment","role","shot","gap"):
            e=TelemetryEngine(experimental=True,separate_identity_maturity=True)
            for i in range(31):
                f=reviewed(i/10)
                if i<20: f["detections"][0]["pitch_position_candidate"]=None
                if i==20 and mode=="missing": f["detections"]=[]
                if i==20 and mode=="unsafe": f["detections"][0]["continuity_safe"]=False
                if i>=20:
                    if mode=="team": f["detections"][0]["team"]="B"
                    if mode=="segment": f["detections"][0]["continuity_segment"]=1
                    if mode=="role": f["detections"][0]["role"]="goalkeeper"
                    if mode=="shot": f["shot_id"]=1
                    if mode=="gap": f["timestamp_s"]+=1; f["frame_index"]+=1000
                result=e.update(f)
                self.assertTrue(all(v["status"]!="measured" for v in result["observations"]),mode)
            self.assertFalse(e.finish()["fragments"],mode)

    def test_bad_frame_never_interpolated_and_no_gap_distance(self):
        e=TelemetryEngine(experimental=True,separate_identity_maturity=True)
        for i in range(41):
            f=reviewed(i/10)
            if i==25: f["detections"][0]["pitch_position_candidate"]=None
            result=e.update(f)["observations"][0]
            if i==25: self.assertIsNone(result["speed_kmh"])
        rows=e.finish()["fragments"]
        self.assertEqual(len(rows),2)
        self.assertAlmostEqual(sum(r["observed_distance_m"] for r in rows),(2.4+1.4)*3)
        self.assertEqual(rows[1]["start_s"],2.6)

    def test_teleport_resets_identity_and_never_seeds_from_outlier(self):
        e=TelemetryEngine(experimental=True,separate_identity_maturity=True)
        for i in range(36):
            f=reviewed(i/10,x=50 if i==25 else 3*i/10)
            result=e.update(f)["observations"][0]
            if i>=25: self.assertNotEqual(result["status"],"measured")
        self.assertEqual(len(e.finish()["fragments"]),1)

    def test_strict_mode_cannot_enable_policy(self):
        with self.assertRaises(ValueError): TelemetryEngine(separate_identity_maturity=True)
