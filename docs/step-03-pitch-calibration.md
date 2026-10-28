# Step 3 — Pitch calibration

Implemented in `football_intelligence/calibration.py`, with a runnable synthetic
landmark file in `examples/calibration-landmarks.json` and ten tests in
`tests/test_calibration.py`.

## What it does

Fit a homography from supplied image/pitch landmark correspondences, reject inconsistent
matches with RANSAC, report fit and optional independent validation errors, project
reliable athlete feet onto the pitch, and update known ground landmarks between
consecutive frames using guarded optical flow. It supports different visible pitch
regions by fitting their visible landmarks in the same canonical coordinate system.

This is a calibration engine, not an automatic pitch-marking detector. Correspondences
are supplied by an analyst or a future detector. Video ingestion and calibration expose
Python APIs for later pipeline orchestration; the ingestion CLI does not automatically
invoke calibration. New camera shots require new landmark initialization.

## Mathematics in plain English

A flat pitch appears distorted by perspective. A 3×3 matrix H accounts for that
distortion. Multiply H by `[pixel_x, pixel_y, 1]` to get `[u, v, w]`, then divide:
`pitch_x = u/w` and `pitch_y = v/w`. This maps ground-plane pixels to meters.
It cannot correctly map airborne objects, and it does not correct radial lens distortion.
Use footage with negligible distortion or a consistently undistorted raster for both
landmark annotation and subsequent tracking.

At least four non-collinear pairs are required. Four points can fit almost perfectly
even if they are incorrectly labeled, so use more widely distributed landmarks and
independent check points. OpenCV's RANSAC samples candidate fits and identifies points
consistent with the model. Since the destination coordinates are meters, this module's
RANSAC threshold is in meters. Default threshold: 0.75 m; minimum inlier ratio: 60%.
The default maximum inlier RMSE is 0.5 m. The default minimum pitch support hull area
is 20 m². These are configurable engineering thresholds, not proven accuracy guarantees.

RMSE is the square root of the mean squared Euclidean position error. Fit RMSE uses
only accepted training landmarks. Optional `validation_landmarks` are not used to fit H;
their RMSE is reported separately and must not exceed 1 m by default. No check points
means validation RMSE is null, not zero. A small validation set cannot establish accuracy
across an entire match. The implementation is based on the official
[OpenCV homography and calibration API](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html).

## Run and inspect

Optional dependencies are OpenCV headless and NumPy. Prefer a dedicated virtual environment
when installing them; do not install multiple OpenCV wheel variants in the same environment.

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[video,calibration]"
python3 -m football_intelligence calibrate-pitch examples/calibration-landmarks.json
python3 -m unittest discover -s tests -v
```

The CLI prints a JSON calibration report. It contains the matrix, source frame/raster
scope, landmarks, accepted and rejected names, fit RMSE, validation count/RMSE, and a
unique calibration ID. Output can be saved using shell redirection. The report is an
audit/export artifact; there is not yet an API to load arbitrary exported matrices as
trusted calibrations. Python consumers use the validated object returned by
`fit_calibration`.

The example uses six synthetic fitting points and two independent synthetic check points.
Its near-zero error is expected by construction and is not a real-match accuracy result.
For real footage, copy the example and replace every pixel location with a measurement
on the actual native, unrotated video frame. Pixel arrays are `[x, y]`; pitch arrays are
`[x_m, y_m]`. Frame index and shot ID must match the Step 2 output. Use a consistent physical
pitch origin across all views and halves. A mirrored or mislabeled set of landmarks can
still be mathematically consistent; semantic landmark correctness requires human review
or a future pitch detector with orientation checks.

## Python interface

```python
from football_intelligence.calibration import Landmark, fit_calibration
from football_intelligence.models import PixelPoint, PitchPoint

points = [
    Landmark("a", PixelPoint(100, 100), PitchPoint(0, 0)),
    Landmark("b", PixelPoint(1150, 100), PitchPoint(105, 0)),
    Landmark("c", PixelPoint(1150, 644), PitchPoint(105, 68)),
    Landmark("d", PixelPoint(100, 644), PitchPoint(0, 68)),
]
scope = dict(match_id="example", shot_id=0, frame_index=0, width=1280, height=720)
calibration = fit_calibration(points, **scope)
center = calibration.project(PixelPoint(625, 372), **scope)
print(center)  # approximately PitchPoint(52.5, 34)
```

`project_observation` uses the athlete bounding box's foot anchor. It clears any old
projection when ground contact is unreliable, and leaves out-of-pitch observations
without a usable position. It does not itself decide whether a player is grounded.

## Guarding against false telemetry

- Calibrations apply to exactly one match, shot, frame index, and raster size. Any mismatch
  raises `CalibrationError`; no stale matrix silently carries across camera movement.
- Projection is limited to the convex hull of inlier image landmarks. Regions outside
  that support are rejected rather than extrapolated. Reinitialize with wider landmark
  coverage to analyze more of the pitch.
- Duplicate correspondences, insufficient spatial coverage, singular matrices, and a
  projective horizon crossing the support region are rejected.
- Stored pitch coordinates retain their canonical orientation. A later display can rotate
  both axes to align with the camera view, but must not change the physical coordinates
  used for speed and distance. Team attacking direction will require period/team metadata.

## Camera motion updates

Call `update_camera(previous_rgb, current_rgb, calibration, ...)` with consecutive native
RGB uint8 arrays and their elapsed timestamps. Pass the shot ID from Step 2. The function
tracks known inlier ground landmarks with pyramidal Lucas–Kanade optical flow, checks the
reverse tracks (maximum default round-trip discrepancy 1.5 px), discards failed/out-of-frame
points, and refits the mapping using their fixed pitch coordinates.

The returned calibration is scoped to the new frame and references its parent ID. It
does not inherit the parent's validation RMSE: tracked anchors are not independent
ground truth. Gaps over 0.25 seconds, changed shots, nonconsecutive frame indices, changed
raster sizes, and insufficient remaining landmarks reject the update. Callers must stop
projecting and reinitialize when an update fails, never fall back silently to the old H.

Optical flow can drift onto players or other textures. Good forward/backward consistency
and low fitting residual do not rule out coherent drift. Re-anchor periodically using
fresh pitch observations and independent checks. The API does not yet schedule those
reinitializations. It is intended for small frame-to-frame camera movement, not unrestricted
automatic calibration through all broadcast pans, zooms, replays, and cuts.

## Validation and remaining limits

Tests cover perspective recovery, held-out residuals, a bad RANSAC correspondence,
collinear/duplicate points, stale frame/shot/match rejection, extrapolation and horizon
rejection, clearing unreliable projections, synthetic camera translation, timestamp gap
and shot resets, textureless optical-flow failure, and the example file.

The local combined suite passed with OpenCV 5.0.0, PyAV 16.0.1, and NumPy 2.4.6. The host's
existing OpenCV/PyAV wheels emitted duplicate macOS AVFoundation class warnings when loaded
together. No test failed, but packaging/integration must verify compatible isolated wheels
before production deployment. Real-camera metric accuracy remains unmeasured.

Step 4 (object detection and tracking) remains gated on review.
