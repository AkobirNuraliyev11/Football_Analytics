# Paint screening and tracking continuity — November 8, 2026

This milestone adds an experimental image-supported calibration rejection path
and measures the real tracker's continuity without reference-assisted IDs. It does
not recover accurate automatic geometry or validate physical speeds. Step 8
expansion remains paused.

## Visible pitch markings

`analyze-video --check-pitch-paint --no-preview` checks each new or transported
calibration before projecting players. Regulation markings are projected into the
current image inside the calibration's support hull. The screen tests whether they
land near narrow, bright, low-chroma ridges with grass nearby. It requires at least
60 distinct sampled pixels, three supported marking components, and 65% aggregate
support within a resolution-scaled tolerance. These are development thresholds,
not validated confidence levels. Failed checks remove the current fit and preserve
the reason and evidence in `tracks.jsonl`. Strict telemetry is unchanged.

The screen does not use reference coordinates to judge automatic fits. The
separate reference-assisted control projects publisher geometry solely to test
the screen; it is never used to correct automatic predictions.

| Frame | Automatic paint support | Static reference control support | Automatic accepted | Control accepted |
| --- | ---: | ---: | --- | --- |
| 360 | 47.5% | 63.1% | No | No |
| 390 | 33.1% | 51.0% | No | No |
| 420 | 44.1% | 58.0% | No | No |

All three previously distorted fits are rejected. However, all three static
reference controls also fail. Potential causes include paint extraction, static
reference alignment, camera motion and annotation geometry. This experiment does
not distinguish them or establish a real-video false-rejection rate. Therefore
the screen is **opt-in**, not a new production default or a claim that calibration
is solved. Synthetic visible correct geometry passes; translated geometry, pale
unmarked turf, white screens, and insufficient support fail.

An initial broad RGB mask confused pale turf with paint and accepted two wrong
fits. A stricter chroma-only mask lost too much visible paint. The final local
contrast screen and its thresholds were developed on these same frames. There
is no held-out generalization claim. Model inference was not repeated.

## Actual tracker continuity

The existing original-detector cache contains 79 frames from indices 0–234 at
three-frame spacing, approximately 10 Hz. This fits the tracker's normal gap limit.
The tracker reads cached detections and source-image appearance with default
settings. Only after prediction are publisher player centers loaded for scoring.
There is no calibration or ground-truth ID input to the tracker.

- Matched player observations: **65 / 1,738 (3.74%)**.
- Adjacent reference links: **1,716**; both ends matched for **29**.
- Same predicted ID on both matched ends: **29 / 29**.
- Confirmed, continuity-safe, same-segment links: **15 / 1,716 (0.87%)**.
- Adjacent ID changes among the 29 matched pairs: **0**.
- Predicted track IDs associated with multiple reference players over the sequence: **2**.

The zero adjacent-change count is not reliable-tracking evidence: coverage is
extremely low and the two reused IDs show identity problems across the sequence.
Missing observations remain in denominators; gaps are never bridged. Spatial
reference associations must be within 40 native pixels and unambiguous by a
10-pixel margin. These diagnostic identity matches also have uncertainty. The
552 unmatched emitted person observations can include officials and people outside
the annotated squads, so they are not reported as 552 false positives.

This is a single-shot, same-match, original-detector diagnostic at about 10 Hz.
It does not measure the newer tiled detector's continuity or normal full-frame-rate
tracking. No additional player-model inference or preview rendering was performed.

## Next gate

Recover usable image-supported geometry for this overhead view, rather than
trying to refine the demonstrably wrong model fits into usable physical speeds.
Separate static-reference misalignment from paint-mask failures before choosing
default rejection thresholds. Then collect a short dense tiled-detection cache
and repeat the identity evaluation with a better detection baseline. A separate
recording is still needed for generalization claims; actual ground contact and
physical speed accuracy remain unvalidated.

Reproduce the two JSON reports with unused output paths:

```sh
.venv/bin/python scripts/evaluate_pitch_paint.py data/soccertrack-reference evaluations/automatic-calibration-aerial.json data/paint-check.json
.venv/bin/python scripts/evaluate_cached_tracking.py data/soccertrack-reference data/soccertrack-reference/detections-step3.jsonl data/tracking-check.json
.venv/bin/python -m unittest discover -s tests -q
```

Validation: 155 tests pass with no skips in the project environment. Added tests
cover false paint support, geometric displacement, missing tracking denominators,
ID swaps, unsafe segments, gaps, ambiguous matches, and pipeline rejection before
player projection. Tests do not certify real-video measurement accuracy.
