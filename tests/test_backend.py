import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

from football_intelligence.jobs import JobStore, run_one


class QueueTests(unittest.TestCase):
    def test_durable_claim_restart_and_single_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(tmp)
            first, second = str(uuid.uuid4()), str(uuid.uuid4())
            store.enqueue(first, 'a', None)
            store.enqueue(second, 'b', 5)
            with store.worker_lock():
                self.assertEqual(store.claim()['id'], first)
                with self.assertRaises(RuntimeError):
                    with JobStore(tmp).worker_lock():
                        pass
                self.assertEqual(store.get(first)['status'], 'running')
            restored = JobStore(tmp)
            with restored.worker_lock():
                self.assertEqual(restored.get(first)['status'], 'failed')
                self.assertIn('interrupted', restored.get(first)['error'])
                self.assertEqual(restored.claim()['id'], second)
                self.assertIsNone(restored.claim())

    def test_claim_is_atomic_between_connections(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(tmp)
            store.enqueue(str(uuid.uuid4()), 'hash', None)
            claims = []
            def claim():
                claims.append(JobStore(tmp).claim())
            threads = [threading.Thread(target=claim) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertEqual(sum(job is not None for job in claims), 1)


@unittest.skipUnless(all(importlib.util.find_spec(m) for m in
    ('fastapi', 'httpx', 'av', 'numpy', 'cv2')), 'Requires backend/video/calibration extras')
class BackendTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from football_intelligence.api import create_app
        from test_highlights import HighlightExtractionTests
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, _ = HighlightExtractionTests().setup_source(self.root, count=5)
        self.app = create_app(self.root / 'backend', token='test-only',
                              allowed_origins=['http://localhost:5173'])
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.headers = {'Authorization': 'Bearer test-only', 'Content-Type': 'application/octet-stream'}
        self.store = self.app.state.store

    def submit(self, **kwargs):
        response = self.client.post('/jobs', headers=self.headers,
                                    content=self.source.read_bytes(), **kwargs)
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()['id']

    def run_pipeline(self, identity, *, fail=False):
        from football_intelligence.analysis import analyze_video
        from football_intelligence.calibration import CalibrationError
        store = self.store
        class EmptyDetector:
            fingerprints = {'test': 'synthetic-empty-detector'}
            def calibrate(self, *args, **kwargs):
                raise CalibrationError('Synthetic footage has no validated pitch')
            def detect(self, rgb):
                if fail:
                    raise ValueError('deliberate detector failure')
                return []
        progress = []
        def pipeline(*args, **kwargs):
            callback = kwargs.pop('progress_callback')
            def record(count, timestamp):
                callback(count, timestamp)
                progress.append(store.get(identity)['processed_frames'])
            return analyze_video(*args, **kwargs, detector=EmptyDetector(), progress_callback=record)
        with store.worker_lock():
            self.assertTrue(run_one(store, pipeline=pipeline))
            self.assertFalse(run_one(store, pipeline=pipeline))
        return progress

    def test_upload_real_pipeline_progress_results_range_and_quality(self):
        identity = self.submit(params={'max_frames': 3})
        status = self.client.get(f'/jobs/{identity}', headers=self.headers).json()
        self.assertEqual(status['status'], 'queued')
        self.assertEqual(self.client.get(f'/jobs/{identity}/results', headers=self.headers).status_code, 409)
        self.assertEqual(self.run_pipeline(identity), [1, 2, 3])
        result = self.client.get(f'/jobs/{identity}/results', headers=self.headers).json()
        self.assertFalse(result['metric_measurements_available'])
        self.assertFalse(result['preview_generated'])
        self.assertEqual(result['events_status'], 'unavailable')
        self.assertEqual(result['candidate_events'], 0)
        artifact = f'/jobs/{identity}/artifacts/telemetry.jsonl'
        response = self.client.get(artifact, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.text.splitlines()), 3)
        ranged = self.client.get(artifact, headers=self.headers | {'Range': 'bytes=0-19'})
        self.assertEqual(ranged.status_code, 206)
        self.assertEqual(ranged.content, response.content[:20])
        self.assertTrue(ranged.headers['content-range'].startswith('bytes 0-19/'))
        self.assertEqual(self.client.get(artifact, headers=self.headers | {'Range': 'bytes=999999999-'}).status_code, 416)
        self.assertEqual(self.client.get(artifact, headers=self.headers | {'Range': 'bytes=0-1,3-4'}).status_code, 400)
        for name in ('source.video', 'preview.mp4', 'tracks.partial.jsonl', 'jobs.sqlite3'):
            self.assertEqual(self.client.get(f'/jobs/{identity}/artifacts/{name}', headers=self.headers).status_code, 404)
        self.assertFalse(list(self.store.directory(identity).rglob('*.mp4')))
        # File symlinks must not expose anything outside the completed output.
        path = self.store.directory(identity) / 'analysis' / 'telemetry.jsonl'
        path.unlink(); path.symlink_to(self.source)
        self.assertEqual(self.client.get(artifact, headers=self.headers).status_code, 404)

    def test_auth_invalid_upload_limits_and_cors(self):
        self.assertEqual(self.client.post('/jobs', content=b'bad').status_code, 401)
        self.assertEqual(self.client.post('/jobs', headers=self.headers, content=b'bad').status_code, 422)
        self.assertEqual(self.client.post('/jobs', headers=self.headers, content=b'').status_code, 422)
        self.assertEqual(list((self.store.root / 'jobs').iterdir()), [])
        self.assertEqual(self.client.post('/jobs?max_frames=0', headers=self.headers, content=b'bad').status_code, 422)
        self.assertEqual(self.client.post('/jobs', headers=self.headers | {'Content-Type': 'multipart/form-data'}, content=b'bad').status_code, 415)
        from fastapi.testclient import TestClient
        from football_intelligence.api import create_app
        with TestClient(create_app(self.root / 'limited', token='test-only', max_upload_bytes=10)) as client:
            self.assertEqual(client.post('/jobs', headers=self.headers, content=b'x'*11).status_code, 413)
            self.assertEqual(client.post('/jobs', headers=self.headers, content=iter([b'x'*6, b'x'*6])).status_code, 413)
        self.assertEqual(list((self.root / 'limited' / 'jobs').iterdir()), [])
        for origin, expected in [('http://localhost:5173', 200), ('https://untrusted.example', 400)]:
            response = self.client.options('/jobs', headers={'Origin': origin,
                'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'Authorization'})
            self.assertEqual(response.status_code, expected)
        self.assertEqual(self.client.get('/jobs/not-a-uuid', headers=self.headers).status_code, 404)

    def test_failed_worker_does_not_publish_partial_artifacts(self):
        identity = self.submit()
        self.run_pipeline(identity, fail=True)
        status = self.client.get(f'/jobs/{identity}', headers=self.headers).json()
        self.assertEqual(status['status'], 'failed')
        self.assertIn('deliberate detector failure', status['error'])
        self.assertEqual(self.client.get(f'/jobs/{identity}/artifacts/manifest.json', headers=self.headers).status_code, 409)
        self.assertEqual(self.client.get(f'/jobs/{identity}/results', headers=self.headers).status_code, 409)

    def test_changed_source_fails_before_inference(self):
        identity = self.submit()
        (self.store.directory(identity) / 'source.video').write_bytes(b'changed')
        with self.store.worker_lock(), patch('football_intelligence.analysis.analyze_video') as inference:
            run_one(self.store)
            inference.assert_not_called()
        self.assertEqual(self.store.get(identity)['status'], 'failed')
        self.assertIn('source changed', self.store.get(identity)['error'])
