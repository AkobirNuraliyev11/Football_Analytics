# Continuation prompt for ChatGPT Astra or another coding assistant

You are continuing my Football Analytics project. Inspect the actual repository,
diagnose the outstanding measurement problem, implement improvements, test them,
and push completed milestones to GitHub. Do not merely propose work you can perform.

Repository: https://github.com/AkobirNuraliyev11/Football_Analytics

Original Step 7 implementation:
`8af5f5943d1a5028e39b76e3dbb14baeadc0c1f9` — gated tactical radar and occupancy heatmaps.
Current work adds penalty-area junction recovery and the Step 8 data-only event foundation.
Check for newer commits and preserve existing changes. The original local project
was deleted and restored from GitHub on November 2, 2026. The exact original videos
and pinned player/pitch models were subsequently restored from their public sources.
Use `scripts/restore_samples.py` to recover videos in a new clone. Read `START_HERE.md`
and check `data/continuity-review/` for regenerated analysis and newer comparisons.

## Latest completed comparison

Both original sources were recovered and verified. On identical saved positions,
separating identity maturity from the measurement window increased experimental
coverage from 83 to 367 samples on the 30-second clip and from zero to 87 on the
six-second clip. The 83 shared speed and distance readings agreed exactly.
See `evaluations/identity-maturity-real.json` for denominators and rejection counts.
The penalty-area junction experiment now has a small separate-clip landmark check.
Read `docs/penalty-area-trial.md` for the annotation audit, coverage, and limitations.
Temporal camera stability and athlete ground contact remain unvalidated in that region. Keep future investigations
data-only unless the user asks for a clip.

## Objective and implemented scope

Build an automatic single-camera football analytics platform: upload a video, detect
and track athletes/officials/ball, classify teams and roles, calibrate pitch geometry,
estimate physical movement, show radar and occupancy heatmaps, then eventually provide
events, highlights, an API, and a dashboard. The user should not have to supply video
resolution or pixel coordinates. Pitch dimensions currently use an explicit configurable
105 × 68 m assumption, not a measurement inferred from footage.

Steps 1–7 are implemented: foundation, timestamp-aware ingestion, calibration, detection
and tracking, classification, gated telemetry, and tactical visualization. Step 8 now includes strict data-only sprint and duel candidate records. Read
`docs/step-08-events.md`. Backend, dashboard, and highlight extraction are not implemented. The user has requested progression toward Step 8 after addressing Step 7 problems.
Keep event engineering isolated from unvalidated real-video geometry. Implementation does not mean real-video physical
measurement accuracy has been demonstrated.

## Immediate task: resolve reference disagreement before more Step 8 work

Read `docs/sensor-comparison.md` first. A same-frame tiled-detection comparison
improved matching from 16/198 to 121/198 observations. All 142 tests passed.
The sensor benchmark is implemented but diagnostic: reference video annotations
and aligned GNSS already disagree by about 2.95 m median. The 0.85-second clock
offset is inferred on setup data, not independently verified. Do not tune our model
to this unexplained mismatch or claim validated speed from the 24 usable intervals.
Step 8 expansion is paused. No previews. Keep runs bounded and reuse cached
detections to avoid unnecessary cost.

## Prior measurement-sensitivity work

Read `docs/measurement-sensitivity.md` first. Pixel-speed sensitivity is implemented
and tested. SoccerTrack version 6 reference files are under
`data/soccertrack-reference/`, with a committed acquisition manifest. Resolve its
duplicate timestamps and GNSS/video alignment before reporting any speed errors.
Do not silently turn sensor conflicts into ground truth. No generated clips.

## Real-video measurement continuity background

Too few consecutive observations pass geometry, tracking, visible-feet, camera-motion,
displacement, and maturity checks. Diagnose the actual bottlenecks and improve useful
continuous measurement coverage while evaluating accuracy. Do not populate the radar
with stale, invented, or silently unverified positions to make coverage appear better.

Existing work:

1. Tracking/classification reliability pass: ambiguous associations carry continuity
   warnings; conflicting kit classifications can remain unknown; kit thresholds adapt.
2. Experimental measurements: visible midfield paint refinement, held-out paint-region
   checks, camera-motion checks, foot screening, and body-height discontinuity checks.
   Estimates are restricted to the checked center-circle region. Ground contact remains
   unverified; results are labeled `experimental_estimate`.
3. Optional pose-foot trials: pinned YOLO11n-pose on crops, confident leg joints,
   shoe-component extraction, a heuristic vertical-motion veto, and an optional current
   ankle plus recently observed shoe-offset proxy. Visible-shoe localization improved
   on a tiny paired sample, but continuous coverage got worse. Neither variant produced
   mature metric fragments in the two six-second trials. Neither became the default.

Recorded baseline:

