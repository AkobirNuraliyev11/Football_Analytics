# Step 7 closure assessment — November 8, 2026

**November 10 authorization update:** Step 7 accuracy validation remains open.
The user authorized Step 8 software engineering to proceed separately; strict
measurement/event gates remain unchanged. The pause instructions below describe
the November 8 assessment and are superseded by this authorization.

This is the Step 7 validation record; it supersedes earlier benchmark counts.
Implementation tests passing is not evidence that athlete measurements are accurate.

## Completed fixes

### Automatic full-pitch overhead geometry

The automatic detector now first attempts an image-only full-pitch solution for
roughly axis-aligned overhead views with visible white markings. It proposes long
boundary-line combinations, selects candidates using midfield paint, refines the
four boundaries at native resolution, and screens against internal markings.
At most 128 plausible perimeter candidates and eight native-resolution candidates
are considered. No publisher coordinates or manual pixel clicks enter prediction.
All internal marking checks participate in hypothesis selection/screening and are
not claimed as independent physical validation.

A narrow chroma condition is necessary: local brightness alone also selects pale
turf texture. A regression test now covers bright, textured grass, as well as
an extra white rectangle outside the actual pitch. Blank, incomplete and
boundary-only synthetic views abstain. The six real broadcast frames checked also
abstain, leaving those views on the existing semantic-model candidate path.

On the existing aerial recording, **38/38 sampled frames pass image checks**.
Frames include a dense 31-frame sequence and seven later samples. Three later
frames informed initial development; the remaining frames are within-recording
checks, not an independent match. Temporal checks use internal paint features,
forward/backward optical flow and a spatially spread motion consensus. **23/30**
adjacent checks were available; the other seven remain unavailable. Across the
available checks, median pairwise p90 stationary-field displacement is **0.060 m**,
and the maximum pairwise p90 is **0.087 m**. These test camera consistency, not
athlete speed, physical dimensions or ground contact.

Production camera updates re-detect overhead boundaries in the current frame;
failed updates clear the mapping. Geometry evidence is stored in the calibration
record. Pitch size remains the explicit configured 105 × 68 m assumption. Image
left/right does not establish physical pitch-end identity or attacking direction.

An actual one-frame, data-only pipeline replay completed with this calibration.
It produced one fit and correctly withheld physical telemetry. No preview file
or encoder was created. See `evaluations/overhead-pipeline-smoke.json`.

### Corrected detection scorer

The detection-only video-reference scorer previously solved a forced assignment
and then discarded distant matches. Distant clutter could steal valid nearby
matches. Explicit unmatched choices now participate in the assignment, and an
adversarial regression test reproduces the original failure. The tracking scorer
already had unmatched choices and was unaffected by this bug.

Corrected nine-frame component comparison:

| Metric | Original detector | Tiled detector |
| --- | ---: | ---: |
| Matched observations / 198 | 26 | 138 |
| Complete reference-associated intervals / 66 | 1 | 30 |
| Median center discrepancy (shared reference geometry) | 0.264 m | 0.230 m |
| Mean center net-speed discrepancy | 0.276 km/h (one interval) | 0.459 km/h |

The files ending in `-corrected.json` supersede the old nine-frame reports. These
remain component scores with reference-associated identities and shared geometry,
not physical accuracy or end-to-end tracker scores. Available subsets differ.

### Dense tracking comparison completed

The new cache contains frames 0–90 at three-frame spacing, about 10 Hz and three
seconds. The original and tiled detectors were scored on exactly the same frames.
The real tracker ran without reference positions or IDs. Missing observations
and missing adjacent links remain in the denominators.

| Metric | Original detector + tracker | Tiled detector + tracker |
| --- | ---: | ---: |
| Matched observations / 682 | 31 (4.55%) | 330 (48.39%) |
| Eligible consecutive links / 660 | 6 (0.91%) | 206 (31.21%) |
| Adjacent ID changes on matched pairs | 0 | 1 |
| IDs associated with multiple reference players | 1 | 0 |
| Longest eligible continuity | 0.300 s | 1.802 s |
| Reference players with two-second eligible continuity | 0 | 0 |

This is a material improvement, but **tracking coverage still fails the intended
continuous-measurement use case**. A zero reuse count on this tiny sample does
not prove general identity accuracy. Unknown/nonparticipant observations are not
automatically counted as false detections. Team/role accuracy was not evaluated
by this replay; the historical cache did not retain role predictions.

A three-frame test of smaller 640-pixel tiles matched **22/66** reference
observations versus **37/66** for the existing 1280-pixel tiles. It was rejected;
there is no smaller-tile default change. The dense 31-frame run took about 18.5
minutes on the current CPU environment. The small-tile trial took about 11.2
minutes for three frames. Runs overlapped with other work, so these are recorded
wall times, not a controlled throughput comparison. No further expensive tiling
sweep is justified by these results.

## Remaining blockers and closure rules

| Area | Current evidence | Requirement before calling it resolved |
| --- | --- | --- |
| Coverage and identity | 48.39% observation coverage; no two-second eligible trajectory in the dense trial | Improve the detector on representative footage and demonstrate useful uninterrupted coverage with identity-error reporting on separate sequences. Do not fill gaps with invented observations. |
| Physical speed and contact | Image-plane agreement and camera consistency only | Use synchronized, independently measured trajectories/contact evidence with stated uncertainty; report physical errors and coverage. Current source comparisons cannot certify these claims. |
| Generalization | One aerial recording plus two broadcast development recordings | Evaluate a separate recording/camera setup before claiming general smartphone or broadcast reliability. |

Existing supported-scope limits remain explicit: local track IDs, arbitrary team
A/B labels, unknown classifications when evidence conflicts, and unverified
cross-shot physical-end identity. Occluded feet, airborne players, missing paint
and unsupported camera views must yield unavailable measurements. Correct
abstention is the acceptance rule for those inputs.

**Do not mark Step 7 complete, enable strict speeds, or proceed with a real-event
accuracy claim using these results.** Further code tuning on these same frames
cannot establish independent physical accuracy. The next substantive work is a
representative detector-training/evaluation set plus suitable measurement-reference
data, not another calibration-offset or smaller-tile sweep. The authors'
[SoccerTrack v2 dataset](https://atomscott.github.io/SoccerTrack-v2/) is one candidate
for additional match/role/tracking annotations; no new dataset was downloaded or
treated as a surveyed speed reference during this work.

## Reproduction and artifacts

No generated review clip is part of this milestone. Raw videos, weights and dense
caches remain ignored locally. Source/cache/reference hashes are in the JSON reports.

```sh
.venv/bin/python scripts/evaluate_overhead_geometry.py data/soccertrack-reference data/new-geometry-report.json data/new-geometry-cache.jsonl
.venv/bin/python scripts/evaluate_cached_tracking.py data/soccertrack-reference data/soccertrack-reference/detections-tiled-dense.jsonl data/new-tracking-report.json --end-frame 90
.venv/bin/python -m unittest discover -s tests -q
```

Use unused output paths. The overhead geometry audit does not run neural models.
The tracking audit reuses completed caches. Regenerating the dense detection cache
does require expensive model inference; do not repeat it when the hash-verified
cache is already present.

Validation: **163 tests pass, no skips**. New tests cover automatic recovery under
perspective, moving-camera re-detection, failure without current paint, surrounding
white rectangles, textured pale turf, missing-link continuity, and the forced
assignment regression. The full pipeline data-only smoke check also passed.
