"""Local durable queue. One separately supervised worker per data directory."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
import uuid

from .model_assets import sha256

ARTIFACTS = ('manifest.json', 'tracks.jsonl', 'calibrations.jsonl',
             'telemetry.jsonl', 'telemetry-summary.json', 'highlight-plan.json')


def now():
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'jobs').mkdir(exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, processed_frames INTEGER NOT NULL DEFAULT 0,
                timestamp_s REAL, max_frames INTEGER, source_sha256 TEXT NOT NULL,
                error TEXT, result TEXT)''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / 'jobs.sqlite3', timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def directory(self, identity):
        # Reject noncanonical IDs before constructing any filesystem path.
        if str(uuid.UUID(identity)) != identity:
            raise ValueError('Invalid job ID')
        return self.root / 'jobs' / identity

    def enqueue(self, identity, digest, max_frames):
        self.directory(identity)
        with self.connect() as db:
            db.execute('''INSERT INTO jobs
                (id,status,created_at,updated_at,max_frames,source_sha256)
                VALUES (?,'queued',?,?,?,?)''', (identity, now(), now(), max_frames, digest))
        return self.get(identity)

    def get(self, identity):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise KeyError(identity)
        result = dict(row)
        result['result'] = json.loads(result['result']) if result['result'] else None
        return result

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?", (now(), row['id']))
        return self.get(row['id'])

    def progress(self, identity, frames, timestamp):
        with self.connect() as db:
            db.execute('''UPDATE jobs SET processed_frames=?,timestamp_s=?,updated_at=?
                WHERE id=? AND status='running' ''', (frames, timestamp, now(), identity))

    def finish(self, identity, *, result=None, error=None):
        with self.connect() as db:
            db.execute('''UPDATE jobs SET status=?,result=?,error=?,updated_at=? WHERE id=?''',
                       ('failed' if error else 'completed', json.dumps(result) if result else None,
                        error, now(), identity))

    @contextmanager
    def worker_lock(self):
        # macOS/Linux local worker. OS releases lock even after a hard process crash.
        import fcntl
        with (self.root / 'worker.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('A worker already owns this data directory') from exc
            try:
                with self.connect() as db:
                    db.execute("""UPDATE jobs SET status='failed',error='Worker interrupted; submit a new job',
                        updated_at=? WHERE status='running'""", (now(),))
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


def run_one(store, *, pipeline=None, model_dir=Path('data/models'), device='cpu'):
    """Caller must own worker_lock. Returns False when queue is empty."""
    from .analysis import analyze_video
    from .highlights import write_plan
    job = store.claim()
    if job is None:
        return False
    identity = job['id']
    directory = store.directory(identity)
    output = directory / 'analysis'
    try:
        source = directory / 'source.video'
        if sha256(source) != job['source_sha256']:
            raise ValueError('Uploaded source changed before analysis')
        manifest = (pipeline or analyze_video)(source, output, match_id=identity,
            model_dir=model_dir, device=device, max_frames=job['max_frames'], write_preview=False,
            progress_callback=lambda count, timestamp: store.progress(identity, count, timestamp))
        if manifest['status'] != 'completed':
            raise ValueError('Analysis did not complete')
        plan = write_plan(output, output / 'highlight-plan.json')
        # Publish only when every expected data artifact exists. No media is generated.
        artifacts = {name: {'bytes': (output / name).stat().st_size,
                            'sha256': sha256(output / name)} for name in ARTIFACTS}
        store.finish(identity, result={'artifacts': artifacts,
            'metric_measurements_available': manifest['metric_measurements_available'],
            'events_status': plan['status'], 'candidate_events': len(plan['events']),
            'preview_generated': False})
    except Exception as exc:
        store.finish(identity, error=f'{type(exc).__name__}: {exc}')
    return True


def worker(root, *, once=False, model_dir=Path('data/models'), device='cpu'):
    store = JobStore(root)
    with store.worker_lock():
        while True:
            worked = run_one(store, model_dir=model_dir, device=device)
            if once:
                return
            if not worked:
                time.sleep(1)
