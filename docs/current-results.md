# Complete results review — November 11, 2026

We are in **Step 9: backend engineering**. The first local API milestone is implemented:
video upload, persistent SQLite jobs, a separate analysis worker, frame progress,
result summaries and completed artifact downloads. Last full suite: **182 passing tests**.
Next engineering work is telemetry queries and cancellation/retry, followed by the Step 10 dashboard.
Steps 1–8 have core implementations, but real physical measurement validation remains open.

## Watch the outputs

These files are available in this local working copy. Large media and raw data are
excluded from GitHub; committed evaluation summaries below remain available there.
The user requested this review; the 12-second preview reuses saved analysis, with no fresh model inference.

- [12-second real-video tracking and classification preview](../data/results-review/tracking-12s.mp4).
- [Tracking still at 5 seconds](../data/results-review/tracking-still.jpg).
- [Second real-video tracking run, 6 seconds](../data/continuity-review/second-analysis/preview.mp4).
- [Experimental real-video radar, 6 seconds](../data/continuity-review/second-tactics/preview.mp4).
- [Experimental team B occupancy heatmap](../data/continuity-review/second-tactics/heatmap-65fd6baacf3cce9a3b7d.png).
- [Synthetic speed/distance chart](../data/results-review/synthetic/telemetry-demo.png).
- [Synthetic radar demonstration, 8 seconds](../data/results-review/synthetic/tactics/preview.mp4).
- [Synthetic team occupancy heatmap](../data/results-review/synthetic/tactics/heatmap-6a1b4e0b2e6d91f795c3.png).
- [Synthetic candidate highlight viewer](../data/step08-browser-check/clips/index.html).

The tracking preview uses red/white boxes for arbitrary teams A/B, cyan for officials,
and yellow for the ball/goalkeeper when detected. IDs refer to local tracks, not verified
athlete identities. Green pitch points are estimated geometry. `-- km/h` means speed
is unavailable. A visible box or label is a prediction and may be wrong.

## Every component and its current result

| Part | Implemented output | What the evidence establishes |
|---|---|---|
| Video ingestion | Automatic resolution, timing, frame decoding, shot records | Both broadcast inputs are 1920 × 1080 at 25 fps; 750 and 150 frames were analyzed |
| Person/ball detection | Boxes, confidence, image anchors | Real outputs exist; misses and false detections remain |
| Tracking | Local IDs, association and continuity flags | Real tracks exist; IDs can fragment and cannot yet reliably follow every player |
| Classification | Team A/B, outfield, official, goalkeeper, unknown | Small development kit checks improved; no general role/identity accuracy guarantee |
| Pitch calibration | Automatic landmarks/homography, pitch-paint and camera checks | Overhead geometry improved; pitch size still assumes configured 105 × 68 m |
| Foot/ground contact | Experimental shoe/ankle candidates and exclusion reasons | Real contact is not independently verified; pose trial was not promoted |
| Speed and distance | Time-aware, gated per-fragment calculations | Correct on known-motion synthetic fixtures; strict real speeds/distances unavailable |
| Sprints | Threshold/duration-based sustained sprint records | Synthetic positive case works; no trusted real sprint count |
| Radar | Current eligible pitch positions, gaps left empty | Synthetic demonstration works; real experimental positions are sparse |
| Heatmaps | Time-weighted observed occupancy, team/local-track PNGs | Sparse experimental output only; not possession or full-match coverage |
| Events | Sprint and opposing-team duel candidates | Conditional candidates, not confirmed tackles, possession changes or counterattacks |
| Highlight clips | Padded shot-bounded extraction, overlays, viewer/playlist | Synthetic playback verified; strict real analyses produced no eligible clips |
| Backend | Authenticated upload, durable queue, worker, progress, downloads | Integration tests pass; local foundation, not a public deployed service |
| Dashboard/deployment | Planned next stages | Not implemented yet |

## Real broadcast output inventory

Counts below describe model output, not ground truth. A person observation is one
person in one frame; repeated observations and fragmented IDs are not unique athletes.

| Saved output | First clip (30 s) | Second clip (first 6 s) |
|---|---:|---:|
| Frames | 750 | 150 |
| Person observations | 17,460 | 3,606 |
| Distinct local person IDs | 44 | 33 |
| Ball observations | 461 | 143 |
| Frames with unvalidated pitch fit | 731 | 150 |
| Predicted role: goalkeeper | 0 | 23 |
| Predicted role: official | 2,244 | 424 |
| Predicted role: outfield | 14,959 | 3,069 |
| Predicted role: unknown | 257 | 90 |
| Predicted team: A | 6,847 | 1,133 |
| Predicted team: B | 7,458 | 1,658 |
| Predicted team: unknown | 3,155 | 815 |

