# Specialist football-ball model trial

The opt-in `benchmarks.ball_detector.SpecialistBallDetector` loads the separate
ball model published in [Roboflow's soccer setup script](https://github.com/roboflow/sports/blob/main/examples/soccer/setup.sh).
This is a different checkpoint from the four-class player model. Its single class
and SHA-256 are checked before inference. It is not loaded by the normal worker.
Weights stay outside Git under `data/models/experimental/football-ball-detection.pt`.
Source Drive ID: `1isw4wx-MK9h9LMr36VvIWlJD6ppUvw7V`.
Pinned SHA-256: `678fbad05134f19c5094cb8d273812ec9c6691228180d46832551ecf99ed2912`.
The existing third-party model/runtime licensing notes apply; downloading does
not establish new deployment rights.

The adapter accepts native RGB images, converts to BGR, runs either full-frame
640 inference or overlapping 640-pixel crops, restores native coordinates and
suppresses overlapping ball boxes. All outputs remain unverified candidates.
Tiling can both recover small balls and introduce false detections.

```sh
.venv/bin/python scripts/compare_ball_detector.py INPUT_VIDEO data/ball-trial.json --frames 100 187 325
.venv/bin/python scripts/score_ball_detector.py --predictions data/ball-trial.json --review data/ball-review.json --output data/ball-score.json
```

Choose at most ten frame indices per run. Outputs are exclusive-created. The
comparison runs fresh raw inference in all three modes, not raw-versus-tracked
counts. It records source/model hashes and wall time. Timings include warm-up;
the baseline also detects people, so specialist time is additional if combined
with that model. It generates no clips. Reviewed labels never enter inference.

The review JSON contains `source_sha256` and a `frames` array. Each frame has
`frame_index` and `status` (`visible` or `uncertain`). Visible entries require
`center_px` and `radius_px`. Score at the same confidence threshold; missing
paired rows, duplicated rows and mismatched source hashes fail. Unknown visibility
is excluded explicitly, not counted as a successful missing-ball prediction.
Off-reference candidates are not exhaustive whole-frame false-positive labels.

## Current decision

The first local upload trial does not justify replacing the default. The tiled
specialist recovers some missed ball candidates but loses another and produces
additional wrong-location candidates. Its advantage at the raw candidate threshold
does not persist at the existing new-track threshold. Full-frame specialist
inference also loses visible balls. This is small, assistant-reviewed development
evidence, not independent validation, and selected missing frames bias the sample.
Keep the alternative available for sequence experiments; do not lower tracker
thresholds or promote confidence to verified match-ball identity.

Private predictions, labels and detailed counts are under `data/upload-review/`.
Next: paired consecutive-frame evaluations around recoveries and false detections,
then separate-recording controls. Player tracking, pitch geometry, radar/heatmaps
and event validation remain separate open tasks. No retraining or production
accuracy improvement is claimed by adding this adapter.
