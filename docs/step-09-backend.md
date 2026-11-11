# Step 9 — local result-serving workflow

Started November 11, 2026, after the synthetic Step 8 viewer playback check.
This milestone implements authenticated video submission, SQLite job records,
a separate single analysis worker, persisted frame progress, result summaries,
indexed telemetry/radar/tracking queries, cancellation/retry, heatmaps, candidate events,
and opt-in video/highlight streaming. It does not validate physical measurements.

## Run locally

Install the backend and analysis dependencies in the project environment:

```sh
.venv/bin/python -m pip install -e '.[backend,detection]'
.venv/bin/python -m football_intelligence download-models
export FOOTBALL_API_TOKEN="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"
.venv/bin/python -m football_intelligence serve --data-dir data/backend
```

The server binds only to `127.0.0.1:8000`. Keep the token private. In a second
terminal, from the same project directory, start the worker:

```sh
.venv/bin/python -m football_intelligence worker --data-dir data/backend
```

The worker needs no API token. It reads only the local queue. Use `--once` to
process at most one waiting job and exit. macOS/Linux are supported for the
worker's OS file lock; Windows support is not implemented.

From a terminal with the token exported, upload raw video bytes:

```sh
curl --fail-with-body -X POST 'http://127.0.0.1:8000/jobs?max_frames=100' \
  -H "Authorization: Bearer $FOOTBALL_API_TOKEN" \
  -H 'Content-Type: application/octet-stream' \
  --data-binary '@/absolute/path/to/your-video.mp4'
```

Remove `?max_frames=100` to process the entire video. Resolution and timestamps
are read automatically. The existing explicit 105 × 68 m pitch assumption remains;
it is not an automatic physical size measurement. This first API uses default
analysis configuration and CPU inference. Worker `--device` and `--model-dir`
options can select an installed device and models.

Media generation stays off by default. Add `&render_media=true` to the upload URL
only when you want a full annotated analysis video, a short radar video (up to
12 seconds) and eligible candidate highlight clips. Heatmap PNGs and radar records
are produced without that option. When no positions pass the strict checks, the
heatmap endpoint returns an empty list plus an explicit unavailable placeholder;
it never invents activity. This API uses strict analysis, not experimental reviews.

The response includes `id` and `status: queued`. Substitute that ID below:

```sh
curl -H "Authorization: Bearer $FOOTBALL_API_TOKEN" http://127.0.0.1:8000/jobs/JOB_ID
curl -H "Authorization: Bearer $FOOTBALL_API_TOKEN" http://127.0.0.1:8000/jobs/JOB_ID/results
curl -H "Authorization: Bearer $FOOTBALL_API_TOKEN" \
  http://127.0.0.1:8000/jobs/JOB_ID/artifacts/telemetry-summary.json
```

API documentation is available at `/docs`; protected requests need the bearer
header. These examples use curl because a dashboard is not implemented yet.

## Contracts

- `POST /jobs`: raw video body, optional positive `max_frames`. The upload limit
  defaults to 2 GiB and is checked while streaming, including chunked uploads.
  Probe metadata and decode the first frame before accepting the job. A later
  corrupt frame fails the worker job. Multipart uploads and arbitrary source URLs
  or server filesystem paths are not accepted.
- `GET /jobs/{id}`: `queued`, `running`, `cancel_requested`, `cancelled`, `completed`, or `failed`, timestamps,
  processed frame count, last processed source timestamp, source hash and errors.
  Frame counts are progress, not a fabricated completion percentage or ETA.
- `GET /jobs/{id}/results`: completed results with measurement availability,
  candidate count, event availability, artifact sizes and SHA-256 hashes.