Both strict summaries contain **zero eligible measured observations** and no physical
measurement fragments. Therefore real top speed, player distance totals and sprint
counts are **unavailable**, not zero. The absence of eligible sprint events does not
mean that nobody sprinted in the footage.

## Tracking and classification evaluation

- Aerial 3-second diagnostic: tiled detection/tracking matched **330/682 reference
  observations (48.4%)**, compared with **31/682 (4.5%)** before tiling.
- Eligible same-ID adjacent links: **206/660 (31.2%)**; one adjacent ID change among
  matched links. Longest eligible continuity: **1.80 seconds**, and **zero players
  reached 2 seconds**. This is one aerial shot sampled near 10 Hz, not a full-match benchmark.
- Visible kit review, first clip: **88 correct, 1 wrong, 2 unknown** after the change
  versus 88 correct, 3 wrong, 0 unknown before it.
- Visible kit review, second clip: **18 correct, 1 wrong** versus 19 unknown before.
  These are small assistant-reviewed development samples, not independent held-out accuracy.

## Calibration and experimental real measurements

Automatic overhead geometry passed the visible-paint screen on **38/38 sampled frames**.
Stationary-paint checks were available for **23/30 adjacent pairs**; the median pair's
90th-percentile displacement was about **0.060 m**, maximum about **0.087 m**.
These concern stationary paint consistency, not athlete speed accuracy. Six sampled
broadcast negative frames were rejected by the overhead method. No independent
match or real ground-contact validation closes the physical measurement problem.

The separate experimental continuity policy increased published samples from
83 to **367/17,460 (2.10%)** on the first clip and from 0 to **87/3,606 (2.41%)** on
the second. Those are sparse estimates and must not become trusted full-match totals.

For transparency, these are all five retained experimental fragments in the second
clip. They are **unvalidated estimates**, not confirmed player statistics. Fragment
distance includes eligible warmup observations; radar occupancy starts after maturity.

| Local ID | Predicted role | Fragment time (s) | Estimated distance (m) | Estimated peak (km/h) | Fragment sprint candidates |
|---|---|---|---:|---:|---:|
| 1 | outfield | 1.80–2.44 | 1.87 | 12.03 | 0 |
| 1 | outfield | 2.60–3.92 | 3.68 | 12.57 | 0 |
| 3 | official | 3.40–5.04 | 4.26 | 11.95 | 0 |
| 17 | outfield | 4.12–5.08 | 3.52 | 15.82 | 0 |
| 4 | outfield | 3.92–5.24 | 4.14 | 14.94 | 0 |

These short fragment counts cannot determine the players' sprint totals. The experimental
team B heatmap contains just **2.16 person-seconds**, summed over available intervals.

## Synthetic speed, distance and sprint results

These values come from simulated motion with exact positions, not the football video.

| Simulated track | Speed | Distance over 8 s | Sprints |
|---|---:|---:|---:|
| 1 | 10.8 km/h | 24 m | 0 |
| 2 | 21.6 km/h | 48 m | 1 |

Sprint threshold: 18 km/h, sustained for at least 1 second. The sprint is still active
when the fixture ends, so its end is marked truncated. Measurements become visible
after a two-second maturity period. A short ghost track is excluded; another track
with unverified contact is withheld. These checks validate the calculation logic.

## Events, highlights and backend

Strict replay of the two real analyses (750 and 150 frames) returned
`status: unavailable`, zero emitted events and zero planned clips. This is a quality
abstention, not a real event-accuracy result. Two synthetic candidate clips played
to completion in the browser (3.34 s each). Duel-candidate rules are tested, but
there are no validated real duel/tackle/counterattack results to display.

The backend milestone is commit `4c5d119`. The 182-test suite included six backend
tests for upload through the actual pipeline with a synthetic detector, progress,
result availability, ranges, auth/CORS, invalid uploads, source tampering, failure,
restart persistence and worker exclusion. [Backend setup and limits](step-09-backend.md).

## Open all raw outputs

### First broadcast analysis

- [manifest.json](../data/continuity-review/first-analysis/manifest.json)
- [tracks.jsonl](../data/continuity-review/first-analysis/tracks.jsonl)
- [calibrations.jsonl](../data/continuity-review/first-analysis/calibrations.jsonl)
- [telemetry.jsonl](../data/continuity-review/first-analysis/telemetry.jsonl)
- [telemetry-summary.json](../data/continuity-review/first-analysis/telemetry-summary.json)

### Second broadcast analysis

- [manifest.json](../data/continuity-review/second-analysis/manifest.json)
- [tracks.jsonl](../data/continuity-review/second-analysis/tracks.jsonl)
- [calibrations.jsonl](../data/continuity-review/second-analysis/calibrations.jsonl)
- [telemetry.jsonl](../data/continuity-review/second-analysis/telemetry.jsonl)
- [telemetry-summary.json](../data/continuity-review/second-analysis/telemetry-summary.json)

