# Compare pitch model changes independently of fitting residuals

A smaller homography fitting residual can coexist with worse image landmarks.
Score model variants against separately reviewed image-space intersections before
promoting preprocessing changes. Keep the same reviewed points for both modes,
and count low-confidence/missing predictions in the denominator.

```sh
.venv/bin/python scripts/compare_pitch_landmarks.py predictions.json references.json data/comparison.json
```

Predictions are an array of `{mode, frame, points}` records, where `points` is the
model's native-raster list of `[x,y,confidence]` keypoints. Provide exactly two modes.
References are an array of `{frame,keypoint_index,pixel:[x,y],uncertainty_px}` records;
indices are zero-based. Duplicate frame/mode predictions and duplicate reference
points are rejected. The output includes input file hashes and is created without
overwriting an existing report. Reviewer uncertainty is not statistical confidence.
These are image errors, not metre or speed errors, and no result changes gates.

Roboflow's [training description](https://roboflow.com/blog/camera-calibration-sports-computer-vision)
states that images were stretched to 640×640. This motivates testing that input
against the current aspect-preserving adapter, but does not prove that changing
preprocessing improves this pinned checkpoint. Run paired inference, rescale
stretched output coordinates back to the native raster, and retain confidence.
Do not infer an improvement from fitting residual alone. Pitch-line checks,
independent points and subsequent camera/foot checks remain necessary.

The local upload trial and approximate assistant annotations stay in ignored
`data/upload-review/`. The trial did not justify switching production preprocessing.
No user footage or landmarks are distributed with this tool.
