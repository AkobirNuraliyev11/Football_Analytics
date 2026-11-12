"""Authenticated, local-first video submission and completed result downloads."""
from contextlib import closing
import hashlib
import hmac
import re
import secrets
import time
from typing import Literal
from pathlib import Path
import shutil
import uuid

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .jobs import ARTIFACTS, JobStore
from .result_queries import query
from .video import iter_frames, probe_video


def create_app(root, *, token, max_upload_bytes=2 * 1024**3, allowed_origins=()):
    if not token or max_upload_bytes < 1:
        raise ValueError('A nonempty API token and positive upload limit are required')
    store = JobStore(root)

    sessions = {}

    def check_origin(request):
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'Browser sessions require same-origin requests')

    async def authorize(request: Request):
        if (request.url.path == '/session' and request.method == 'POST') or (request.url.path == '/' and request.method == 'GET'):
            return
        session = request.cookies.get('football_session')
        if session and sessions.get(session, 0) > time.time():
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                check_origin(request)
            return
        supplied = request.headers.get('authorization', '')
        if not hmac.compare_digest(supplied.encode(), f'Bearer {token}'.encode()):
            raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})

    app = FastAPI(title='Football Analytics', version='0.1.0', dependencies=[Depends(authorize)])
    app.state.store = store

    @app.post('/session')
    async def sign_in(request: Request):
        check_origin(request)
        try:
            body = await request.json()
            supplied = body.get('token', '') if isinstance(body, dict) else ''
        except ValueError:
            supplied = ''
        if not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode(), token.encode()):
            raise HTTPException(401, 'Incorrect API token')
        for key, expiry in list(sessions.items()):
            if expiry <= time.time():
                del sessions[key]
        if len(sessions) >= 128:
            del sessions[next(iter(sessions))]
        session = secrets.token_urlsafe(32)
        sessions[session] = time.time() + 8 * 3600
        from fastapi.responses import JSONResponse
        response = JSONResponse({'authenticated': True})
        response.set_cookie('football_session', session, httponly=True, samesite='strict',
                            secure=request.url.scheme == 'https', max_age=8*3600)
        return response

    @app.delete('/session')
    def sign_out(request: Request):
        sessions.pop(request.cookies.get('football_session'), None)
        from fastapi.responses import JSONResponse
        response = JSONResponse({'authenticated': False})
        response.delete_cookie('football_session')
        return response

    dashboard = Path(__file__).resolve().parents[1] / 'frontend/dist'
    if (dashboard / 'index.html').is_file():
        app.mount('/dashboard', StaticFiles(directory=dashboard, html=True), name='dashboard')

    @app.get('/')
    def home():
        return RedirectResponse('/dashboard/')

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
    async def submit(request: Request, max_frames: int | None = Query(default=None, ge=1),
                     render_media: bool = False):
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
            job = store.enqueue(identity, digest.hexdigest(), max_frames, render_media=render_media)
            queued = True
            return job
        finally:
            if not queued:
                shutil.rmtree(directory)

    @app.get('/jobs')
    def list_jobs(limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        rows = store.list(limit + 1, offset)
        return {'items': rows[:limit], 'next_offset': offset + limit if len(rows) > limit else None}

    @app.post('/jobs/{identity}/cancel')
    def cancel(identity: str):
        get_job(identity)
        try:
            return store.cancel(identity)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.post('/jobs/{identity}/retry', status_code=202)
    def retry(identity: str):
        get_job(identity)
        try:
            return store.retry(identity)
        except (ValueError, OSError) as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get('/jobs/{identity}')
    def status(identity: str):
        return get_job(identity)

    @app.get('/jobs/{identity}/results')
    def results(identity: str):
        job = get_job(identity)
        if job['status'] != 'completed':
            raise HTTPException(409, 'Results require a completed job')
        return job['result']

    def complete(identity):
        job = get_job(identity)
        if job['status'] != 'completed':
            raise HTTPException(409, 'Results require a completed job')
        return job

    def read_query(identity, kind, **kwargs):
        job = complete(identity)
        try:
            data = query(store.directory(identity) / 'analysis', kind, **kwargs)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return data | {'metric_measurements_available': job['result']['metric_measurements_available'],
                       'scope': 'Observed local tracks and fragments; not full-match athlete totals'}

    @app.get('/jobs/{identity}/frames/{kind}')
    def frames(identity: str, kind: Literal['tracks', 'telemetry', 'radar'],
               offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500),
               start_s: float = Query(default=0., ge=0, allow_inf_nan=False),
               end_s: float | None = Query(default=None, ge=0, allow_inf_nan=False)):
        if end_s is not None and end_s < start_s:
            raise HTTPException(422, 'end_s must be at least start_s')
        return read_query(identity, kind, offset=offset, limit=limit, start_s=start_s, end_s=end_s)

    @app.get('/jobs/{identity}/telemetry')
    def telemetry(identity: str, offset: int = Query(default=0, ge=0),
                  limit: int = Query(default=100, ge=1, le=500),
                  track_id: int | None = Query(default=None, ge=0),
                  sort: Literal['start_s', 'top_speed_kmh', 'observed_distance_m', 'sprint_count'] = 'start_s',
                  descending: bool = False):
        return read_query(identity, 'fragments', offset=offset, limit=limit,
                          track_id=track_id, sort=sort, descending=descending)

    @app.get('/jobs/{identity}/events')
    def events(identity: str, offset: int = Query(default=0, ge=0),
               limit: int = Query(default=100, ge=1, le=500)):
        job = complete(identity)
        return read_query(identity, 'events', offset=offset, limit=limit) | {
            'status': job['result']['events_status'], 'confirmed_tackles_available': False}

    @app.get('/jobs/{identity}/heatmaps')
    def heatmaps(identity: str):
        result = complete(identity)['result']
        return {'status': result.get('tactics_status', 'unavailable'),
                'items': result.get('heatmaps', []), 'coverage': result.get('coverage'),
                'placeholder_file': ('tactics/heatmap-unavailable.png' if
                    'tactics/heatmap-unavailable.png' in result['artifacts'] else None),
                'scope': 'Observed occupancy; not possession or pitch control'}

    @app.get('/jobs/{identity}/artifacts/{name:path}')
    def artifact(identity: str, name: str, request: Request):
        job = complete(identity)
        allowed = (name in ARTIFACTS or name == 'preview.mp4' or
                   name in ('tactics/manifest.json', 'tactics/occupancy.json', 'tactics/radar.jsonl',
                            'tactics/radar.png', 'tactics/preview.mp4', 'tactics/heatmap-unavailable.png', 'highlights/playlist.json') or
                   re.fullmatch(r'tactics/heatmap-[0-9a-f]{20}\.png', name) or
                   re.fullmatch(r'highlights/clip-[0-9]{4,}\.mp4', name))
        if not allowed or name not in job['result']['artifacts']:
            raise HTTPException(404, 'Artifact not found')
        range_header = request.headers.get('range', '')
        if len(range_header) > 128 or ',' in range_header:
            raise HTTPException(400, 'Only a single byte range is supported')
        directory = store.directory(identity) / 'analysis'
        path = directory / name
        if (not path.is_file() or not path.resolve().is_relative_to(directory.resolve()) or
                any(part.is_symlink() for part in [path, *path.parents] if part != directory.parent)):
            raise HTTPException(404, 'Artifact not found')
        media_type = {'.jsonl': 'application/x-ndjson', '.json': 'application/json',
                      '.mp4': 'video/mp4', '.png': 'image/png'}[path.suffix]
        return FileResponse(path, filename=path.name, media_type=media_type,
                            content_disposition_type='inline' if path.suffix in ('.mp4', '.png') else 'attachment')

    return app