### Other detailed outputs

- [Experimental occupancy, all fragments and coverage](../data/continuity-review/second-tactics/occupancy.json)
- [Experimental radar records](../data/continuity-review/second-tactics/radar.jsonl)
- [Synthetic telemetry summary](../data/results-review/synthetic/results/telemetry-summary.json)
- [Synthetic telemetry records](../data/results-review/synthetic/results/telemetry.jsonl)
- [Synthetic occupancy](../data/results-review/synthetic/tactics/occupancy.json)
- [First real highlight plan](../data/step08-first-highlight-plan.json)
- [Second real highlight plan](../data/step08-second-highlight-plan.json)
- [Synthetic highlight playlist](../data/step08-browser-check/clips/playlist.json)

## Complete committed evaluation archive

These files include historical trials, rejected approaches, reference annotations,
and later corrections. They are not all measurements from the current version.
For sensor/detection comparisons, use the `*-corrected.json` reports and the
[reference methodology correction](reference-methodology-correction.md); the old
GNSS comparisons must not be interpreted as physical speed ground truth.

- [anchor-sequence-reference](../evaluations/anchor-sequence-reference.json)
- [anchor-sequence-results](../evaluations/anchor-sequence-results.json)
- [automatic-calibration-aerial](../evaluations/automatic-calibration-aerial.json)
- [box-final-reference-audited](../evaluations/box-final-reference-audited.json)
- [box-final-reference](../evaluations/box-final-reference.json)
- [box-final-validation-audited](../evaluations/box-final-validation-audited.json)
- [box-final-validation](../evaluations/box-final-validation.json)
- [box-junction-development](../evaluations/box-junction-development.json)
- [box-junction-holdout](../evaluations/box-junction-holdout.json)
- [box-junction-recheck](../evaluations/box-junction-recheck.json)
- [box-junction-reference](../evaluations/box-junction-reference.json)
- [current-output-inventory](../evaluations/current-output-inventory.json)
- [foot-reference](../evaluations/foot-reference.json)
- [foot-review-results](../evaluations/foot-review-results.json)
- [identity-maturity-real](../evaluations/identity-maturity-real.json)
- [identity-maturity-synthetic](../evaluations/identity-maturity-synthetic.json)
- [kit-review](../evaluations/kit-review.json)
- [normal-tiles-trial](../evaluations/normal-tiles-trial.json)
- [overhead-broadcast-abstention](../evaluations/overhead-broadcast-abstention.json)
- [overhead-geometry](../evaluations/overhead-geometry.json)
- [overhead-pipeline-smoke](../evaluations/overhead-pipeline-smoke.json)
- [penalty-geometry-results](../evaluations/penalty-geometry-results.json)
- [penalty-reference](../evaluations/penalty-reference.json)
- [pitch-paint-aerial](../evaluations/pitch-paint-aerial.json)
- [real-measurement-results](../evaluations/real-measurement-results.json)
- [real-video-reference](../evaluations/real-video-reference.json)
- [reliability-results](../evaluations/reliability-results.json)
- [second-kit-review](../evaluations/second-kit-review.json)
- [sensor-baseline](../evaluations/sensor-baseline.json)
- [sensor-coordinate-check](../evaluations/sensor-coordinate-check.json)
- [sensor-original-nine](../evaluations/sensor-original-nine.json)
- [sensor-tiled-nine](../evaluations/sensor-tiled-nine.json)
- [small-tiles-trial](../evaluations/small-tiles-trial.json)
- [soccertrack-sample](../evaluations/soccertrack-sample.json)
- [speed-sensitivity-first](../evaluations/speed-sensitivity-first.json)
- [speed-sensitivity-second](../evaluations/speed-sensitivity-second.json)
- [step06-results](../evaluations/step06-results.json)
- [step07-results](../evaluations/step07-results.json)
- [step08-highlight-planning](../evaluations/step08-highlight-planning.json)
- [step08-strict-replay](../evaluations/step08-strict-replay.json)
- [tracking-original-dense](../evaluations/tracking-original-dense.json)
- [tracking-original-three-seconds](../evaluations/tracking-original-three-seconds.json)
- [tracking-tiled-three-seconds](../evaluations/tracking-tiled-three-seconds.json)
- [video-reference-original-nine-corrected](../evaluations/video-reference-original-nine-corrected.json)
- [video-reference-original-nine](../evaluations/video-reference-original-nine.json)
- [video-reference-tiled-nine-corrected](../evaluations/video-reference-tiled-nine-corrected.json)
- [video-reference-tiled-nine](../evaluations/video-reference-tiled-nine.json)
