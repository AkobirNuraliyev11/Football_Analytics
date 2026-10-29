from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from football_intelligence.calibration import CalibrationError
from football_intelligence.config import PitchConfig
from football_intelligence.detection import Detection, landmarks_from_keypoints
from football_intelligence.models import BoundingBox


@unittest.skipUnless(all(importlib.util.find_spec(p) for p in ("numpy","cv2","scipy")), "Install detection dependencies")
class TrackingTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from football_intelligence.tracking import MultiObjectTracker
        self.tracker = MultiObjectTracker(min_hits=2)
        self.rgb = np.zeros((100,200,3),dtype=np.uint8)

    def detection(self,x=10,kind="person",confidence=.9):
        return Detection(BoundingBox(x,20,x+20,70),confidence,kind)

    def update(self,detections,time,shot=0):
        return self.tracker.update(detections,self.rgb,timestamp_s=time,shot_id=shot)

    def test_motion_and_short_occlusion_retain_identity(self):
        first = self.update([self.detection()],0)[0][0].track_id
        self.update([self.detection(12)],.04)
        self.assertEqual(self.update([],.08),[])
        recovered = self.update([self.detection(16)],.12)[0]
        self.assertEqual(recovered[0].track_id,first)
        self.assertTrue(recovered[1])

    def test_low_confidence_cannot_start_but_can_continue(self):
        self.assertEqual(self.update([self.detection(confidence=.2)],0),[])
        first = self.update([self.detection()],.04)[0][0].track_id
        self.assertEqual(self.update([self.detection(confidence=.2)],.08)[0][0].track_id,first)

    def test_shots_and_gaps_reset_identity(self):
        a = self.update([self.detection()],0)[0][0].track_id
        b = self.update([self.detection()],.04,1)[0][0].track_id
        c = self.update([self.detection()],1,1)[0][0].track_id
        self.assertEqual(len({a,b,c}),3)

    def test_person_and_ball_never_share_identity(self):
        a = self.update([self.detection()],0)[0][0].track_id
        b = self.update([self.detection(kind="ball")],.04)[0][0].track_id
        self.assertNotEqual(a,b)

    def test_one_detection_cannot_match_two_tracks(self):
        self.update([self.detection(10),self.detection(40)],0)
        self.assertEqual(len(self.update([self.detection(25)],.04)),1)

    def test_detection_order_does_not_swap_ids(self):
        first = self.update([self.detection(10),self.detection(120)],0)
        ids = [t.track_id for t,_ in first]
        later = self.update([self.detection(118),self.detection(12)],.04)
        self.assertEqual([t.track_id for t,_ in later],list(reversed(ids)))

    def test_lost_track_expires(self):
        first = self.update([self.detection()],0)[0][0].track_id
        for i in range(1,31):
            self.update([],i*.04)
        self.assertNotEqual(self.update([self.detection()],1.24)[0][0].track_id,first)

    def test_non_monotonic_time_fails(self):
        self.update([],1)
        with self.assertRaises(ValueError):
            self.update([],1)

    def test_ambiguous_assignment_breaks_measurement_continuity(self):
        self.update([self.detection(10),self.detection(10)],0)
        result=self.update([self.detection(10),self.detection(10)],.04)
        self.assertTrue(all(not t.continuity_safe and t.continuity_segment==1 for t,_ in result))
        self.assertTrue(all(t.association_reason=="ambiguous_assignment" for t,_ in result))

    def test_reacquisition_keeps_id_but_breaks_measurement_link(self):
        first=self.update([self.detection()],0)[0][0].track_id
        self.update([],.04);self.update([],.08);self.update([],.12)
        track,_=self.update([self.detection()],.16)[0]
        self.assertEqual(track.track_id,first)
        self.assertFalse(track.continuity_safe)
        self.assertEqual(track.association_reason,"reacquired_after_gap")

    def test_contradictory_kit_cannot_take_over_mature_track(self):
        self.rgb[:]=(220,30,30)
        for i in range(4):track,_=self.update([self.detection()],i*.04)[0]
        first=track.track_id
        self.rgb[:]=(210,210,210)
        next_track,_=self.update([self.detection()],.16)[0]
        self.assertNotEqual(next_track.track_id,first)
        self.assertFalse(next_track.continuity_safe)

    def test_automatic_keypoints_filter_confidence_and_ambiguous_labels(self):
        import numpy as np
        points = np.array([[100+i,100,.9] for i in range(32)])
        points[0,2] = .1
        landmarks = landmarks_from_keypoints(points,1280,720,PitchConfig())
        self.assertEqual(len(landmarks),27)
        self.assertNotIn("pitch-11",[p.name for p in landmarks])
        self.assertNotIn("pitch-01",[p.name for p in landmarks])
        with self.assertRaises(ValueError):
            landmarks_from_keypoints(points[:10],1280,720,PitchConfig())


