# Automatic calibration audit — November 8, 2026

Step 7 remains under validation; Step 8 expansion remains paused. The next
identified blocker is incorrect automatic pitch geometry on the aerial sample.
This supersedes the assumption that detection-anchor agreement establishes a
usable automatic measurement pipeline.

The pinned pitch model ran on frames 360, 390 and 420 of the recovered SoccerTrack
video. Predictions used images and the configured 105 × 68 m pitch only. Publisher
coordinates were read after all three predictions. No manual pixels, publisher
homography or athlete identities were supplied to prediction. No clip was rendered.
These are additional frames from the same match, not an independent test match.

| Frame | Internal fit RMSE (m) | Reference points within predicted support / 65 | Best symmetry median discrepancy (m) | Median pair-distance discrepancy (m) |
| --- | ---: | ---: | ---: | ---: |
| 360 | 0.232 | 23 | 16.438 | 12.858 |
| 390 | 0.272 | 7 | 35.618 | 19.608 |
| 420 | 0.357 | 15 | 10.601 | 10.140 |

All three fits passed existing internal consistency checks. Those checks measure
agreement among the model's own predicted landmarks. They cannot establish that
the semantic landmark assignments are correct.

The symmetry diagnostic compares identity, length reversal, width reversal and
180-degree rotation. Even the best is poor. Pair-distance disagreement also remains
large; it does not depend on pitch-end orientation. Neither diagnostic alters
production predictions. Each frame has a different supported subset. These numbers
are disagreement with static publisher landmarks, not certified physical errors;
camera motion and the reference's own accuracy remain unverified.

## Decision

Do not spend another dense tiled-detection run trying to produce physical speeds
with this calibration. First add image-supported pitch-geometry validation and
evaluate a suitable aerial calibration method. Verify visible paint alignment and
temporal consistency without supplying reference coordinates to prediction. Use a
separate recording for generalization claims. The existing broadcast-specific
experimental geometry is not automatically validated for this aerial view.

Tracking still needs an evaluation with its own predicted IDs on a sufficiently
dense sequence. The nine cached tiled frames are spaced about 0.5 seconds apart,
exceeding the tracker's default 0.25-second gap limit; replaying those frames would
reset the tracker and would not fairly measure normal tracking continuity.

Ground contact and physical speed accuracy remain unresolved. Strict telemetry
continues withholding these measurements. The new `analyze-video --no-preview`
option permits the full analysis pipeline to write JSON without creating an
encoder or rendering images, reducing unnecessary work on future evaluations.

## Reproduction

```sh
.venv/bin/python scripts/audit_automatic_calibration.py data/soccertrack-reference data/automatic-calibration-aerial.json
.venv/bin/python -m unittest discover -s tests -q
```

Use a new output path. The audit makes only three pitch-model predictions and no
player-model predictions. Source, reference and model fingerprints are recorded in
`evaluations/automatic-calibration-aerial.json`. Symmetry diagnostics in the saved
report were calculated from the saved fits, without repeating model inference.
