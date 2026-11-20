# Reviewed position maps for uploaded video

## Geometry correction

The experimental midfield fitter previously selected white pixels using color
alone. Pale turf could satisfy those conditions and contaminate the fitted lines.
It now uses the existing pitch-paint ridge mask: narrow bright features with grass
nearby, followed by the same person masking and independent spatial paint holdout.
The final paint residual, correction magnitude, camera and foot screens have not
been relaxed. The method is recorded as `midfield_ridge_paint_refinement` in new
review evidence. This does not certify physical calibration or ground contact.

## Positions and velocity require different evidence

`build_tactics(..., review=..., position_only=True)` accepts only explicitly reviewed
experimental inputs. It retains the existing minimum identity duration, confirmed
observations, role/team continuity, checked geometry, visible-foot candidates and
camera checks. Current positions can appear before a continuous velocity smoothing
window matures. Unsafe displacement and failed geometry remain withheld. This is
an explicit new display policy, not a change to the speed/sprint gates.

Quality is `experimental_position_only`. Radar emits current observations only.
Occupancy still uses consecutive endpoints from the same measurement fragment;
no interpolation through gaps or persistence of old dots is added. Isolated
positions may appear in radar but cannot create occupancy time. Strict mode
cannot enable this option.

CLI: add `--position-only` to `build-tactics --review REVIEW ...`.

## Upload integration

When a newly processed upload has no validated metric measurements, the worker
now performs a data-only measurement review and builds position-only maps from it.
The review obeys cancellation and runtime/disk checkpoints and retains the original
analytics configuration. It does not render another preview. Review provenance and
results are published through the authenticated artifact endpoint and indexed radar
feeds the existing dashboard. Physical telemetry and event planning remain on the
strict original analysis. Existing completed jobs are not silently rewritten.

New artifact paths: `measurement-review/manifest.json`, `quality.jsonl`,
`summary.json`, and `estimates.jsonl`. The artifact allowlist contains only these
specific paths, not arbitrary review-directory access.

## Local paired evidence

Full 375-frame replay on identical saved observations compared the old color mask
and ridge mask, using the same position-only display rules. Old mask: zero accepted
geometry frames and zero radar samples. Ridge mask: 195 geometry frames, 171 with
camera-stability evidence, 44 displayed positions out of 8,488 person observations
(0.518%), and 1.12 person-seconds of individual occupancy. Team maps contain the
same supported time; do not sum team and individual maps as separate observations.
The default continuous-speed review still yields no mature physical measurements.

This is sparse same-recording development evidence, not 86% accuracy or held-out
validation. Stored observations include the known referee classification error;
map appearance does not correct identity/team labels. Fits apply only near the
center circle, explaining the spatially restricted maps. Existing saved previews
remain historical. No new match video was generated.

Private paired outputs remain under `data/upload-review/`: `color-mask-full-review`,
`color-mask-position-maps`, `ridge-positions` and `ridge-position-maps`.
Tests cover pale-turf rejection, known synthetic geometry, position display without
speed maturity, identity/camera gates, gap exclusion, review export and cancellation.
Remaining work: independent position/identity validation and wider reliable spatial
coverage, then valid event measurements. These are not marked complete.

## Revisit an existing analysis without detector inference

```sh
.venv/bin/python scripts/review_saved_job.py ORIGINAL_JOB_ID --source-data-dir data/backend --review-data-dir data/review-backend
.venv/bin/python scripts/run_dashboard.py --data-dir data/review-backend --port 8001
```

The command requires a separate idle review workspace, verifies the saved input
and artifact fingerprints, creates a child job and rebuilds geometry/maps using the
new worker path. Detection/tracking/classification are not rerun; their existing
errors remain. Provenance in the new manifest explicitly records this distinction.
No preview/highlight video is generated. The original queue/results are preserved.
All 233 Python tests pass, including source-job preservation and no-inference replay.

Dashboard verification on the completed child review confirmed a current radar
position at 9.56 seconds, Team A occupancy, and unavailable event measurements.
The radar badge recognizes position-only experimental quality, including gaps.
Frontend production build and model tests pass.
