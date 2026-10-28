from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from football_intelligence.video import PresentationClock, VideoError


class ClockTests(unittest.TestCase):
    def test_variable_intervals_and_nonzero_origin(self):
        clock = PresentationClock()
        self.assertEqual(clock.accept(5000, Fraction(1, 1000)), (0, None))
        self.assertEqual(clock.accept(5040, Fraction(1, 1000)), (0.04, 0.04))
        self.assertEqual(clock.accept(5140, Fraction(1, 1000)), (0.14, 0.1))

    def test_missing_duplicate_and_backwards_times_fail(self):
        for pts in (None, 10, 9):
            clock = PresentationClock()
            clock.accept(10, Fraction(1, 25))
            with self.subTest(pts=pts), self.assertRaises(VideoError):
                clock.accept(pts, Fraction(1, 25))


@unittest.skipUnless(importlib.util.find_spec("av") and importlib.util.find_spec("numpy"),
                     "Install .[video] to run real decoder integration tests")
class VideoIntegrationTests(unittest.TestCase):
    def setUp(self):
        import av
        import numpy as np
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "fixture.mkv"
        # Lossless fixture with nonzero PTS, variable timing and one black→white cut.
        with av.open(str(self.source), "w") as container:
            stream = container.add_stream("ffv1", rate=25)
            stream.width, stream.height = 64, 48
            stream.pix_fmt = "yuv420p"
            stream.time_base = Fraction(1, 1000)
            stream.codec_context.time_base = Fraction(1, 1000)
            for pts, value in [(5000, 0), (5040, 0), (5140, 255), (5180, 255)]:
                frame = av.VideoFrame.from_ndarray(np.full((48, 64, 3), value, dtype=np.uint8),
                                                  format="rgb24")
                frame.pts, frame.time_base = pts, Fraction(1, 1000)
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)

    def test_probe_and_real_decoding_preserve_variable_timestamps(self):
        from football_intelligence.video import probe_video, iter_frames
        meta = probe_video(self.source)
        self.assertEqual((meta.width, meta.height), (64, 48))
        frames = list(iter_frames(self.source))
        self.assertEqual(len(frames), 4)
        self.assertEqual([frame.timestamp_s for frame in frames], [0, 0.04, 0.14, 0.18])
        self.assertEqual(frames[0].timing_record()["source_timestamp_s"], 5)
        self.assertEqual(frames[0].rgb.shape, (48, 64, 3))

    def test_ingestion_manifest_and_cut_are_consistent(self):
        from football_intelligence.ingestion import ingest_video
        output = self.root / "job"
        manifest = ingest_video(self.source, output, match_id="test-match")
        records = [json.loads(line) for line in (output / "frames.jsonl").read_text().splitlines()]
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["decoded_frames"], 4)
        self.assertEqual(manifest["shot_count"], 2)
        self.assertEqual([record["shot_id"] for record in records], [0, 0, 1, 1])
        self.assertEqual(records[2]["boundary_reasons"], ["candidate_cut"])
        self.assertEqual(len(manifest["source_sha256"]), 64)
        self.assertEqual(json.loads((output / "manifest.json").read_text()), manifest)
        self.assertFalse((output / "frames.partial.jsonl").exists())
        with self.assertRaises(FileExistsError):
            ingest_video(self.source, output, match_id="test-match")

    def test_gap_resets_segment_without_visual_change(self):
        import numpy as np
        from football_intelligence.shots import ShotConfig, ShotDetector
        from football_intelligence.video import DecodedFrame
        detector = ShotDetector(ShotConfig())
        rgb = np.zeros((48, 64, 3), dtype=np.uint8)
        detector.update(DecodedFrame(0, 0, Fraction(1, 1000), 0, None, rgb))
        result = detector.update(DecodedFrame(1, 500, Fraction(1, 1000), 0.5, 0.5, rgb))
        self.assertEqual(result["boundary_reasons"], ["timestamp_gap"])
        self.assertEqual(result["shot_id"], 1)

    def test_partial_failure_is_not_published_as_success(self):
        from football_intelligence.ingestion import ingest_video
        from football_intelligence.video import iter_frames
        def broken(*args):
            yield next(iter_frames(self.source))
            raise VideoError("simulated decoder failure")
        output = self.root / "failed-job"
        with patch("football_intelligence.ingestion.iter_frames", broken):
            with self.assertRaises(VideoError):
                ingest_video(self.source, output, match_id="test-match")
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["decoded_frames"], 1)
        self.assertIsNone(manifest["frame_records"])
        self.assertFalse((output / "frames.jsonl").exists())

    def test_bad_inputs_fail(self):
        from football_intelligence.video import probe_video
        with self.assertRaises(VideoError):
            probe_video(self.source, 1)
        with self.assertRaises(FileNotFoundError):
            probe_video(self.root / "missing.mp4")
        path = self.root / "invalid.mp4"
        path.write_text("not a video")
        with self.assertRaises(VideoError):
            probe_video(path)


if __name__ == "__main__":
    unittest.main()
