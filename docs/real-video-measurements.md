# Real-video measurement review

This follow-up addresses Step 6's real-footage prerequisites before Step 7. It adds
experimental estimates using new visual evidence, while keeping strict validated
telemetry separate. It does **not** establish accurate full-match player statistics.

## What changed

The existing model's landmark residual was small even where its projected center
circle missed the actual paint. The new midfield refiner extracts bright, relatively
neutral paint pixels, masks detected people and the ball, and fits the center circle,
halfway line, and near touchline with robust least squares. It requires spatial
support and checks different 16-pixel image tiles from those used for fitting.
The circle radius is 9.15 m under [IFAB Law 1](https://www.theifab.com/laws/latest/the-field-of-play/).
Pitch dimensions remain the configured assumption, not something inferred exactly
from arbitrary pixels. Dark lines, unusual grass, shadows, nonstandard markings,
or camera views without these markings may fail the checks.

Camera motion is estimated from stationary field features inside the circle, with
forward/backward optical-flow checks and RANSAC. The transported mapping must still
match visible paint **inside that supported region**. It is not extrapolated to the
farther touchline for the camera drift test. If a model seed fails but the previous
consecutive frame has checked geometry, its mapping may seed a new fit; the current
frame must pass the same paint and motion tests. There is no unchecked carry-forward
across lost evidence, gaps, or shots.

Player candidates must have sufficiently large, unclipped boxes, unoccluded lower
bodies, visible grass immediately beneath the box, stable body height, and an anchor
inside the checked circle. Position sensitivity to a three-pixel anchor perturbation
is recorded. These are visibility heuristics: grass beneath a box and visible shoes
do not prove ground contact. Ordinary running flight phases, jumps, bounding-box
jitter, and same-team identity swaps remain possible. No pose or ground-contact
model was added. All outputs from this mode are explicitly **experimental estimates**.

The original association, displacement, gap, and maturity checks remain in use.
Peak speeds exclude startup intervals shorter than a complete smoothing window;
otherwise a single early box jitter could become the reported peak of a mature track.

## Real-footage checks

Source: the existing 30-second Roboflow football clip, SHA-256
`43d342c78fbb40e522f48ab378fbee83b5b880d35c056836e0d493ec2b15ee51`.
This is development footage, not a held-out benchmark. Cached detections are reused;
image-based paint and camera checks run on the actual decoded video.

Six assistant-reviewed paint intersections at frames 0, 50, and 100 were not supplied
to the fitter. Their projected discrepancy decreased from **1.09 m RMSE to 0.14 m RMSE**.
The labels are approximate to about three pixels, all lie on the halfway line, and
share the same clip and geometric assumptions. This is not surveyed ground truth,
full-pitch validation, or a claim of 14-centimeter player-location accuracy.

For red-shirt track 23, two visually selected shoe points at 1.0 and 3.0 seconds
give an estimated **5.47 m net displacement**, or **9.84 km/h mean net speed**. Automatic
box-bottom anchors on those frames give **8.97 km/h**. The different position proxies
and gait explain part of that difference. A three-pixel endpoint perturbation alone
corresponds to about **1.44 km/h sensitivity**, excluding geometry, scale, identity,
and ground-contact errors. This sensitivity is not a statistical confidence interval.
Net endpoint displacement is not distance traveled, and mean net speed is not
instantaneous speed. No independent athlete-speed ground truth is available.

The full 750-frame automatic trial produced four mature fragments:

| Track | Role | Observed interval | Estimated distance | Estimated peak speed |
|---|---|---|---|---|
| 23 | Outfield, A | 1.00–3.32 s | 6.32 m | 11.60 km/h |
| 7 | Outfield, B | 21.68–25.24 s | 4.88 m | 6.76 km/h |
| 11 | Outfield, A | 22.12–25.24 s | 4.10 m | 7.53 km/h |
| 32 | Official | 27.56–29.72 s | 3.56 m | 7.69 km/h |

No sustained sprint was detected within those fragments. That is not a conclusion
about the rest of the match. There were 529 frames with paint fits and 508 with camera
checks, but only **83 of 17,460 person observations (0.48%)** had publishable estimates
after all gates and warmup. This is observation coverage, not video-time coverage.
Ninety-one short fragments were excluded. Whole-player and whole-match totals remain
unsupported. Strict telemetry still withholds this footage.

## Run

First create an ordinary analysis run as before. Then use a new output directory:

```sh
.venv/bin/python -m football_intelligence review-measurements /path/to/match.mp4 --analysis data/my-match/analysis --output data/my-match/measurement-review
```

For this repository's cached revised example:

```sh
.venv/bin/python -m football_intelligence review-measurements data/demo-step-04/source.mp4 --analysis data/demo-step-05/full-30s --tracks data/tracking-review/revised-final/tracks.jsonl --output data/measurement-review-new
```

Optional `--max-frames` bounds the trial. No user pixel coordinates or manual kit
selection are requested. The video hash, saved frame timestamps, calibration scope,
and replacement-track provenance are checked. The completed output includes:

- `preview.mp4`: annotated video with a persistent experimental-estimates banner.
- `estimates.jsonl`: per-frame measurements, quality labels, and rejection reasons.
- `quality.jsonl`: fitted matrices, paint/camera diagnostics, candidate foot evidence,
  sensitivity, and prepared detections. This file can be large.
- `summary.json`: fragment totals, coverage, and rejection counts.
- `manifest.json`: provenance, completion state, and the explicit unverified-ground flag.

Normal `analyze-video` output is unchanged in its strict quality requirements. The
experimental engine never writes `ground_contact_reliable: true` or claims a validated
projection. Do not merge these estimates into a trusted leaderboard without their
quality label and scope. The evidence objects are assertions from this review stage,
not a security or authenticity boundary for arbitrary externally supplied JSON.

## Review artifacts and remaining work

`evaluations/real-video-reference.json` contains the visible-point annotations.
`evaluations/real-measurement-results.json` contains the real comparison and final
trial results. Reproduce the reference check with:

```sh
.venv/bin/python scripts/evaluate_real_measurements.py data/demo-step-04/source.mp4 data/demo-step-05/full-30s data/tracking-review/revised-final/tracks.jsonl evaluations/real-video-reference.json data/reference-review-new.json
.venv/bin/python -m unittest discover -s tests -v
```

All **81 tests** passed, including recovery of known synthetic geometry, rejection
without paint, camera translation compensation, foot occlusion, strict/experimental
separation, source matching, failed-evidence export, and startup peak handling.
Generated media stay in ignored `data/real-measurement-review/`. The final 30-second
preview and recomputed summaries are in `final/`; their image-evidence audit is in
`run-004/quality.jsonl`. The final replay reused that evidence after correcting startup
peak reporting; it did not rerun or change the geometric checks.
For a shorter review, `final/review-12s.mp4` shows source time 18–30 seconds, including
the later player and official fragments. The full 30-second analysis is retained for
validation; shortening the viewing sample does not change reported coverage or totals.

Next measurement work should address foot localization/contact evidence and validate
trajectories against independent real-world reference data. Broader pitch coverage
requires other visible markings and view-specific validation. The current progress
is a measured development result, not completion of those remaining prerequisites.
