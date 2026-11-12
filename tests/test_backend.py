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

    def test_status_probe_does_not_recover_or_change_active_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=JobStore(tmp)
            identity=str(uuid.uuid4());store.enqueue(identity,'hash',None)
            self.assertFalse(store.system_status()['worker_connected'])
            with store.worker_lock():
                store.claim()
                self.assertTrue(JobStore(tmp).system_status()['worker_connected'])
                self.assertEqual(store.get(identity)['status'],'running')
            self.assertFalse(store.system_status()['worker_connected'])
            self.assertEqual(store.get(identity)['status'],'running')

    def test_queue_capacity_is_atomic(self):
        from football_intelligence.jobs import QueueFull
        with tempfile.TemporaryDirectory() as tmp:
            store=JobStore(tmp);results=[]
            def enqueue():
                try:
                    store.enqueue(str(uuid.uuid4()),'hash',None,max_active=1)
                    results.append('queued')
                except QueueFull:results.append('full')
            threads=[threading.Thread(target=enqueue) for _ in range(2)]
            for t in threads:t.start()
            for t in threads:t.join()
            self.assertCountEqual(results,['queued','full'])

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
        with patch('football_intelligence.analysis.PreviewWriter', side_effect=AssertionError('Media must be opt-in')):
            self.assertEqual(self.run_pipeline(identity), [1, 2, 3])
        result = self.client.get(f'/jobs/{identity}/results', headers=self.headers).json()
        self.assertEqual(result['detection_quality']['ball_frames']['missing'],3)
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

    def test_system_status_requires_auth_and_reports_worker(self):
        self.assertEqual(self.client.get('/system').status_code,401)
        response=self.client.get('/system',headers=self.headers)
        self.assertEqual(response.json()['status'],'worker_offline')
        with self.store.worker_lock():
            state=self.client.get('/system',headers=self.headers).json()
            self.assertEqual(state['status'],'ready')
            self.assertFalse(state['metric_accuracy_validated'])
            self.assertEqual(state['limits']['max_active_jobs'],10)

    def test_capacity_disk_and_pixel_limits_leave_no_partial_upload(self):
        from fastapi.testclient import TestClient
        from football_intelligence.api import create_app
        from types import SimpleNamespace
        with TestClient(create_app(self.root/'capacity',token='test-only',max_active_jobs=1)) as client:
            response=client.post('/jobs',headers=self.headers,content=self.source.read_bytes())
            self.assertEqual(response.status_code,202)
            identity=response.json()['id']
            self.assertEqual(client.post('/jobs',headers=self.headers,content=b'bad').status_code,429)
            client.post(f'/jobs/{identity}/cancel',headers=self.headers)
            self.assertEqual(client.post(f'/jobs/{identity}/retry',headers=self.headers).status_code,202)
            self.assertEqual(client.post(f'/jobs/{identity}/retry',headers=self.headers).status_code,429)
        with patch('football_intelligence.api.shutil.disk_usage',return_value=SimpleNamespace(free=1)):
            self.assertEqual(self.client.post('/jobs',headers=self.headers,content=b'x').status_code,507)
        self.assertEqual(list((self.store.root/'jobs').iterdir()),[])
        with TestClient(create_app(self.root/'pixels',token='test-only',max_video_pixels=1)) as client:
            self.assertEqual(client.post('/jobs',headers=self.headers,content=self.source.read_bytes()).status_code,422)
        self.assertEqual(list((self.root/'pixels/jobs').iterdir()),[])

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

    def test_paginated_frames_filtering_empty_results_and_job_list(self):
        identity = self.submit()
        self.run_pipeline(identity)
        url = f'/jobs/{identity}'
        page = self.client.get(url+'/frames/tracks?limit=2', headers=self.headers).json()
        self.assertEqual([r['frame_index'] for r in page['items']], [0, 1])
        self.assertEqual(page['next_offset'], 2)
        next_page = self.client.get(url+'/frames/tracks?limit=2&offset=2', headers=self.headers).json()
        self.assertEqual([r['frame_index'] for r in next_page['items']], [2, 3])
        last = self.client.get(url+'/frames/telemetry?limit=2&offset=4', headers=self.headers).json()
        self.assertEqual(len(last['items']), 1)
        self.assertIsNone(last['next_offset'])
        filtered = self.client.get(url+'/frames/radar?start_s=0.2&end_s=0.5', headers=self.headers).json()
        self.assertEqual([r['frame_index'] for r in filtered['items']], [2, 3])
        for endpoint in ('telemetry', 'events', 'heatmaps'):
            response = self.client.get(url+'/'+endpoint, headers=self.headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['items'], [])
        self.assertEqual(self.client.get(url+'/events', headers=self.headers).json()['status'], 'unavailable')
        placeholder = self.client.get(url+'/heatmaps', headers=self.headers).json()['placeholder_file']
        self.assertEqual(self.client.get(url+'/artifacts/'+placeholder, headers=self.headers).status_code, 200)
        for path in ('frames/tracks?limit=501', 'frames/tracks?start_s=nan',
                     'frames/tracks?end_s=0&start_s=1', 'telemetry?sort=DROP_TABLE', 'telemetry?offset=-1'):
            self.assertEqual(self.client.get(url+'/'+path, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.get(url+'/telemetry').status_code, 401)
        other = self.submit()
        jobs = self.client.get('/jobs?limit=1', headers=self.headers).json()
        self.assertEqual(jobs['items'][0]['id'], other)
        self.assertEqual(jobs['next_offset'], 1)

    def test_cancel_waiting_and_retry_preserves_original(self):
        identity = self.submit(params={'max_frames': 2, 'render_media': 'true'})
        self.assertEqual(self.client.post(f'/jobs/{identity}/retry', headers=self.headers).status_code, 409)
        response = self.client.post(f'/jobs/{identity}/cancel', headers=self.headers)
        self.assertEqual(response.json()['status'], 'cancelled')
        with self.store.worker_lock():
            self.assertFalse(run_one(self.store))
        response = self.client.post(f'/jobs/{identity}/retry', headers=self.headers)
        self.assertEqual(response.status_code, 202)
        new = response.json()
        self.assertNotEqual(new['id'], identity)
        self.assertEqual(new['parent_id'], identity)
        self.assertEqual(new['max_frames'], 2)
        self.assertTrue(new['render_media'])
        self.assertEqual(self.store.get(identity)['status'], 'cancelled')
        self.assertEqual((self.store.directory(new['id'])/'source.video').read_bytes(), self.source.read_bytes())
        (self.store.directory(identity)/'source.video').write_bytes(b'tampered')
        directories = set((self.store.root/'jobs').iterdir())
        self.assertEqual(self.client.post(f'/jobs/{identity}/retry', headers=self.headers).status_code, 409)
        self.assertEqual(set((self.store.root/'jobs').iterdir()), directories)

    def test_cancel_running_stops_pipeline_and_hides_artifacts(self):
        identity = self.submit()
        original = self.store.progress
        def progress(job, count, timestamp):
            if count == 2:
                response = self.client.post(f'/jobs/{identity}/cancel', headers=self.headers)
                self.assertEqual(response.json()['status'], 'cancel_requested')
            original(job, count, timestamp)
        with patch.object(self.store, 'progress', side_effect=progress):
            observed = self.run_pipeline(identity)
        self.assertEqual(observed, [1])
        job = self.store.get(identity)
        self.assertEqual(job['status'], 'cancelled')
        self.assertIsNone(job['result'])
        self.assertEqual(self.client.get(f'/jobs/{identity}/frames/tracks', headers=self.headers).status_code, 409)

    def test_opt_in_media_heatmaps_events_and_fragment_sorting(self):
        from test_highlights import HighlightExtractionTests, analysis_fixture
        from football_intelligence.telemetry import TelemetryEngine
        from football_intelligence.analysis import PreviewWriter
        from football_intelligence.video import iter_frames
        from contextlib import closing
        from fractions import Fraction
        self.source, times = HighlightExtractionTests().setup_source(self.root, count=23)
        identity = self.submit(params={'render_media': 'true'})
        def synthetic_pipeline(source, output, **options):
            analysis_fixture(output.parent, source, times)
            path = output/'tracks.jsonl'
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            import copy
            for row in rows:
                row['match_id'] = options['match_id']
                second = copy.deepcopy(row['detections'][0])
                second.update(track_id=2, team='B')
                second['pitch_position_candidate'] = {'x_m': 10+3*row['timestamp_s'], 'y_m': 40}
                row['detections'].append(second)
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            engine = TelemetryEngine()
            measurements = [engine.update(r) for r in rows]
            summary = engine.finish()
            (output/'telemetry.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in measurements))
            (output/'telemetry-summary.json').write_text(json.dumps(summary))
            (output/'calibrations.jsonl').write_text('')
            manifest = json.loads((output/'manifest.json').read_text())
            manifest.update(match_id=options['match_id'], metric_measurements_available=True)
            (output/'manifest.json').write_text(json.dumps(manifest))
            with closing(PreviewWriter(output/'preview.mp4',64,48,Fraction(25))) as writer, closing(iter_frames(source)) as frames:
                for frame in frames:
                    writer.write(frame.rgb,frame.timestamp_s)
                    options['progress_callback'](frame.frame_index+1,frame.timestamp_s)
            return manifest
        with self.store.worker_lock():
            run_one(self.store, pipeline=synthetic_pipeline)
        job = self.store.get(identity)
        self.assertEqual(job['status'], 'completed', job['error'])
        base = f'/jobs/{identity}'
        telemetry = self.client.get(base+'/telemetry?sort=top_speed_kmh&descending=true&limit=1', headers=self.headers).json()
        self.assertEqual(telemetry['items'][0]['track_id'], 1)
        self.assertAlmostEqual(telemetry['items'][0]['top_speed_kmh'], 21.6)
        self.assertEqual(telemetry['next_offset'], 1)
        filtered = self.client.get(base+'/telemetry?track_id=2', headers=self.headers).json()
        self.assertEqual([r['track_id'] for r in filtered['items']], [2])
        events = self.client.get(base+'/events', headers=self.headers).json()
        self.assertEqual(events['status'], 'available')
        self.assertEqual(events['items'][0]['kind'], 'sprint_candidate')
        self.assertFalse(events['confirmed_tackles_available'])
        maps = self.client.get(base+'/heatmaps', headers=self.headers).json()
        self.assertEqual(len(maps['items']), 4)
        png = self.client.get(base+'/artifacts/'+maps['items'][0]['file'], headers=self.headers)
        self.assertEqual(png.status_code, 200)
        self.assertEqual(png.headers['content-type'], 'image/png')
        self.assertTrue(png.content.startswith(b'\x89PNG'))
        for name in ['preview.mp4', 'tactics/preview.mp4', 'highlights/clip-0001.mp4']:
            response = self.client.get(base+'/artifacts/'+name, headers=self.headers | {'Range': 'bytes=0-31'})
            self.assertEqual(response.status_code, 206, response.text)
            self.assertEqual(response.headers['content-type'], 'video/mp4')
            self.assertEqual(len(response.content), 32)
        self.assertEqual(self.client.post(base+'/cancel', headers=self.headers).status_code, 409)
        for name in ['queries.sqlite3', '../source.video', 'tactics/../../source.video', 'highlights/index.html']:
            self.assertEqual(self.client.get(base+'/artifacts/'+name, headers=self.headers).status_code, 404)
        # Entire artifact subdirectories cannot be redirected via symlinks either.
        directory = self.store.directory(identity)/'analysis'
        (directory/'tactics').rename(directory/'moved-tactics')
        (directory/'tactics').symlink_to(directory/'moved-tactics', target_is_directory=True)
        self.assertEqual(self.client.get(base+'/artifacts/'+maps['items'][0]['file'], headers=self.headers).status_code, 404)


class JobLifecycleTests(unittest.TestCase):
    def test_cancel_wins_finish_transaction_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(tmp)
            identity = str(uuid.uuid4())
            store.enqueue(identity, 'hash', None)
            with store.worker_lock():
                store.claim()
                store.cancel(identity)
                store.finish(identity, result={'artifacts': {}})
                self.assertEqual(store.get(identity)['status'], 'cancelled')
                self.assertIsNone(store.get(identity)['result'])
            second = str(uuid.uuid4())
            store.enqueue(second, 'hash', None)
            store.claim(); store.cancel(second)
            with store.worker_lock():
                self.assertEqual(store.get(second)['status'], 'cancelled')

    def test_existing_database_migrates_without_losing_jobs(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            identity = str(uuid.uuid4())
            with sqlite3.connect(Path(tmp)/'jobs.sqlite3') as db:
                db.execute('''CREATE TABLE jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, processed_frames INTEGER DEFAULT 0,
                    timestamp_s REAL, max_frames INTEGER, source_sha256 TEXT NOT NULL, error TEXT, result TEXT)''')
                db.execute("INSERT INTO jobs (id,status,created_at,updated_at,source_sha256) VALUES (?,'queued','now','now','hash')", (identity,))
            for _ in range(2):
                job = JobStore(tmp).get(identity)
                self.assertEqual(job['status'], 'queued')
                self.assertEqual(job['render_media'], 0)
                self.assertIsNone(job['parent_id'])

@unittest.skipUnless(all(importlib.util.find_spec(m) for m in ('fastapi','httpx')), 'Requires backend extras')
class DashboardSessionTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from football_intelligence.api import create_app
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = TestClient(create_app(self.temp.name, token='private-test-token'))
        self.addCleanup(self.client.close)

    def test_cookie_session_authenticates_native_requests_and_logout_revokes_it(self):
        self.assertEqual(self.client.get('/jobs').status_code,401)
        self.assertEqual(self.client.post('/session',json={'token':'wrong'}).status_code,401)
        response=self.client.post('/session',json={'token':'private-test-token'},headers={'Origin':'http://testserver'})
        self.assertEqual(response.status_code,200)
        cookie=response.headers['set-cookie'].lower()
        self.assertIn('httponly',cookie);self.assertIn('samesite=strict',cookie)
        self.assertNotIn('private-test-token',cookie)
        session=self.client.cookies.get('football_session')
        self.assertEqual(self.client.get('/jobs').status_code,200)
        self.assertEqual(self.client.delete('/session',headers={'Origin':'https://attacker.invalid'}).status_code,403)
        self.assertEqual(self.client.delete('/session').status_code,200)
        self.assertEqual(self.client.get('/jobs',headers={'Cookie':f'football_session={session}'}).status_code,401)

    def test_cross_origin_login_expiration_and_invalid_body(self):
        self.assertEqual(self.client.post('/session',json={'token':'private-test-token'},headers={'Origin':'https://attacker.invalid'}).status_code,403)
        self.assertEqual(self.client.post('/session',json=['private-test-token']).status_code,401)
        self.client.post('/session',json={'token':'private-test-token'})
        import time
        with patch('football_intelligence.api.time.time',return_value=time.time()+9*3600):
            self.assertEqual(self.client.get('/jobs').status_code,401)
        # Existing CLI clients remain compatible and do not need browser cookies.
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/jobs',headers={'Authorization':'Bearer private-test-token'}).status_code,200)
