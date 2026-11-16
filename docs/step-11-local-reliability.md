# Step 11 — local reliability and validation foundation

Implemented November 13, 2026. Step 11 has started; public deployment and real-world accuracy validation are not complete.

## Operations

The local launcher binds its loopback port before starting a worker. Occupied ports fail with an actionable message. A worker exit stops the dashboard rather than leaving a silently nonfunctional queue. Worker failure causes a nonzero launcher exit. Ctrl-C still stops both. `--port` and `--data-dir` support isolated local instances.

```sh
.venv/bin/python scripts/run_dashboard.py
# Isolated instance:
.venv/bin/python scripts/run_dashboard.py --port 8001 --data-dir data/another-workspace
```

Authenticated `GET /system` reports worker-lock ownership, queue counts, available disk bytes and configured limits. A lock probe never invokes job recovery or mutates active jobs. Lock ownership does not prove responsive inference. The dashboard polls this status while connected and warns when the worker is offline or storage is low.

API defaults:

- One in-progress upload/retry per API process; concurrent submissions get HTTP 429.
- At most ten queued/running/cancel-requested jobs. SQLite serializes capacity checks and insertion. Retries respect the same cap.
- 2 GiB maximum input (existing limit).
- Preserve at least 512 MiB free storage while accepting uploads; declared-size and streaming checks return HTTP 507 when insufficient. Retries check space before copying.
- At most 8,294,400 input pixels, checked before first-frame decode. Larger videos receive HTTP 422. This is a configurable product resource limit, not a model limitation or automatic resize.

Configure limits through `create_app(...)`. No files are automatically deleted. Failed submissions remove only their newly created incomplete job directory. These are admission controls, not a disk reservation or a runtime memory/CPU/output quota. Multiple API processes are not supported as a deployment architecture; in-progress upload slots are process-local. The service remains localhost-only.

## Prediction diagnostics

### Runtime budgets (November 16)

The worker now checks elapsed monotonic time and free storage before inference,
at each frame progress callback, between post-processing stages and at their
cancellation checkpoints. Defaults are six hours per job and a 512 MiB free-disk
reserve. Configure the launcher or standalone worker with `--max-job-seconds`
and `--min-free-bytes`. The launcher applies the same disk reserve to uploads.
Exhausting a budget fails the job with an actionable error and withholds partial
results; subsequent queued jobs remain eligible to run. Existing files are kept.

These are cooperative limits, not a hard timeout: a blocked decoder/model call or
long operation without a checkpoint can overrun the budget. Disk checks do not
reserve capacity and a single write can cross the reserve. Hard process isolation,
memory/output quotas and retention controls remain unfinished.

### Trying your own video

Start `.venv/bin/python scripts/run_dashboard.py`, open
`http://127.0.0.1:8000/dashboard/`, and paste the printed temporary token into
**Connection**. Select **New analysis**, choose MP4/MOV/MKV (up to 2 GiB and
8,294,400 pixels), and begin with a frame limit such as 150 to check compatibility
and processing cost. This is about six seconds at 25 fps; duration varies with
frame rate. Resolution and timestamps are automatic. No pixel coordinates are
required. Pitch dimensions currently assume 105 × 68 m.

Preview/highlight generation is optional and off by default. Without it, use the
result timeline and analysis tabs. Predictions can miss or misidentify players
and the ball; experimental maps can be sparse or empty. Physical speed and sprint
accuracy are not validated, and confirmed tackles are not implemented. Uploading
your footage does not itself retrain the model. Files stay in the local workspace.

Each newly analyzed frame records `detection_quality`: missing, single-candidate or ambiguous ball state; candidate IDs; and `verified_ball_available=false`. No score-based candidate is silently promoted to a verified match ball. Aggregate diagnostics are stored in the analysis manifest and completed job results, and displayed in a collapsible dashboard panel. Existing stored results without these optional fields remain readable.

Person summaries count unconfirmed observations, unsafe associations, unknown teams and unknown roles. Flags overlap. These are predictions, not precision/recall; officials may legitimately lack team labels. A confirmed tracker ID is not verification of the underlying detection.

Read-only replay of both historical outputs is recorded with fingerprints in `evaluations/detection-quality-baseline.json`. The cached dashboard now exposes those diagnostics without rerunning detection or generating video. Second sample: 39 missing-ball frames, 79 single-candidate frames and 32 competing-candidate frames out of 150.

## Validation and remaining work

199 Python tests and three frontend tests passed. TypeScript/Vite build passed. Tests include atomic capacity under concurrent enqueues, worker probes preserving active job state, authenticated status, queue/retry caps, low disk cleanup, resolution rejection, ball ambiguity and pipeline-to-result export. Browser inspection confirmed the expanded quality panel. A real isolated launcher smoke check confirmed ready status, occupied-port refusal and shutdown when its idle worker was terminated. The test server was stopped afterward.

Remaining: representative independently labeled player/ball sequences and training/evaluation, validated physical measurements, storage retention controls, runtime compute/output budgets, packaging, and a separately designed authenticated multi-user hosting setup. This milestone improves observability and local operation; it does not improve detector precision or certify speed, sprint or tackle accuracy.
