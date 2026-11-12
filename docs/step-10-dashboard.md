# Step 10 — professional coaching dashboard

Implemented November 12, 2026 from the approved Concept 01. React + TypeScript,
Vite, local CSS and Lucide icons. This is a working local application, not a hosted
service. The current build follows the navy/charcoal, restrained teal design.

## Start it

Install Node.js 22.12+ (or a compatible newer version) and the Python backend and
analysis dependencies. Vite's supported runtime versions are documented in its
[official guide](https://vite.dev/guide/). From the repository root:

```sh
.venv/bin/python -m pip install -e '.[backend,detection]'
# Optional: prepare cached real-video results already present in this working copy.
.venv/bin/python scripts/prepare_dashboard_demo.py
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python scripts/run_dashboard.py
```

Open `http://127.0.0.1:8000/dashboard/`. The launcher runs the local API and a
single analysis worker, prints a temporary token for Connection, and stops both
when you press Ctrl-C. An existing `FOOTBALL_API_TOKEN` is used if set. Download
model weights with `python -m football_intelligence download-models` before real
inference. An upload remains queued if no worker is running.

The prepared build and cached data currently exist in this working copy. This
Mac also has a checksum-verified Node runtime under the ignored
`data/tooling/node-v22.23.4-darwin-arm64/bin/`; it can be added to PATH locally.
That runtime is not required on other machines with Node installed normally.
No dependency or CDN download happens during dashboard use after the build.

For development, `npm run dev` serves the UI under `/dashboard/` and proxies
`/jobs` and `/session` to the local API on port 8000. Production-style local use
serves the built files from the same Python process as the API.

## Implemented flows

- **Cached sample review:** uses the existing six-second second-video tracking
  preview, predicted classifications and experimental radar/occupancy outputs.
  A visible banner distinguishes it from live analysis. The preparation script
  copies saved artifacts; it does not run inference or render new match footage.
  Without the local data, a fresh clone can still connect to the API and upload.
- **Live upload:** file picker or drop target, upload progress/cancel, frame limit,
  media rendering off by default, explicit video-generation checkbox, and errors.
- **Queue:** recent jobs, progress, waiting/failed/cancelled states, cancellation,
  and retry into a new job. Refresh every four seconds while connected.
- **Match review:** native video controls, current observed player/role labels,
  source-time radar, no-video timeline for data-only runs, and explicit unavailable
  metrics. Live frame queries load short indexed time windows, not entire videos'
  JSONL records. Old requests are aborted when the selection/time window changes.
- **Players:** current-frame team filter, continuous measured fragments with
  server-side speed/distance/sprint/time sorting and pagination. IDs are local;
  no unverified full-match totals or persistent athlete identity is implied.
- **Heatmaps:** selectable team/local-track occupancy images, evidence quality,
  observed person-seconds and coverage. Missing groups do not get invented maps.
- **Events:** conditional sprint/duel candidates, source-time seek, pagination,
  and eligible clip playback when media was requested. Unavailable measurements
  are distinguished from a valid analysis finding no qualifying candidates.
- **Exports:** cached review JSON or the live telemetry summary.
- **Responsive layout:** desktop sidebar and two-column video/radar; narrow screens
  use a compact navigation bar and stacked content. Native controls have labels;
  the connection dialog supports Escape and keyboard focus containment.

## Evidence and security contracts

The approved mockup is illustrative; the implemented UI uses actual stored records.
The initial sample frame has unclassified people and an empty radar, which is
correct for that timestamp. Labels update with playback. A heatmap summarizes
eligible intervals, while radar shows only the current available frame. Colors
are normalized independently per heatmap and do not measure possession/control.
Gaps do not borrow future positions or retain stale dots. Speed/distance nulls
remain dashes. Confirmed tackles, counterattacks and possession are not implemented.

Browser sign-in uses `POST /session` with the existing API token. The server issues
an opaque, HttpOnly, SameSite=Strict cookie for eight hours; HTTPS also sets Secure.
Cookies let native video/image requests authenticate without putting tokens in
URLs, localStorage or sessionStorage. Mutation requests with a different Origin
are rejected. Logout revokes the server-side session. Sessions are in memory and
expire on server restart; CLI bearer authentication remains supported.

The static dashboard shell and prepared public-sample demo files are unauthenticated
local assets. User uploads/results remain behind API authentication. Do not put
private footage into `frontend/public`. The service stays bound to loopback and is
not intended for public/multi-user deployment.

## Verification

- Production TypeScript/Vite build passed.
- Three frontend model tests pass: temporal gaps/no future samples, null metric
  display, and safe artifact paths.
- 190 Python tests passed without skips, including cookie session authentication,
  logout revocation, wrong-origin rejection, expiration and bearer compatibility.
- In-app browser: cached video played to completion, heatmap selector changed to
  Team B with 2.16 person-seconds, event abstention displayed correctly, and team
  filtering worked. At 390 px the document had no horizontal overflow.
- Browser upload of a synthetic MKV reached queued state; cancellation and retry
  worked, and a separately executed synthetic detector worker produced completed
  results visible through the live UI. No trained-model run or real-match preview
  regeneration was needed.

## Remaining scope

This is the first Step 10 implementation. Follow-up work includes user feedback on
layout, additional real-video validation, richer exports and measured-fragment charts,
and deployment/storage/resource controls. No CSV export, full-match athlete
re-identification or verified tackle detector is claimed. Large media and generated
build/demo files remain ignored by Git; source and lockfile are committed.

November 13 update: the dashboard exposes detection-quality diagnostics and connected worker/storage warnings. See [Step 11](step-11-local-reliability.md) for API and startup controls.