@unittest.skipUnless(all(importlib.util.find_spec(p) for p in ("numpy","cv2","scipy","av")), "Install detection dependencies")
class AnalysisTests(unittest.TestCase):
    def test_real_preview_and_json_outputs_without_manual_calibration(self):
        import av
        import numpy as np
        from football_intelligence.analysis import analyze_video
        from football_intelligence.video import iter_frames
        class Detector:
            fingerprints = {"test":"synthetic"}
            def detect(self,rgb):
                return [Detection(BoundingBox(10,10,30,40),.9,"person"),
                        Detection(BoundingBox(40,30,45,35),.9,"ball")]
            def calibrate(self,*args,**kwargs):
                raise CalibrationError("No pitch in synthetic fixture")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/"source.mkv"
            with av.open(str(source),"w") as container:
                stream = container.add_stream("ffv1",rate=25)
                stream.width,stream.height,stream.pix_fmt = 64,48,"yuv420p"
                stream.time_base = stream.codec_context.time_base = Fraction(1,1000)
                for pts in [5000,5040,5140,5180]:
                    frame = av.VideoFrame.from_ndarray(np.zeros((48,64,3),dtype=np.uint8),format="rgb24")
                    frame.pts,frame.time_base = pts,Fraction(1,1000)
                    for packet in stream.encode(frame): container.mux(packet)
                for packet in stream.encode(): container.mux(packet)
            output = root/"run"
            manifest = analyze_video(source,output,match_id="test",detector=Detector(),max_frames=3)
            self.assertEqual(manifest["processed_frames"],3)
            self.assertEqual(manifest["status"],"completed")
            self.assertEqual(manifest["frames_with_pitch_fit"],0)
            self.assertEqual(manifest["classification"]["status"],"insufficient_kit_evidence")
            records = [json.loads(line) for line in (output/"tracks.jsonl").read_text().splitlines()]
            self.assertEqual([r["timestamp_s"] for r in records],[0,.04,.14])
            self.assertTrue(records[-1]["detections"][0]["confirmed"])
            self.assertFalse(records[0]["detections"][0]["measurement_link_eligible"])
            self.assertEqual(records[0]["detections"][0]["association_reason"],"new_track")
            self.assertTrue(records[-1]["detections"][0]["measurement_link_eligible"])
            self.assertEqual(records[-1]["detections"][0]["continuity_segment"],0)
            self.assertFalse(records[-1]["detections"][0]["ground_contact_reliable"])
            self.assertEqual(records[-1]["detections"][1]["projection_state"],"ball_depth_unknown")
            preview = list(iter_frames(output/"preview.mp4"))
            self.assertEqual(len(preview),3)
            self.assertAlmostEqual(preview[-1].timestamp_s,.14,places=5)
            with self.assertRaises(FileExistsError):
                analyze_video(source,output,match_id="test",detector=Detector())
            class BrokenDetector(Detector):
                def detect(self,rgb):
                    raise ValueError("simulated inference failure")
            with self.assertRaisesRegex(ValueError,"simulated inference"):
                analyze_video(source,root/"failed",match_id="test",detector=BrokenDetector())
            failed = json.loads((root/"failed/manifest.json").read_text())
            self.assertEqual(failed["status"],"failed")
            self.assertFalse((root/"failed/preview.mp4").exists())


if __name__ == "__main__":
    unittest.main()
