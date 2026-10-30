import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from football_intelligence.feet import FootLocalizer,visible_shoe,AnkleDetector,download_pose_model
from football_intelligence.measurement_quality import PaintFit


@unittest.skipUnless(all(importlib.util.find_spec(p) for p in ("numpy","cv2")),"Install calibration dependencies")
class FeetTests(unittest.TestCase):
    def fixture(self,dy=0):
        import numpy as np
        rgb=np.full((240,240,3),[60,130,45],dtype=np.uint8)
        points=np.zeros((17,3));points[:,2]=.95
        points[11,:2]=[96,125+dy];points[12,:2]=[104,125+dy]
        points[13,:2]=[95,155+dy];points[14,:2]=[105,155+dy]
        points[15,:2]=[94,180+dy];points[16,:2]=[106,180+dy]
        for x in [94,106]:rgb[178+dy:185+dy,x-3:x+4]=[220,220,220]
        item={"track_id":1,"kind":"person","continuity_segment":0,
              "bbox":{"x_min":80,"y_min":80+dy,"x_max":120,"y_max":185+dy}}
        return rgb,[item],{1:{"status":"localized","keypoints":points.tolist()}}

    def test_shoe_is_localized_without_claiming_ground_contact(self):
        rgb,items,poses=self.fixture()
        out=FootLocalizer().update(rgb,items,poses,timestamp_s=0,shot_id=0)[1]
        self.assertEqual(out["status"],"shoe_candidate")
        self.assertEqual(out["anchor_px"][1],184)
        self.assertFalse(out["ground_contact_verified"])

    def test_missing_ankle_is_not_replaced_with_box_anchor(self):
        rgb,items,poses=self.fixture()
        poses[1]["keypoints"][15][2]=.1
        out=FootLocalizer().update(rgb,items,poses,timestamp_s=0,shot_id=0)[1]
        self.assertEqual(out["status"],"legs_not_visible")
        self.assertNotIn("anchor_px",out)

    def test_pitch_line_merged_with_shoe_is_rejected(self):
        rgb,items,poses=self.fixture()
        rgb[181:185,:]=[220,220,220]
        self.assertIsNone(visible_shoe(rgb,[94,180],105))

    def test_no_shoe_in_grass_is_not_invented(self):
        rgb,_,_=self.fixture();rgb[:]=[60,130,45]
        self.assertIsNone(visible_shoe(rgb,[94,180],105))

    def test_camera_compensated_vertical_motion_veto_and_cooldown(self):
        import numpy as np
        local=FootLocalizer();fit=PaintFit(np.eye(3),{})
        rgb,items,poses=self.fixture()
        local.update(rgb,items,poses,timestamp_s=0,shot_id=0,fit=fit)
        rgb,items,poses=self.fixture(-10)
        out=local.update(rgb,items,poses,timestamp_s=.04,shot_id=0,fit=fit)[1]
        self.assertEqual(out["status"],"vertical_motion_cooldown")
        self.assertEqual(out["motion_warning"],"possible_airborne_or_vertical_motion")
        # A missing pose during the cooldown cannot erase the veto.
        local.update(rgb,items,{},timestamp_s=.08,shot_id=0,fit=fit)
        out=local.update(rgb,items,poses,timestamp_s=.12,shot_id=0,fit=fit)[1]
        self.assertEqual(out["status"],"vertical_motion_cooldown")
        out=local.update(rgb,items,poses,timestamp_s=.16,shot_id=1,fit=fit)[1]
        self.assertEqual(out["status"],"shoe_candidate")

    def test_camera_translation_is_not_a_jump(self):
        import numpy as np
        local=FootLocalizer()
        rgb,items,poses=self.fixture()
        local.update(rgb,items,poses,timestamp_s=0,shot_id=0,fit=PaintFit(np.eye(3),{}))
        rgb,items,poses=self.fixture(-10)
        matrix=np.array([[1,0,0],[0,1,10],[0,0,1]])
        out=local.update(rgb,items,poses,timestamp_s=.04,shot_id=0,fit=PaintFit(matrix,{}))[1]
        self.assertEqual(out["status"],"shoe_candidate")

    def test_wrong_pose_shape_and_nonfinite_points_fail_closed(self):
        for bad in [[],[[float('nan'),0,.9]]*17]:
            rgb,items,_=self.fixture()
            out=FootLocalizer().update(rgb,items,{1:{"status":"localized","keypoints":bad}},timestamp_s=0,shot_id=0)[1]
            self.assertEqual(out["status"],"invalid_pose")

    def test_model_hash_is_checked_before_loading(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"yolo11n-pose.pt";path.write_bytes(b"not a model")
            with self.assertRaisesRegex(ValueError,"hash"):AnkleDetector(path)
            with self.assertRaisesRegex(ValueError,"hash"):download_pose_model(Path(folder))

    def test_optional_proxy_requires_recent_observed_shoes_and_expires(self):
        local=FootLocalizer(allow_ankle_proxy=True)
        rgb,items,poses=self.fixture()
        for i in range(3):local.update(rgb,items,poses,timestamp_s=i*.04,shot_id=0)
        rgb[:]=[60,130,45]
        out=local.update(rgb,items,poses,timestamp_s=.12,shot_id=0)[1]
        self.assertEqual(out["anchor_method"],"current_ankle_recent_shoe_offset")
        self.assertFalse(out["ground_contact_verified"])
        for i in range(4,17):out=local.update(rgb,items,poses,timestamp_s=i*.04,shot_id=0)[1]
        self.assertEqual(out["status"],"shoe_not_separable")

    def test_proxy_cannot_cross_identity_segment_or_low_confidence_ankles(self):
        for change in ["segment","confidence"]:
            local=FootLocalizer(allow_ankle_proxy=True)
            rgb,items,poses=self.fixture()
            for i in range(3):local.update(rgb,items,poses,timestamp_s=i*.04,shot_id=0)
            rgb[:]=[60,130,45]
            if change=="segment":items[0]["continuity_segment"]=1
            else:poses[1]["keypoints"][15][2]=.6
            out=local.update(rgb,items,poses,timestamp_s=.12,shot_id=0)[1]
            self.assertEqual(out["status"],"shoe_not_separable")

    @unittest.skipUnless(importlib.util.find_spec("av"),"Install video dependencies")
    def test_review_publishes_comparison_without_inventing_missing_pose(self):
        import av
        import numpy as np
        from football_intelligence.config import AppConfig
        from football_intelligence.model_assets import sha256
        from football_intelligence.foot_review import review_feet
        class MissingPose:
            fingerprint="synthetic-missing-pose"
            def predict(self,rgb,items):return {}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);geometry=root/"geometry";geometry.mkdir();source=root/"source.mkv"
            with av.open(str(source),"w") as container:
                stream=container.add_stream("ffv1",rate=25);stream.width,stream.height,stream.pix_fmt=64,48,"yuv420p"
                for i in range(3):
                    image=av.VideoFrame.from_ndarray(np.zeros((48,64,3),dtype=np.uint8),format="rgb24")
                    for packet in stream.encode(image):container.mux(packet)
                for packet in stream.encode():container.mux(packet)
            records=[{"frame_index":i,"timestamp_s":i/25,"match_id":"fixture","shot_id":0,
                      "detections":[{"track_id":1,"kind":"person","role":"outfield","team":"A",
                                     "bbox":{"x_min":10,"y_min":5,"x_max":30,"y_max":40}}]} for i in range(3)]
            tracks=root/"tracks.jsonl";tracks.write_text("\n".join(map(json.dumps,records))+"\n")
            quality=[r|{"matrix":None,"geometry":None} for r in records]
            (geometry/"quality.jsonl").write_text("\n".join(map(json.dumps,quality))+"\n")
            (geometry/"manifest.json").write_text(json.dumps({"status":"completed","source_sha256":sha256(source),
                "tracks_sha256":sha256(tracks),"config":AppConfig().to_dict(),"processed_frames":3}))
            output=root/"result"
            result=review_feet(source,geometry,tracks,output,pose_model=None,detector=MissingPose())
            self.assertEqual(result["processed_frames"],3)
            comparison=json.loads((output/"comparison.json").read_text())
            self.assertEqual(comparison["pose"]["measured_observations"],0)
            self.assertEqual(comparison["foot_status_counts"],{"pose_unavailable":3})
            with self.assertRaisesRegex(ValueError,"No frames"):
                review_feet(source,geometry,tracks,root/"empty",pose_model=None,detector=MissingPose(),start_s=1)
            self.assertEqual(json.loads((root/"empty/manifest.json").read_text())["status"],"failed")
            self.assertFalse((root/"empty/comparison.json").exists())


if __name__=="__main__":unittest.main()
