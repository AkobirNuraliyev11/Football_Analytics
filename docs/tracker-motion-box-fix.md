# Prevent inverted tracking predictions

Corner-wise velocity extrapolation could predict negative width or height after
an observation gap. Such a box has no geometric meaning but previously entered
association distance and intersection-over-union calculations.

`predict_box` now preserves the predicted center while restoring the most recent
observed box extent when extrapolation becomes invalid. Nonfinite predicted centers
fall back to the observed center. Valid predictions are unchanged. Predictions
remain association-only: missing detections never become observations or telemetry.
Any match using the fallback is labeled `invalid_motion_prediction`, breaks
continuity and cannot be treated as a safe physical measurement link. The classifier
then discards inherited team/role votes under the continuity-reset rule.

Regression tests cover collapsed predictions, ID preservation in a controlled
fixture, uncertain continuity, unchanged valid motion and no emission of unseen
tracks. All 224 Python tests passed at this milestone.

A paired replay of retained detections on the local upload found zero inverted
person predictions after the correction. Retained detections omit some raw model
candidates; this is not a full detector replay. A change in local ID count is not
verified identity accuracy. Private paired evidence and source fingerprints remain
in `data/upload-review/tracker-box-comparison.json`. Saved analyses are not rewritten;
new analyses use the correction after a worker restart.

Player association accuracy, pitch geometry, radar/heatmaps and events remain open.
The November 23 target is a research presentation with measured limitations; see
`november-23-research-delivery.md`. Specialist ball sequence trials stay paused.
