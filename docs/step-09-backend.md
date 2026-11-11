# Step 9 — local backend foundation

Started November 11, 2026, after the synthetic Step 8 viewer playback check.
This milestone implements authenticated video submission, SQLite job records,
a separate single analysis worker, persisted frame progress, result summaries,
and completed JSON/JSONL artifact downloads. It does not validate physical measurements.

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
- `GET /jobs/{id}`: `queued`, `running`, `completed`, or `failed`, timestamps,
  processed frame count, last processed source timestamp, source hash and errors.
  Frame counts are progress, not a fabricated completion percentage or ETA.
- `GET /jobs/{id}/results`: completed results with measurement availability,
  candidate count, event availability, artifact sizes and SHA-256 hashes.
- `GET /jobs/{id}/artifacts/{name}`: fixed allowlist of completed manifest, tracks,
  calibrations, telemetry, telemetry summary and strict highlight plan. Partial
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
jobs are not silently replayed or treated as completed. Resubmit to retry.
A normal worker stop between jobs is safe; interruption during processing may
leave diagnostic partial files, which remain inaccessible through the API.

Analysis writes no preview or highlight media. It produces a strict JSON highlight
plan after analysis. Successful software processing can still return
`metric_measurements_available: false` and `events_status: unavailable`.
The API does not relax contact, calibration, identity, or continuity gates.

## Validation and remaining work

November 11: 182 tests passed, no skips. Six new backend tests cover real synthetic
video upload through the actual analysis pipeline with an empty test detector,
frame progress, quality abstention, completed downloads and byte ranges, auth,
CORS, invalid/oversized uploads, worker failure, source tampering, durable restart,
atomic claiming and exclusion of a second worker. No trained-model inference or
real-video preview was needed for this milestone.

This is the first Step 9 milestone. Next work: paginated telemetry queries for the
dashboard, explicit cancellation/retry, API-controlled optional artifact jobs,
and bounded storage cleanup. Public deployment additionally needs isolation of
untrusted media decoding, per-user authorization/quotas, upload concurrency limits,
worker supervision and resource/time limits. Failed/interrupted job data and any
upload orphaned by a hard server crash currently remain on disk for manual cleanup.
There is no cloud queue, automatic retry, resumable upload, or dashboard yet.
