import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.evaluate_trajectories import evaluate


class ReferenceEvaluationTests(unittest.TestCase):
    def test_known_errors_and_missing_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"radar.jsonl"
            frames=[];samples=[]
            for i in range(3):
                sample={"match_id":"synthetic","shot_id":0,"frame_index":i,"track_id":1,
                        "coordinate_reference_id":"exact","timestamp_s":i*.1,
                        "x_m":i,"y_m":0,"uncertainty_m":0}
                samples.append(sample)
                point={"track_id":1,"fragment_id":1,"coordinate_reference_id":"exact","x_m":i+3,"y_m":4}
                frames.append({"match_id":"synthetic","shot_id":0,"frame_index":i,"timestamp_s":i*.1,
                               "positions":[point] if i<2 else []})
            path.write_text("".join(json.dumps(f)+"\n" for f in frames))
            labels={"predictions_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                    "independent_reference":True,"reference_method":"Analytic fixture only; not real video", "samples":samples}
            result=evaluate(path,labels)
            self.assertEqual(result["position_mae_m"],5)
            self.assertEqual(result["availability"],2/3)
            self.assertEqual(result["paired_interval_count"],1)
            self.assertAlmostEqual(result["interval_speed_mae_kmh"],0)
            labels["samples"][0]["coordinate_reference_id"]="wrong"
            with self.assertRaises(ValueError): evaluate(path,labels)

    def test_provenance_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"radar.jsonl";path.write_text("")
            with self.assertRaises(ValueError): evaluate(path,{"predictions_sha256":"wrong"})
            labels={"predictions_sha256":hashlib.sha256(b"").hexdigest(),"independent_reference":False}
            with self.assertRaises(ValueError): evaluate(path,labels)
