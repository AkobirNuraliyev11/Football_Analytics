# Penalty-area mapping trial

This data-only trial asks whether the goal line and the two boxes provide enough
local geometry to map a player outside the checked midfield region. The normal
telemetry pipeline still uses its existing quality checks.

The detector supplies an initial image-to-pitch transform. The checker searches
short profiles perpendicular to seven expected line segments, masks detected
people and the ball, and looks for a light stripe with grass on both sides.
It requires two distinct markings in each pitch direction. Alternating two-meter
pieces of each line supply fit and check pixels. A local affine correction is
limited to 1.2 m over the observed points. Each supported line must pass a 0.30 m
90th-percentile check on its reserved pieces. The output supports positions
inside the convex hull of the visible markings only. These residuals describe the
paint used by the method. They cannot establish athlete-position or speed accuracy.

On the second development match the left box passed in 33 of 150 frames.
Twenty-three confirmed person observations fell inside supported geometry.
They can include repeated observations of the same person. The trial has no
camera-motion continuity or verified ground-contact stage, so those observations
do not enter speed, distance, radar, or occupancy totals.

A separate match supplied a wide right-box view at frame 0 and partial views
at frames 375 and 700. Five landmarks were manually marked on native frame 0
before testing the mapper there. Their physical coordinates assume the configured
105 × 68 m pitch. The seed detector can itself use these markings. Only the
manual pixel readings are independent of its predictions. The mapping was
withheld on all three frames. Local error is therefore unavailable on all five
reference points. The report also gives the initial model's error at each point.
Three sampled frames from one separate match are a small generalization check.

## Reproduce

The third video is the public Roboflow soccer sample named in
`evaluations/penalty-reference.json`. Download with its recorded Drive ID and
verify the SHA-256 there. From the restored workspace, run the following with
a new output filename. The evaluator writes JSON.

```sh
.venv/bin/python scripts/evaluate_penalty.py data/tracking-review/second-source.mp4 data/continuity-review/second-analysis data/penalty-trial/08fd33_0.mp4 evaluations/penalty-reference.json data/models data/penalty-trial/replay.json
```

## Historical decision and next check

Keep this module diagnostic. The next geometry experiment should separate a
poor initial position from lost stripe contrast by measuring distance to the
nearest manually traced line on multiple labeled frames. Reserve a different
match for the next acceptance check.

For a coach usability pilot, select two comparable sequences with a player
crossing another player's path. Ask the coach to identify the same player after
the crossing and record the timestamp. Use ordinary footage for one task and
the existing tracking overlay for the other. Reverse the assignment for a
second reviewer. Record elapsed time, correct identity against an independently
reviewed answer, and corrections needed. Agree on the acceptable error rate
and time saving before testing. A coach has yet to run this pilot.

## Junction recovery follow-up (November 5, 2026)

The original checker is retained as the baseline. When it fails, the candidate
matches directed L-shaped line ends at three or four box corners. It tests bounded
local transforms, samples across image-space stripe normals, and reserves alternate
paint strips for checking. Multiple accepted transforms must share at least 35
one-meter grid samples with agreement within 0.6 m. Each returned point must also
lie inside every supporting hull and satisfy that agreement limit. Missing or
ambiguous positions stay unavailable. This remains a diagnostic experiment.

On the same 150 development frames, supported maps increased from 33 to 90 and
supported person anchors from 23 to 85. These are geometry counts, not continuous
athlete measurements. The earlier right-box sample became development data during
tuning. Its penalty-spot error fell from approximately 4.0 m to 0.58 m. Two partial
views still correctly fail the junction-support requirement.

`box-junction-holdout.json` records the first check on another view, before later
changes. `box-junction-recheck.json` is a development recheck, not a fresh holdout.
The final unused source is identified by hash and public source ID in
`box-final-reference.json`. Three correlated frames from that one clip were labeled
before predictions. No thresholds changed after that final evaluation.

### Annotation audit and results

Native-resolution inspection after evaluation found an annotation error in frame
375. The near outer-box corner was marked at (238,602), along a stripe, rather than
at its visible junction (196,630). The original labels and original 2.10 m outlier
remain in `box-final-reference.json` and `box-final-validation.json`. The corrected
labels and rerun are separate `*-audited.json` files, with an explicit audit trail.
The corrected corner lies outside supported geometry, so its prediction is missing.
It is not counted as an accurate estimate.

With audited labels, the baseline maps 1/3 sampled frames and returns 5/20 reference
points, with mean error 0.113 m and maximum 0.238 m. The candidate maps 3/3 frames
and returns 13/20 reference points, with mean error 0.135 m and maximum 0.238 m.
Unavailable points remain in the denominator. These approximate manual readings
of painted landmarks establish neither athlete ground contact nor speed accuracy.
The sample is too small to establish generalization across cameras and matches.

Reproduce the audited final check without creating media:

```sh
.venv/bin/python scripts/check_box_views.py data/penalty-trial/121364_0.mp4 evaluations/box-final-reference-audited.json data/models data/penalty-trial/audited-replay.json
```

### Remaining release blockers

- Penalty geometry has no temporal camera-motion or foot-contact validation and is
  not connected to production telemetry, radar, speed, or occupancy.
- Independent athlete trajectories and speed references are absent.
- Partial views and uncertain locations must remain unavailable.
- Full-match identity, attacking direction, and cross-shot continuity remain limited.

Step 7's existing strict gates remain in force. Step 8 event engineering can consume
those gated inputs without promoting this experiment into trusted measurements.
Real-video metric events remain unavailable until their required evidence passes.