- First clip: 30 seconds, 1920×1080, 25 fps. 83 eligible experimental person samples
  out of 17,460 (about 0.475%), four mature movement fragments, and 3.16 post-warmup
  person-seconds in Step 7 occupancy. Strict validated mode produces none.
- Second match: six seconds / 150 frames analyzed in the latest comparison; no mature
  experimental fragments or usable heatmap occupancy.
- Both clips informed development. They are not independent held-out benchmarks.
- No independently measured real-video meter trajectories were available. The scorer
  exists, but its accuracy tests use analytic fixtures. Do not claim real speed accuracy.
- At the implementation milestone, 109 tests passed. Re-run tests in your environment
  and report any skips instead of assuming all optional dependencies are available.

## Files to read first

`README.md`, `THIRD_PARTY.md`, and:

- `docs/step-06-telemetry.md`
- `docs/tracking-reliability-review.md`
- `docs/real-video-measurements.md`
- `docs/foot-position-review.md`
- `docs/step-07-tactical-visualization.md`
- `evaluations/foot-review-results.json`
- `evaluations/foot-reference.json`
- `evaluations/step07-results.json`

Key modules: `tracking.py`, `classification.py`, `measurement_quality.py`,
`real_measurements.py`, `feet.py`, `foot_review.py`, `telemetry.py`, `tactical.py`,
`tactical_io.py`, and `tactical_render.py` under `football_intelligence/`.

Evaluation tools: `scripts/evaluate_feet.py`, `scripts/evaluate_trajectories.py`,
and `scripts/validate_step07.py`.

## Data needed to reproduce the old experiments

These paths describe the ORIGINAL workspace and may be absent after deletion:

- `data/demo-step-04/source.mp4`
- `data/demo-step-05/full-30s/`
- `data/tracking-review/revised-final/tracks.jsonl`
- `data/real-measurement-review/run-004/`
- `data/tracking-review/second-source.mp4`
- `data/foot-review/second-analysis/`
- `data/foot-review/second-geometry/`
- `data/foot-review/first-trial/` and `second-trial/`
- `data/foot-review/first-proxy-trial/` and `second-proxy-trial/`
- `data/step-07/known-motion/`, `first-experimental/`, `second-experimental/`, `first-strict/`

Original source SHA-256 values:

- First: `43d342c78fbb40e522f48ab378fbee83b5b880d35c056836e0d493ec2b15ee51`
- Second: `7788719b32b944e42d8f1024fb4802f681bc2053d6301218a5bff6705b549f96`

GitHub contains code, documentation, and evaluation summaries, not these large files.
If sources cannot be recovered, ask once for the minimum source videos required and
continue useful source-code work meanwhile. New footage needs a new baseline and must
not be compared as if it were the identical old test. Models can be downloaded again.

## Investigation and validation

1. Reproduce the baseline if data are available.
2. Quantify failures by gate over time: geometry, camera motion, foot localization,
   occlusion, association ambiguity, classification changes, displacement, maturation.
3. Inspect sequences rather than isolated frames and target the dominant failure.
4. Keep alternate methods testable separately until improvement is demonstrated.
5. Compare baseline/candidate on identical footage and timestamps. Measure available
   samples, continuous durations, fragment lengths, identity switches, and outliers.
6. Evaluate position/speed accuracy against independent reference measurements when
   available. Missing predictions must stay in the coverage denominator.
7. Use a held-out clip or segment when possible. Threshold changes may be experiments,
   but increased coverage alone is not evidence of increased accuracy.
8. Report remaining limits honestly. Do not silently equate shoe/ankle confidence with
   ground contact, or project airborne feet as validated ground positions.

## Step 7 contracts to preserve

- Radar shows current mature eligible samples; gaps stay empty.
- No stale-dot persistence or unsupported interpolation through gaps.
- Occupancy weights timestamps, not frame counts, and never bridges measurement
  fragments, shots, or coordinate-reference changes.
- Gaussian smoothing conserves person-seconds, including pitch edges.
- Team maps exclude officials and unknown teams. Individual IDs are local tracks.
- Cross-shot physical-end identity and attacking direction remain unresolved.
- Occupancy is not possession or pitch control.
- Observed, inferred, experimental, and validated-input evidence remain distinguishable.

## Working preferences

Use normal judgment and proceed autonomously. Commit and push completed milestones.
Keep updates brief. Do not show intermediate generated videos; any final review preview
should be 12–15 seconds. Do not generate clips without a new request. If your environment cannot run/edit/push,
say so clearly instead of implying those operations occurred.

Begin by checking the restored repository and data availability, then investigate the
continuity problem. Use `python3 -m unittest discover -s tests -v` and inspect CLI help
for `analyze-video`, `review-measurements`, `review-feet`, and `build-tactics`.
