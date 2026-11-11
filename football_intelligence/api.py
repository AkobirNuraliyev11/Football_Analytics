"""Authenticated, local-first video submission and completed result downloads."""
from contextlib import closing
import hashlib
import hmac
from pathlib import Path
import shutil
import uuid

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from .jobs import ARTIFACTS, JobStore
from .video import iter_frames, probe_video


def create_app(root, *, token, max_upload_bytes=2 * 1024**3, allowed_origins=()):
    if not token or max_upload_bytes < 1:
        raise ValueError('A nonempty API token and positive upload limit are required')
    store = JobStore(root)

    async def authorize(request: Request):
        supplied = request.headers.get('authorization', '')
        if not hmac.compare_digest(supplied.encode(), f'Bearer {token}'.encode()):
            raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})

    app = FastAPI(title='Football Analytics', version='0.1.0', dependencies=[Depends(authorize)])
    app.state.store = store
    if allowed_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(allowed_origins),
            allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type', 'Range'],
            expose_headers=['Content-Range', 'Accept-Ranges', 'Content-Length'])

    def get_job(identity):
        try:
            store.directory(identity)
            return store.get(identity)
        except (ValueError, KeyError):
            raise HTTPException(404, 'Job not found') from None

    @app.post('/jobs', status_code=202)
    async def submit(request: Request, max_frames: int | None = Query(default=None, ge=1)):
        """Send the video as the raw request body (not multipart/form-data)."""
        if request.headers.get('content-type', '').split(';')[0] not in (
                'application/octet-stream', 'video/mp4', 'video/quicktime', 'video/x-matroska'):
            raise HTTPException(415, 'Send raw video bytes with Content-Type: application/octet-stream')
        length = request.headers.get('content-length')
        if length:
            try:
                size = int(length)
            except ValueError:
                raise HTTPException(400, 'Invalid Content-Length') from None
            if size < 0:
                raise HTTPException(400, 'Invalid Content-Length')
            if size > max_upload_bytes:
                raise HTTPException(413, 'Video exceeds upload limit')
        identity = str(uuid.uuid4())
        directory = store.directory(identity)
        directory.mkdir()
        source = directory / 'source.video'
        queued = False
        try:
            digest, size = hashlib.sha256(), 0
            with source.open('xb') as target:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > max_upload_bytes:
                        raise HTTPException(413, 'Video exceeds upload limit')
                    digest.update(chunk)
                    await run_in_threadpool(target.write, chunk)
            def validate():
                metadata = probe_video(source)
                if metadata.width < 1 or metadata.height < 1:
                    raise ValueError('Invalid video dimensions')
                with closing(iter_frames(source)) as frames:
                    if next(frames, None) is None:
                        raise ValueError('Video contains no decodable frames')
            try:
                await run_in_threadpool(validate)
            except ValueError:
                raise HTTPException(422, 'Video is empty, unreadable, or has invalid timing') from None
            job = store.enqueue(identity, digest.hexdigest(), max_frames)
            queued = True
            return job
        finally:
            if not queued:
                shutil.rmtree(directory)

    @app.get('/jobs/{identity}')
    def status(identity: str):
        return get_job(identity)

    @app.get('/jobs/{identity}/results')
    def results(identity: str):
        job = get_job(identity)
        if job['status'] != 'completed':
            raise HTTPException(409, 'Results require a completed job')
        return job['result']

    @app.get('/jobs/{identity}/artifacts/{name}')
    def artifact(identity: str, name: str, request: Request):
        job = get_job(identity)
        if job['status'] != 'completed':
            raise HTTPException(409, 'Artifacts require a completed job')
        if name not in ARTIFACTS or name not in job['result']['artifacts']:
            raise HTTPException(404, 'Artifact not found')
        # Only single ranges are needed by clients; bound parser work on older Starlette.
        range_header = request.headers.get('range', '')
        if len(range_header) > 128 or ',' in range_header:
            raise HTTPException(400, 'Only a single byte range is supported')
        directory = store.directory(identity) / 'analysis'
        path = directory / name
        if path.is_symlink() or path.resolve().parent != directory.resolve() or not path.is_file():
            raise HTTPException(404, 'Artifact not found')
        return FileResponse(path, filename=name, media_type=(
            'application/x-ndjson' if name.endswith('.jsonl') else 'application/json'))

    return app
