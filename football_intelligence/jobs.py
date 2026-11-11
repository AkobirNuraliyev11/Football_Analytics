"""Local durable queue. One separately supervised worker per data directory."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import shutil
import time
import uuid

from .model_assets import sha256

ARTIFACTS = ('manifest.json', 'tracks.jsonl', 'calibrations.jsonl',
             'telemetry.jsonl', 'telemetry-summary.json', 'highlight-plan.json')


class JobCancelled(Exception):
    pass


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
            db.execute('BEGIN IMMEDIATE')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(jobs)')}
            for name, declaration in [('render_media', 'INTEGER NOT NULL DEFAULT 0'),
                                      ('parent_id', 'TEXT')]:
                if name not in columns:
                    db.execute(f'ALTER TABLE jobs ADD COLUMN {name} {declaration}')

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

    def enqueue(self, identity, digest, max_frames, *, render_media=False, parent_id=None):
        self.directory(identity)
        with self.connect() as db:
            db.execute('''INSERT INTO jobs
                (id,status,created_at,updated_at,max_frames,source_sha256,render_media,parent_id)
                VALUES (?,'queued',?,?,?,?,?,?)''', (identity, now(), now(), max_frames, digest,
                    int(render_media), parent_id))
        return self.get(identity)

    def get(self, identity):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise KeyError(identity)
        result = dict(row)
        result['result'] = json.loads(result['result']) if result['result'] else None
        return result

    def list(self, limit=50, offset=0):
        with self.connect() as db:
            rows = db.execute('SELECT id FROM jobs ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?',
                              (limit, offset)).fetchall()
        return [self.get(row['id']) for row in rows]

    def cancel(self, identity):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM jobs WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise KeyError(identity)
            if row['status'] in ('completed', 'failed'):
                raise ValueError('Only waiting or active jobs can be cancelled')
            status = 'cancel_requested' if row['status'] in ('running', 'cancel_requested') else 'cancelled'
            db.execute('UPDATE jobs SET status=?,updated_at=? WHERE id=?', (status, now(), identity))
        return self.get(identity)

    def check_cancel(self, identity):
        if self.get(identity)['status'] in ('cancel_requested', 'cancelled'):
            raise JobCancelled('Cancellation requested')

    def retry(self, identity):
        old = self.get(identity)
        if old['status'] not in ('failed', 'cancelled'):
            raise ValueError('Retry requires a failed or cancelled job')
        new_id = str(uuid.uuid4())
        directory = self.directory(new_id)
        directory.mkdir()
        try:
            source = self.directory(identity) / 'source.video'
            shutil.copyfile(source, directory / 'source.video')
            if sha256(directory / 'source.video') != old['source_sha256']:
                raise ValueError('Source changed; upload the video again')
            return self.enqueue(new_id, old['source_sha256'], old['max_frames'],
                                render_media=old['render_media'], parent_id=identity)
        except BaseException:
            shutil.rmtree(directory)
            raise

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?", (now(), row['id']))
        return self.get(row['id'])

    def progress(self, identity, frames, timestamp):
        self.check_cancel(identity)
        with self.connect() as db:
            db.execute('''UPDATE jobs SET processed_frames=?,timestamp_s=?,updated_at=?
                WHERE id=? AND status='running' ''', (frames, timestamp, now(), identity))

    def finish(self, identity, *, result=None, error=None):
        # Completion and cancellation serialize in SQLite: a cancellation accepted
        # before this transaction wins even after files have finished rendering.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM jobs WHERE id=?', (identity,)).fetchone()
            if row is None or row['status'] not in ('running', 'cancel_requested'):
                raise ValueError('Only an active job can finish')
            cancelled = row['status'] == 'cancel_requested'
            status = 'cancelled' if cancelled else ('failed' if error else 'completed')
            db.execute('UPDATE jobs SET status=?,result=?,error=?,updated_at=? WHERE id=?',
                       (status, json.dumps(result) if status == 'completed' else None,
                        None if cancelled else error, now(), identity))

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
                    db.execute("UPDATE jobs SET status='cancelled',updated_at=? WHERE status='cancel_requested'", (now(),))
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


def run_one(store, *, pipeline=None, model_dir=Path('data/models'), device='cpu'):
    """Caller must own worker_lock. Returns False when queue is empty."""
    from .analysis import analyze_video
    from .highlights import write_plan, extract_highlights
    from .tactical_io import build_tactics
    from .config import AppConfig
    from .result_queries import build_index
    job = store.claim()
    if job is None:
        return False
    identity = job['id']
    directory = store.directory(identity)
    output = directory / 'analysis'
    try:
        store.check_cancel(identity)
        source = directory / 'source.video'
        if sha256(source) != job['source_sha256']:
            raise ValueError('Uploaded source changed before analysis')
        manifest = (pipeline or analyze_video)(source, output, match_id=identity,
            model_dir=model_dir, device=device, max_frames=job['max_frames'], write_preview=bool(job['render_media']),
            progress_callback=lambda count, timestamp: store.progress(identity, count, timestamp))
        if manifest['status'] != 'completed':
            raise ValueError('Analysis did not complete')
        plan = write_plan(output, output / 'highlight-plan.json')
        check = lambda: store.check_cancel(identity)
        check()
        config = AppConfig.from_dict({'pitch': manifest['pitch'], 'analytics': manifest['analytics']})
        tactical = build_tactics(output / 'tracks.jsonl', output / 'tactics', config=config,
            write_preview=bool(job['render_media']), cancel_check=check)
        check()
        clips = None
        if job['render_media']:
            clips = extract_highlights(source, output, output / 'highlights', overlays=True,
                                       cancel_check=check)
        build_index(output, check=check)
        check()
        names = list(ARTIFACTS)
        if job['render_media']:
            names.append('preview.mp4')
        names += ['tactics/manifest.json'] + ['tactics/' + n for n in tactical['artifacts']]
        if clips:
            names += ['highlights/playlist.json'] + ['highlights/' + w['file'] for w in clips['windows']]
        artifacts = {name: {'bytes': (output / name).stat().st_size,
                            'sha256': sha256(output / name)} for name in names}
        occupancy = json.loads((output / 'tactics/occupancy.json').read_text())
        store.finish(identity, result={'artifacts': artifacts,
            'metric_measurements_available': manifest['metric_measurements_available'],
            'events_status': plan['status'], 'candidate_events': len(plan['events']),
            'preview_generated': bool(job['render_media']),
            'heatmaps': [{'file': 'tactics/heatmap-' + g['id'] + '.png',
                         'identity': g['identity'], 'observed_person_seconds': g['observed_person_seconds'],
                         'quality': occupancy['quality']} for g in occupancy['groups']],
            'tactics_status': occupancy['status'], 'coverage': occupancy['coverage'],
            'clips_generated': clips['clips_written'] if clips else 0,
            'query_index_version': 1})
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
