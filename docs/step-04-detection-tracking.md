# Step 4 — Automatic detection, tracking, and pitch initialization

## Implemented

- Football-specific player, goalkeeper, referee, and ball detections from a pretrained model.
- Automatic 32-keypoint pitch detection, with confidence filtering and a mapped landmark subset.
- No manual dimensions, boxes, or pixel coordinates required for `analyze-video`.
- Motion/appearance tracking, conservative short-occlusion association, track maturation,
  shot/gap reset behavior, and separate ball/person identities.
- Automatic initialization of Step 3 calibration, optical-flow updates between model
  refreshes, and explicit unavailable states when geometry fails checks.
- A silent H.264 review video with boxes/IDs and accepted pitch landmarks, plus frame records,
  calibration reports, source/model hashes, and job manifests.

These outputs are review artifacts, not the finished tactical dashboard.

## Run

The existing project virtual environment was created with host packages for the local smoke
test. For a reproducible setup on a new machine, create an isolated virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[detection]"
python3 -m football_intelligence download-models
python3 -m football_intelligence analyze-video /path/to/match.mp4 --match-id my-match --output data/my-match/analysis-001 --max-frames 100
python3 -m unittest discover -s tests -v
```

Use a new output directory per run. `--max-frames` bounds a smoke test; omit it for the full
video. `--device cpu` is the default. A compatible GPU can be selected with `--device mps`
or the appropriate CUDA device. GPU performance and compatibility have not been validated
by the CPU smoke test. No live inference service or account token is required.

`download-models` fetches about 277 MB from URLs in Roboflow's published soccer setup.
The two artifacts have pinned SHA-256 hashes. `analyze-video` checks those hashes and runs
inference locally. Weights/video remain outside Git. See `THIRD_PARTY.md` for provenance
and licensing constraints. Runtime dependencies use version ranges rather than a deployment
lockfile; dependency locking and clean-platform packaging remain release tasks.

## Files and contracts

| File | Responsibility |
| --- | --- |
| `model_assets.py` | Explicit cached downloads, pinned hashes, model manifest |
| `detection.py` | Model adapters, image-coordinate boxes, semantic pitch landmarks |
| `tracking.py` | Temporal association and track lifecycle |
| `analysis.py` | Streaming pipeline, automatic calibration, JSONL and preview video |
| `tests/test_detection_tracking.py` | Deterministic association and media-output integration tests |

Each `tracks.jsonl` line contains source timing, frame index, shot ID, calibration status,
and observed detections. Each detection includes track ID, tentative/confirmed status,
kind, confidence, candidate role, bounding box, and image anchor. People use feet-level
bottom-center anchors; balls use image centers and are never ground-projected automatically.

Metric coordinates, when available, are named `pitch_position_candidate`. They assume the
feet touch the pitch and are explicitly not trusted telemetry. `ground_contact_reliable`
remains false until Step 6 adds temporal/ground-contact quality decisions. Unknown or
unsupported positions stay missing; no coordinates are invented for off-camera movement.

`calibrations.jsonl` contains accepted per-frame calibration reports. Reported fitting
residuals are not independently measured accuracy. No validation percentage is fabricated.
`manifest.json` records counts, timing, parameters, hashes, assumed dimensions and completed
or failed status. Preview audio is intentionally omitted. A bounded run's frame limit is
recorded so it is not mistaken for a full-match analysis.

## How tracking works

The model proposes boxes and class probabilities. Association compares each current
detection to predicted positions of recent tracks using:

1. Box intersection-over-union (overlap divided by union area).
2. Center distance normalized by box size.
3. An HSV histogram from the inner torso crop, which provides a weak appearance cue.

A Hungarian assignment minimizes the combined cost while ensuring one-to-one matches.
The predictor smooths image-box velocity using actual timestamp differences. This pixel
velocity is only for matching; it is not athlete speed in km/h. Weak detections can extend
an existing track but cannot start one below confidence 0.4. Tracks become confirmed after
three observations. Unseen tracks are retained for at most one second, but predicted boxes
are not emitted as observations. Camera cuts and gaps above 0.25 seconds clear association
state. IDs are unique within a run; match/shot scope remains explicit.

This is a baseline appearance-assisted tracker, not a trained person re-identification
network. Matching can fail through identical-kit crossings, long occlusions, rapid camera
motion, and replays. A track ID does not establish a player's name or jersey number. Step 5
will stabilize team/role classification; model role labels here are candidate observations.

## Automatic pitch geometry

Model keypoint pixels are returned in native image coordinates. Their index order is mapped
to known pitch geometry. Ambiguous penalty-arc intersection labels are omitted; circle
cardinal-point labels are retained for midfield coverage, using the model's intended
semantic interpretation. Their true perspective accuracy still needs labeled evaluation.

At least six confident and six geometrically consistent landmarks are required for automatic
initialization. Step 3's spread, inlier ratio, residual, horizon, and support-region checks
remain active. Pitch inference refreshes every ten frames by default (`--pitch-every`);
the intervening frames use guarded optical flow. Failure removes the calibration and retries
model initialization on the next frame. There is no fallback to an outdated transform.

Only positions inside the inlier landmark hull are supported. People outside that hull are
retained as image tracks with unavailable pitch positions, not included as valid on-pitch
telemetry. Off-pitch candidates fail the pitch-boundary check. This intentionally sacrifices
coverage when geometry is weak rather than snapping bench personnel to the touchline.

The metric scale assumes a 105×68 m full-size pitch. It cannot establish the true pitch size
from arbitrary footage alone. The Python API accepts `PitchConfig` for known dimensions.
Model-canonical orientation is not verified physical-end identity across shots; future
cross-shot aggregation must resolve that before claiming consistent attacking direction.

## Test scope and remaining work

Unit/integration tests verify ordering-invariant IDs, short occlusion recovery, expiry,
confidence thresholds, ball/person separation, shot/gap resets, timestamp monotonicity,
keypoint filtering, bounded analysis, variable-timestamp video export, and failure manifests.
The deterministic pipeline test injects detections deliberately; the separate smoke test
uses real model weights on a short published football sample.

Recorded smoke test: a one-second, 1920×1080, 25 FPS excerpt from the first sample linked
by Roboflow's soccer setup. The corrected pipeline processed all 25 frames, produced 24
track IDs, and accepted pitch fits on 24 frames. The other frame failed geometric support
checks. Across the 25 frames it emitted nine observed ball records (not nine separate balls).
175 person records had candidate pitch positions; other person observations lacked usable
calibration or lay outside the supported region. The run took about 37 seconds on this
host's CPU, including source hashing and media export after model loading. These counts
are diagnostic outputs, not ground-truth accuracy scores. All 40 repository tests passed.

Local smoke artifacts are under `data/demo-step-04/run-002/`; they are intentionally ignored
by Git. A sample still is `data/demo-step-04/step-04-result.png`. Reproduction uses the model
hashes pinned in `model_assets.py` and the command described above on a one-second excerpt;
exact detector/tracker results can vary by runtime/platform.

This does not establish detector recall, identity accuracy, ball recall, calibration accuracy,
or full-match performance. Broadcast balls can be tiny or occluded. Optical flow can drift,
and model landmark errors can be mutually consistent. The local host's OpenCV/PyAV wheels
still emit duplicate macOS AVFoundation class warnings (documented in Step 3); the tests
run successfully, but clean deployment packaging must resolve that combination.

Not yet implemented: stable team separation, ground-contact validation, metric telemetry,
radar/heatmaps, highlight extraction, service endpoints, or the interactive dashboard.
The final intended experience is documented in `docs/final-product.md`.
