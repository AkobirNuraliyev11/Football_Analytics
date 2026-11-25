import unittest
import json
import tempfile
from pathlib import Path
import importlib.util
from football_intelligence.calibration import CalibrationError, transform
from football_intelligence.measurement_quality import refine_midfield, stabilize_camera, foot_candidate, PaintFit
from football_intelligence.telemetry import TelemetryEngine
from test_telemetry import frame


@unittest.skipUnless(all(importlib.util.find_spec(p) for p in ("numpy","cv2","scipy","av")),
                     "Install detection dependencies for real-measurement tests")
class MeasurementQualityTests(unittest.TestCase):
    def setUp(self):
        global np, cv2
        import numpy as np
        import cv2

    def field(self):
        # Known synthetic projective mapping, with a circle, halfway line, and near sideline.
        matrix=np.array([[.16386559,.60986204,-151.11764],[-.03472723,1.22061325,-364.16006],
                         [-.00024113,.01098562,1.]])
        rgb=np.full((1080,1920,3),[60,115,45],dtype=np.uint8)
        inverse=np.linalg.inv(matrix)
        angles=np.linspace(0,2*np.pi,400)
        circle=np.c_[52.5+9.15*np.cos(angles),34+9.15*np.sin(angles)]
        for coordinates in [circle,[[52.5,0],[52.5,68]],[[20,68],[85,68]]]:
            pixels=transform(inverse,coordinates).astype(np.int32)
            cv2.polylines(rgb,[pixels],len(coordinates)>2,(220,225,210),3)
        return rgb,matrix

    def test_paint_fit_recovers_known_geometry(self):
        rgb,true=self.field()
        seed=true@np.array([[1,0,3],[0,1,1],[0,0,1]])
        fit=refine_midfield(rgb,seed,[])
        probes=transform(np.linalg.inv(true),[[52.5,25],[48,35],[55,39]])
        error=np.linalg.norm(transform(fit.matrix,probes)-transform(true,probes),axis=1)
        self.assertLess(error.max(),.25)
        self.assertLess(fit.evidence["paint_p90_after_m"],fit.evidence["paint_p90_before_m"])

    def test_absent_paint_is_rejected(self):
        rgb,matrix=self.field()
        rgb[:]=[60,115,45]
        with self.assertRaises(CalibrationError):refine_midfield(rgb,matrix,[])

    def test_pale_turf_is_not_used_as_paint(self):
        from football_intelligence.pitch_paint import paint_mask
        rgb,matrix=self.field()
        rgb[:]=[130,150,120]  # Passed the old color-only white threshold.
        self.assertFalse(paint_mask(rgb).any())
        with self.assertRaisesRegex(CalibrationError,'Insufficient visible paint'):
            refine_midfield(rgb,matrix,[])

    def test_camera_translation_does_not_become_player_motion(self):
        rgb,matrix=self.field()
        first=refine_midfield(rgb,matrix,[])
        camera=np.array([[1.,0,2],[0,1.,1],[0,0,1.]])
        moved=cv2.warpPerspective(rgb,camera,(1920,1080),borderValue=(60,115,45))
        second=refine_midfield(moved,matrix@np.linalg.inv(camera),[])
        stable=stabilize_camera(rgb,moved,first,second,[],[])
        pixel=transform(np.linalg.inv(first.matrix),[[51,32]])
        motion=transform(camera,pixel)
        self.assertLess(np.linalg.norm(transform(stable.matrix,motion)-[[51,32]]),.1)
        self.assertTrue(stable.evidence["camera_stable"])

    def test_current_paint_transport_survives_missing_touchline_but_not_missing_circle(self):
        from football_intelligence.measurement_quality import transport_midfield
        rgb,matrix=self.field();first=refine_midfield(rgb,matrix,[])
        camera=np.array([[1.,0.,2.],[0.,1.,1.],[0.,0.,1.]])
        current=cv2.warpPerspective(rgb,camera,(rgb.shape[1],rgb.shape[0]),borderValue=(60,115,45))
        expected=matrix@np.linalg.inv(camera)
        ys,xs=np.indices(current.shape[:2]);points=np.c_[xs.ravel(),ys.ravel()]
        field_y=transform(expected,points)[:,1].reshape(ys.shape)
        current[field_y>65]=[60,115,45]
        with self.assertRaises(CalibrationError):refine_midfield(current,expected,[])
        fit=transport_midfield(rgb,current,first,[],[])
        self.assertTrue(fit.evidence['camera_stable'])
        self.assertEqual(fit.evidence['method'],'current_paint_checked_camera_transport')
        pixels=transform(np.linalg.inv(expected),[[51,32],[55,35]])
        self.assertLess(np.linalg.norm(transform(fit.matrix,pixels)-[[51,32],[55,35]],axis=1).max(),.15)
        current[:]=[60,115,45]
        with self.assertRaises(CalibrationError):transport_midfield(rgb,current,first,[],[])

    def test_failed_camera_check_retains_only_current_refit_as_unstable_seed(self):
        from unittest.mock import patch
        from football_intelligence.real_measurements import stabilize_checked_refit
        previous=PaintFit(np.eye(3),{'camera_stable':True})
        matrix=np.array([[1,0,2],[0,1,0],[0,0,1]])
        current=PaintFit(matrix,{'status':'line_checked_estimate'})
        with patch('football_intelligence.real_measurements.stabilize_camera',side_effect=CalibrationError('flow rejected')):
            with self.assertRaises(CalibrationError):stabilize_checked_refit(None,None,previous,current,[],[],None)
            result=stabilize_checked_refit(None,None,previous,current,[],[],None,retain=True)
        np.testing.assert_array_equal(result.matrix,matrix)
        self.assertFalse(result.evidence['camera_stable'])
        self.assertTrue(result.evidence['camera_reference_reset'])
        self.assertTrue(previous.evidence['camera_stable'])
        with patch('football_intelligence.real_measurements.stabilize_camera',return_value=previous) as check:
            self.assertIs(stabilize_checked_refit(None,None,result,previous,[],[],None,retain=True),previous)
            self.assertIs(check.call_args.args[2],result)

    def test_foot_evidence_requires_visibility_and_never_claims_ground_contact(self):
        rgb=np.full((300,300,3),[60,115,45],dtype=np.uint8)
        fit=PaintFit(np.array([[.1,0,37.5],[0,.1,14],[0,0,1]]),{})
        item={"track_id":1,"kind":"person","bbox":{"x_min":140,"y_min":130,"x_max":160,"y_max":200}}
        candidate,reason=foot_candidate(rgb,item,[dict(item)],fit)
        self.assertIsNone(reason)
        self.assertFalse(candidate["ground_contact_verified"])
        other=item|{"track_id":2}
        self.assertEqual(foot_candidate(rgb,item,[item,other],fit)[1],"feet_occluded")
        rgb[:]=0
        self.assertEqual(foot_candidate(rgb,item,[item],fit)[1],"no_visible_ground")

    def test_experimental_evidence_cannot_enable_strict_measurements(self):
        strict,experimental=TelemetryEngine(),TelemetryEngine(experimental=True)
        for i in range(31):
            f=frame(i/10,ground_contact_reliable=False,projection_state="ground_contact_unverified")
            f["calibration_status"]="fit_unvalidated"
            f["detections"][0]["measurement_evidence"]={"status":"line_checked_estimate",
                "ground_evidence":"visible_feet_candidate","camera_stable":True}
            strict.update(f); experimental.update(f)
        self.assertEqual(strict.finish()["status"],"unavailable")
        summary=experimental.finish()
        self.assertEqual(summary["status"],"estimates_available")
        self.assertEqual(summary["measurement_quality"],"experimental_estimate")

    def test_missing_camera_evidence_blocks_experimental_results(self):
        engine=TelemetryEngine(experimental=True)
        f=frame(0)
        f["detections"][0]["measurement_evidence"]={"status":"line_checked_estimate","ground_evidence":"visible_feet_candidate"}
        result=engine.update(f)["observations"][0]
        self.assertIn("camera_stability_unverified",result["reasons"])
        self.assertIsNone(result["speed_kmh"])

    def test_real_review_exports_rejections_and_checks_source(self):
        import av
        from football_intelligence.model_assets import sha256
        from football_intelligence.real_measurements import estimate_video
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);analysis=root/"analysis";analysis.mkdir();source=root/"source.mkv"
            with av.open(str(source),"w") as container:
                stream=container.add_stream("ffv1",rate=25)
                stream.width,stream.height,stream.pix_fmt=64,48,"yuv420p"
                for i in range(2):
                    image=av.VideoFrame.from_ndarray(np.zeros((48,64,3),dtype=np.uint8),format="rgb24")
                    for packet in stream.encode(image):container.mux(packet)
                for packet in stream.encode():container.mux(packet)
            manifest={"status":"completed","source_sha256":sha256(source),"pitch":{"length_m":105,"width_m":68},"processed_frames":2}
            (analysis/"manifest.json").write_text(json.dumps(manifest))
            (analysis/"calibrations.jsonl").write_text("")
            records=[]
            for i in range(2):
                f=frame(i/25);f["frame_index"]=i
                f["detections"][0]["bbox"]={"x_min":10,"y_min":10,"x_max":30,"y_max":40}
                records.append(f)
            (analysis/"tracks.jsonl").write_text("\n".join(map(json.dumps,records))+"\n")
            result=estimate_video(source,analysis,root/"review",write_preview=False)
            self.assertFalse(list((root/"review").glob("*.mp4")))
            self.assertNotIn("preview.mp4",result["artifacts"])
            self.assertEqual(result["status"],"completed")
            summary=json.loads((root/"review/summary.json").read_text())
            self.assertEqual(summary["status"],"unavailable")
            self.assertFalse(result["ground_contact_verified"])
            manifest["source_sha256"]="wrong"
            (analysis/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"exact source"):estimate_video(source,analysis,root/"bad")
            self.assertFalse((root/"bad").exists())


if __name__=="__main__":unittest.main()