- `GET /jobs/{id}/artifacts/{name}`: fixed allowlist of completed manifest, tracks,
  calibrations, telemetry, telemetry summary, strict highlight plan, tactical PNGs/JSON
  and explicitly requested MP4s/clip playlist. Nested artifact names come from the
  published results; unlisted paths and symlinked files/directories are rejected. Partial
  files and the original video are not served. Single HTTP byte ranges support
  incremental download; multi-range requests are rejected. Starlette's
  [FileResponse](https://www.starlette.io/responses/#fileresponse) supplies range responses.

All data endpoints require the bearer token. CORS is disabled unless an exact
origin is passed with `serve --allow-origin http://localhost:5173`. CORS is not
a substitute for authentication. The data directory is trusted local storage;
this service is not designed for public or multi-user deployment.

The API never invokes inference inside the upload request. SQLite atomically
claims jobs. An OS lock permits one worker per data directory. API restart does
not interrupt the worker. Worker restart marks previously running jobs failed
with an explicit interruption reason; waiting jobs remain queued. Interrupted
jobs are not silently replayed or treated as completed. Explicit retry creates a new job.
A normal worker stop between jobs is safe; interruption during processing may
leave diagnostic partial files, which remain inaccessible through the API.

Successful software processing can still return
`metric_measurements_available: false` and `events_status: unavailable`.
The API does not relax contact, calibration, identity, or continuity gates.

## Dashboard result endpoints

All routes below require the same bearer header as uploads. Paginated responses
provide `items` and `next_offset`; a null next offset marks the last page.

| Route | Behavior |
|---|---|
| `GET /jobs?limit=50&offset=0` | List jobs, newest first; limit 1–100 |
| `POST /jobs/{id}/cancel` | Cancel queued jobs immediately; request cooperative cancellation for running jobs |
| `POST /jobs/{id}/retry` | Failed/cancelled jobs only; creates a new ID with `parent_id`, copies and verifies the original source, inherits frame/media options |
| `GET /jobs/{id}/frames/tracks` | Original tracking frame records |
| `GET /jobs/{id}/frames/telemetry` | Original per-frame telemetry including null values and rejection reasons |
| `GET /jobs/{id}/frames/radar` | Current eligible positions, including explicit gaps |
| `GET /jobs/{id}/telemetry` | Continuous measurement fragments; optional `track_id`, `sort` and `descending` |
| `GET /jobs/{id}/events` | Paginated candidate events plus availability; `confirmed_tackles_available` remains false |
| `GET /jobs/{id}/heatmaps` | PNG names, group identities, quality and person-seconds; coverage and unavailable placeholder when applicable |

Frame, telemetry and event endpoints accept `limit` (1–500) and nonnegative
`offset`. Frame queries additionally accept inclusive `start_s` and `end_s` bounds.
Telemetry sorts are `start_s`, `top_speed_kmh`, `observed_distance_m`, and
`sprint_count`, with fragment ID breaking ties. Fragments are not aggregated into
unverified full-match athlete totals. Queries use a worker-built SQLite index;
they do not reread all JSONL files for every request.

Example requests (add the bearer header):

```text
GET /jobs/JOB_ID/frames/tracks?start_s=2&end_s=4&limit=50
GET /jobs/JOB_ID/telemetry?sort=top_speed_kmh&descending=true&limit=20
GET /jobs/JOB_ID/events
GET /jobs/JOB_ID/heatmaps
GET /jobs/JOB_ID/artifacts/tactics/heatmap-unavailable.png
GET /jobs/JOB_ID/artifacts/preview.mp4
GET /jobs/JOB_ID/artifacts/highlights/playlist.json
```

Only published artifacts can be fetched. Preview/playlist URLs return 404 when
media was not requested. The original upload and internal query database are not
served. MP4/PNG responses have inline content disposition; other downloads use
attachment disposition. MP4s support authenticated single byte ranges for seeking.
A future frontend must send the bearer header on its media requests too.

Cancellation is cooperative, checked between analysis frames, tactical replay
frames, highlight decoding frames and indexing rows, as well as phase boundaries.
It does not interrupt a model-loading call, an in-flight frame inference, or an
indivisible planning/rendering operation. Accepted cancellation wins over later
completion atomically. Partial and cancelled output stays inaccessible. On restart,
`cancel_requested` becomes `cancelled`; other interrupted running jobs become
`failed`. Cancelling an already cancelled job is idempotent; completed/failed jobs
return 409. Retry is explicit and each request creates a distinct job, rather than
resuming the old partial output. Storage for old attempts is retained.

Existing queue databases migrate automatically with media disabled for old jobs.
Old completed artifacts remain downloadable, but jobs created before this milestone
have no query index; query endpoints return 409 and explain that a new submission
is needed. They are not silently reprocessed.

## Validation and remaining work

November 11: **188 tests passed, no skips**, including 12 backend tests.
Coverage includes synthetic upload through the real pipeline with an empty detector,
strict abstention, default no-media behavior, indexed pagination/time filters,
fragment sorting, PNG delivery, MP4 ranges and synthetic positive event/heatmap
outputs. Lifecycle checks cover cancellation during inference, cancellation winning
publication, interrupted cancellation, retry provenance/source verification, and
migration of preexisting queue databases. Auth, CORS, size limits, path/symlink
restrictions, worker failures and atomic worker claims remain covered.
No trained-model inference or real-match preview was needed for this milestone.

The core local result-serving workflow is implemented. Next is the Step 10 review
dashboard. Before public deployment, work remains on bounded storage cleanup,
isolation of untrusted media decoding, per-user authorization/quotas, upload
concurrency limits, worker supervision and resource/time limits. Failed/interrupted
job data and any upload orphaned by a hard server crash currently remain on disk
for manual cleanup. There is no cloud queue, automatic retry, resumable upload,
or dashboard yet. Physical speed/sprint accuracy and confirmed tackle detection
remain separate unresolved product requirements.
