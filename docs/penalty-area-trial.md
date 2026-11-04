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

## Decision and next check

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
