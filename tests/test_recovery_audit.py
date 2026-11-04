import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.restore_samples import restore
from scripts.audit_continuity import audit_frames
from test_tactical import frame


class RecoveryTests(unittest.TestCase):
    def test_download_verify_cache_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            payload=b"sample fixture"
            sample={"test":{"path":"data/test.mp4","drive_id":"test","sha256":hashlib.sha256(payload).hexdigest()}}
            def downloader(**kwargs):
                Path(kwargs["output"]).write_bytes(payload)
                return kwargs["output"]
            with patch("scripts.restore_samples.SAMPLES",sample):
                restore(root,downloader)
                self.assertEqual((root/"data/test.mp4").read_bytes(),payload)
                restore(root,lambda **kwargs:self.fail("Should reuse verified file"))
                (root/"data/test.mp4").write_bytes(b"different")
                with self.assertRaises(ValueError):restore(root,downloader)

    def test_bad_download_never_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def downloader(**kwargs):
                Path(kwargs["output"]).write_bytes(b"wrong")
                return kwargs["output"]
            with patch("scripts.restore_samples.SAMPLES",{"test":{"path":"data/test.mp4","drive_id":"test","sha256":"wrong"}}):
                with self.assertRaises(ValueError):restore(root,downloader)
            self.assertFalse((root/"data/test.mp4").exists())

    def test_audit_counts_missing_and_rejections(self):
        frames=[]
        for i in range(80):
            f=frame(i,i*.04)
            f["detections"][0]["measurement_evidence"]={"status":"line_checked_estimate",
                "ground_evidence":"visible_feet_candidate","camera_stable":True}
            if i==60: f["detections"]=[]
            if i==70: f["detections"][0]["continuity_safe"]=False
            frames.append(f)
        result=audit_frames(frames)
        self.assertEqual(result["counts"]["person_observations"],79)
        self.assertEqual(result["runs_at_least_seconds"]["2"],1)
        self.assertEqual(result["run_end_reasons"]["missing_observation"],1)
        self.assertEqual(result["run_end_reasons"]["uncertain_association"],1)
        self.assertEqual(len(result["mature_fragments"]),1)
