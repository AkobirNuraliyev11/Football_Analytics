import copy
import json
from pathlib import Path
import tempfile
import unittest

from football_intelligence.config import AppConfig, AnalyticsConfig

try:
    import numpy as np
    import cv2
    import av
except ImportError:
    np = None


def frame(i, t, *, x=40, team="A", role="outfield", shot=0, reference="test-pitch"):
    return {"match_id":"fixture", "shot_id":shot,"frame_index":i,"timestamp_s":t,
        "calibration_status":"validated","detections":[{
            "track_id":1,"kind":"person","role":role,"team":team,"confirmed":True,
            "continuity_safe":True,"measurement_link_eligible":True,"classification_conflict":False,
            "team_changed":False,"continuity_segment":0,"calibration_id":"test",
            "coordinate_reference_id":reference,"ground_contact_reliable":True,
            "projection_state":"validated_ground_position","pitch_position_candidate":{"x_m":x,"y_m":30}}]}


@unittest.skipIf(np is None,"Tactical rendering dependencies not installed")
class TacticalTests(unittest.TestCase):
    def engine(self, **kwargs):
        from football_intelligence.tactical import TacticalEngine
        config=AppConfig(analytics=AnalyticsConfig(min_track_duration_s=.1,smoothing_window_s=.1))
        return TacticalEngine(config,**kwargs)

    def test_known_duration_and_mass(self):
        e=self.engine()
        for i,t in enumerate([0,.1,.2,.3,.4]):
            result=e.update(frame(i,t,x=40+t))
        self.assertEqual(len(result["positions"]),1)
        summary=e.finish()
        for group in summary["groups"]:
            self.assertAlmostEqual(group["observed_person_seconds"],.3)
            self.assertAlmostEqual(np.sum(group["occupancy_seconds"]),.3)
            self.assertAlmostEqual(np.sum(group["smoothed_seconds"]),.3)
            self.assertAlmostEqual(np.sum(group["probability_mass"]),1)

    def test_sampling_rate_invariance(self):
        results=[]
        for times in ([0,.1,.2,.3,.4],[0,.1,.15,.2,.35,.4]):
            e=self.engine()
            for i,t in enumerate(times): e.update(frame(i,t))
            results.append(e.finish()["groups"][0]["occupancy_seconds"])
        np.testing.assert_allclose(results[0],results[1],atol=1e-12)

    def test_gaps_and_cuts_never_bridge(self):
        e=self.engine()
        for i,t in enumerate([0,.1,.2]): e.update(frame(i,t))
        missing=frame(3,.3);missing["detections"]=[]
        self.assertFalse(e.update(missing)["positions"])
        for i,t in enumerate([.4,.5,.6],4): e.update(frame(i,t))
        e.update(frame(7,1.0))  # Too long a timestamp gap.
        e.update(frame(8,1.1,shot=1))
        summary=e.finish()
        tracks=[g for g in summary["groups"] if g["identity"]["type"]=="track"]
        self.assertAlmostEqual(sum(g["observed_person_seconds"] for g in tracks),.2)

    def test_invalid_position_and_ground_contact_are_withheld(self):
        for change in ({"ground_contact_reliable":False},
                       {"pitch_position_candidate":{"x_m":106,"y_m":30}},
                       {"continuity_safe":False}):
            e=self.engine()
            for i in range(5):
                f=frame(i,i*.1);f["detections"][0].update(change)
                self.assertEqual(e.update(f)["positions"],[])
            self.assertEqual(e.finish()["status"],"unavailable")

    def test_reference_and_team_changes_reset(self):
        e=self.engine()
        for i in range(7):
            result=e.update(frame(i,i*.1,reference="a" if i<3 else "b",team="A" if i<5 else "B"))
            if i in (3,5): self.assertFalse(result["positions"])
        groups=e.finish()["groups"]
        self.assertEqual({g["identity"]["coordinate_reference_id"] for g in groups},{"a","b"})

    def test_officials_and_unknown_teams_not_in_team_maps(self):
        for role,team in [("official","unknown"),("outfield","unknown")]:
            e=self.engine()
            for i in range(4): e.update(frame(i,i*.1,team=team,role=role))
            self.assertTrue(all(g["identity"]["type"]=="track" for g in e.finish()["groups"]))

    def test_edge_gaussian_conserves_mass(self):
        from football_intelligence.tactical import gaussian_density
        grid=np.zeros((68,105));grid[0,0]=2;grid[-1,-1]=3
        smooth=gaussian_density(grid,2)
        self.assertAlmostEqual(smooth.sum(),5)
        self.assertTrue(np.all(smooth>=0))
        self.assertEqual(smooth[34,52],0)

    def test_boundary_cell_and_empty_heatmap(self):
        e=self.engine()
        for i in range(4):
            f=frame(i,i*.1,x=105);f["detections"][0]["pitch_position_candidate"]["y_m"]=68
            e.update(f)
        for group in e.finish()["groups"]:
            self.assertGreater(group["occupancy_seconds"][-1][-1],0)

    def test_teleport_not_drawn_or_integrated(self):
        e=self.engine()
        for i in range(3): e.update(frame(i,i*.1))
        self.assertEqual(e.update(frame(3,.3,x=90))["positions"],[])
        for group in e.finish()["groups"]:
            self.assertAlmostEqual(group["observed_person_seconds"],.1)

    def test_experimental_evidence_is_explicit(self):
        e=self.engine(experimental=True)
        for i in range(4):
            f=frame(i,i*.1);f["calibration_status"]="unvalidated"
            f["detections"][0].update(ground_contact_reliable=False,measurement_evidence={
                "status":"line_checked_estimate","ground_evidence":"visible_feet_candidate","camera_stable":True})
            result=e.update(f)
        self.assertEqual(result["positions"][0]["quality"],"experimental_estimate")

    def test_input_monotonicity(self):
        e=self.engine();e.update(frame(0,0))
        with self.assertRaises(ValueError): e.update(frame(1,0))

    def test_render_rotation_does_not_change_coordinates(self):
        from football_intelligence.tactical_render import radar_image
        e=self.engine()
        for i in range(3): result=e.update(frame(i,i*.1,x=10))
        before=copy.deepcopy(result)
        pitch={"length_m":105,"width_m":68}
        normal=radar_image(result,pitch,scale=6)
        rotated=radar_image(result,pitch,scale=6,rotate=True)
        np.testing.assert_array_equal(normal[270,100],rotated[318,610])
        self.assertEqual(result,before)

    def test_publication_and_video_timestamps(self):
        from football_intelligence.tactical_io import build_tactics
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/"tracks.jsonl"
            source.write_text("".join(json.dumps(frame(i,t))+"\n" for i,t in enumerate([0,.1,.24,.4])))
            result=build_tactics(source,root/"out",config=self.engine().config)
            self.assertEqual(result["status"],"completed")
            with av.open(str(root/"out/preview.mp4")) as video:
                times=[f.time for f in video.decode(video=0)]
            np.testing.assert_allclose(times,[0,.1,.24,.4],atol=1e-6)
            self.assertTrue((root/"out/occupancy.json").is_file())
            self.assertFalse((root/"out/partial").exists())

    def test_empty_input_failure_and_no_final_artifacts(self):
        from football_intelligence.tactical_io import build_tactics
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/"tracks.jsonl";source.write_text("")
            with self.assertRaises(ValueError): build_tactics(source,root/"out")
            self.assertEqual(json.loads((root/"out/manifest.json").read_text())["status"],"failed")
            self.assertFalse((root/"out/radar.jsonl").exists())

    def test_review_hash_and_sync_guards(self):
        from football_intelligence.tactical_io import build_tactics, input_frames
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/"tracks.jsonl"
            source.write_text(json.dumps(frame(0,0))+"\n")
            (root/"manifest.json").write_text(json.dumps({"status":"completed","tracks_sha256":"wrong"}))
            with self.assertRaises(ValueError): build_tactics(source,root/"out",review=root)
            (root/"quality.jsonl").write_text(json.dumps(frame(1,.1))+"\n")
            with self.assertRaises(ValueError): list(input_frames(source,root))
            (root/"quality.jsonl").write_text("")
            with self.assertRaises(ValueError): list(input_frames(source,root))
