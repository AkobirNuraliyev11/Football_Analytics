# Foot-position and second-clip review

This is a development follow-up to Step 6, not Step 7. The goal was to replace the
box-bottom anchor with better foot evidence and test whether usable movement
segments became longer. The outcome is mixed: localization improves on the small
paired visible-shoe sample, but continuous measurement coverage gets worse. The
existing box-anchor review remains the default; pose-guided feet are an optional
diagnostic mode. Strict validated telemetry remains unavailable for these clips.

## Implementation

`feet.py` uses the pinned YOLO11n-pose model on padded player crops. Pose detections
must overlap the tracked box sufficiently; ambiguous matches are rejected. Both hips,
knees, and ankles require confidence of at least 0.5 and plausible body geometry.
The model predicts ankle joints, not sole contact. A small non-grass image component
near each ankle supplies a visible-shoe candidate. Components merging into a pitch
line, crop border, or surrounding region are rejected. The lower visible shoe supplies
the experimental anchor. This can change with gait; it is not a verified body-center
trajectory and may be noisier than a box midpoint.

A temporal veto compares hips and ankles with their camera-compensated previous
locations. Rapid simultaneous upward image motion triggers a 0.3-second cooldown,
labeled `possible_airborne_or_vertical_motion`. Missing poses cannot erase an active
cooldown; cuts, long gaps, and changed continuity segments reset motion comparisons.
This is **not a validated jump detector**: rapid movement away from the camera can
trigger it, and some real jumps will be missed. No labeled real airborne examples
were used in this pass. Synthetic tests check the veto and camera compensation.

The foot anchor still passes the prior occlusion, clipping, visible-grass, body-height,
checked-midfield, pixel-sensitivity, tracking, raw-displacement, and two-second maturity
gates. No missing pose is silently replaced by a box anchor. Ground contact remains
unverified. These choices deliberately expose unavailable evidence rather than
interpolating invented feet through occlusion.

A second, explicit experimental option (`--allow-ankle-proxy`) was also tested. It
uses the current high-confidence ankle plus a shoe offset learned from at least
three visible examples within the preceding half-second. Unstable offsets, low
joint confidence, changed track segments, gaps, and expired samples block this
option. It never carries a stale ankle position forward. Its proxy is labeled
`current_ankle_recent_shoe_offset`, distinct from a visible shoe. Candidate availability
increased to 1,795 observations in the first clip and 1,108 in the second, but **neither
trial produced a mature metric fragment**. This option is off by default and is not
a demonstrated solution to continuity. Fourteen observations received the possible
vertical-motion veto in the first proxy trial; without real jump labels, that is a
diagnostic count, not detection accuracy.

`foot_review.py` reuses the exact saved geometric evidence and same input frames for
both methods. This isolates the anchor comparison from fresh calibration changes.
It checks source/track hashes, frame timing, input stability, and completed geometry
status. Quality audits include keypoints, foot statuses, both telemetry results,
rejection reasons, model provenance, and the explicit experimental grade.

## What was tested

The first clip was reviewed at source time **19.52–25.48 seconds**, 150 frames (six
seconds of playback). The second clip's original two-second analysis was extended to
**150 frames / six seconds** using the current detection and classification pipeline.
The second clip is a different match, but both clips informed development, so neither
is an independent held-out benchmark.

| Same-frame comparison | Box anchor | Pose-guided shoe |
|---|---:|---:|
| First clip: published person observations after warmup | 69 | 0 |
| First clip: mature continuous fragments | 2 | 0 |
| Second clip: published person observations after warmup | 0 | 0 |
| Second clip: mature continuous fragments | 0 | 0 |

The pose method found 1,502 shoe candidates among 3,460 person observations in the
first trial and 710 among 3,606 in the second. Many lie outside the checked midfield
area or fail another gate. Frequent missing/separation failures break continuity;
finding a shoe in one frame is insufficient for a reliable trajectory. No claim of
increased measurement coverage, athlete identification, or sprint accuracy is made.

## Visible-point comparison

Assistant-reviewed source-frame crops supply approximate lowest-visible-shoe points,
with roughly three-pixel annotation uncertainty. Ambiguous dark shoes/shadows and a
shoe merged into a pitch marking were excluded with reasons recorded. Alternative
shoe points are permitted when both feet have similar vertical positions. The metric
is distance to a visible shoe, **not athlete-center position or metric speed accuracy**.
A box midpoint is a different position proxy and can intentionally lie between feet.

| Review frame | Pose availability | Box mean error on paired points | Pose mean error on paired points |
|---|---:|---:|---:|
| First clip, frame 75 | 6 of 9 | 9.94 px | 3.30 px |
| Second clip, frame 49 | 4 of 8 | 4.29 px | 2.10 px |

Paired errors use exactly the same available observations. Missing pose points are
reported explicitly, not counted as correct or omitted from the availability result.
The second improvement is within annotation uncertainty. The tiny development sample
does not demonstrate generalized foot accuracy, foot/ground contact, or better speeds.
References and full per-point outputs are committed in `evaluations/foot-reference.json`
and `evaluations/foot-review-results.json`.

## Use the optional review

Existing video analysis and measurement commands keep their behavior. To try this
additional review, explicitly download its optional model once:

```sh
.venv/bin/python -m football_intelligence download-pose-model
.venv/bin/python -m football_intelligence review-feet /path/to/match.mp4 --geometry data/my-match/measurement-review --tracks data/my-match/analysis/tracks.jsonl --output data/my-match/foot-review --start-s 0 --max-frames 150
```

`--geometry` must point to a completed `review-measurements` run containing
`quality.jsonl`. `--tracks` must exactly match that run's recorded track hash. A custom
path to the same pinned pose model can be supplied with `--pose-model`. All inference
is local, using existing detection dependencies. The output directory must be new.

Outputs are `feet.jsonl`, `comparison.json`, `preview.mp4`, and a completion manifest.
The preview marks ankles cyan and candidate shoes gold; visible points do not imply
valid speed measurements. `comparison.json` contains both methods' coverage and
fragments. Model weights and generated videos are excluded from Git.

Reproduce the reference-point check with the script's source, tracks, reference,
case (`first` or `second`), model path, and new output path:

```sh
.venv/bin/python scripts/evaluate_feet.py data/demo-step-04/source.mp4 data/tracking-review/revised-final/tracks.jsonl evaluations/foot-reference.json first data/models/yolo11n-pose.pt data/foot-reference-new.json
.venv/bin/python -m unittest discover -s tests -v
```

All **92 tests** passed. New tests cover shoe isolation, merged pitch lines, missing
ankles, malformed poses, camera-compensated vertical motion, cooldown persistence,
camera translation, model hash checks, output publishing, and empty review failure.
They also cover proxy expiration and its confidence/identity safeguards.
The real trial is summarized in a **12-second review** at
`data/foot-review/review-12s.mp4`: six seconds from each match, clearly labeled as a
foot-localization experiment rather than a speed demonstration.

## Decision

Retain the original measurement method as the default. The optional pose tool and its
audits are useful for identifying failures, but promoting it would discard the few
continuous estimates currently available. Further work needs stronger small-player
foot/contact evidence and independent trajectory labels; simply relaxing confidence
or maturity thresholds would not resolve those problems. Full-match reliable telemetry
and Step 7 remain unfinished.
