# Football Analytics — restored project

Restored from GitHub on November 2, 2026 after the original local folder was deleted.

Repository: https://github.com/AkobirNuraliyev11/Football_Analytics

The restored implementation is commit `8af5f5943d1a5028e39b76e3dbb14baeadc0c1f9`.
Subsequent recovery-documentation commits may follow it.

## What is included

- The complete Git-tracked Python source, configuration, scripts, tests, documentation,
  evaluation summaries, and Git history through Step 7.
- `CONTINUE_PROJECT.md`: context and instructions for another coding assistant.
- `README.md`: architecture, commands, and module status.
- `docs/`: implementation explanations and recorded limitations.
- `docs/ORIGINAL_REQUEST.txt`: the original full specification recovered from the chat attachment.
- `evaluations/`: recorded experiment results and small reference annotations.

The active workspace is `/Users/akobir/Documents/ChatGPT/Football Analytics`.
The Desktop folder and ZIP are recovery snapshots, not automatically synchronized copies.
Choose one working copy when editing; use GitHub to synchronize changes.

Recovery verification: `python3 -m unittest discover -s tests -v` ran all 109 tests
successfully on November 2, 2026, with no skips in the current system Python environment.

## Data recovery update

Source videos, model weights, generated previews, detailed per-frame analysis, and the
old Python virtual environment were excluded from Git. The original download commands
were recovered from chat history. Both sample videos have now been downloaded again and
match their original SHA-256 hashes. The player and pitch models were also restored and
verified. macOS Trash access was not needed for this download-based recovery.

To restore the public sample videos in any new clone:

```sh
.venv/bin/python scripts/restore_samples.py
.venv/bin/python -m football_intelligence download-models
```

The downloader requires `gdown` from the detection extras. Source IDs and hashes are
committed in the script; downloaded media remain ignored by Git. Rebuilt analysis lives
under `data/continuity-review/`. Older evaluation summaries describe historical runs;
new comparisons identify their exact regenerated input hashes.

## Current status

Steps 1–7 are implemented: ingestion, calibration, detection/tracking, team and role
classification, gated telemetry, and tactical radar/heatmaps. Step 8 now has a
data-only candidate-event engine. See `docs/step-08-events.md`. Clip extraction
and overlays remain pending.

Real-video measurement continuity remains unresolved. Strict real-video outputs remain
unavailable; experimental estimates are sparse. Improving continuity and validating
accuracy is the next task. Do not describe the platform as production-ready.

Read `CONTINUE_PROJECT.md` before continuing development. The active next task is
independent sensor/video alignment and measurement validation, described in
`docs/measurement-sensitivity.md`.

## Start and test

Use Python 3.11 or newer from the project directory:

```sh
python3 -m unittest discover -s tests -v
python3 -m football_intelligence --help
```

Some tests require optional dependencies and may skip when those are missing. To create
an isolated environment for full video analysis:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[detection,calibration]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m football_intelligence download-models
```

Dependency/model installation requires internet access. Model provenance and licensing
are documented in `THIRD_PARTY.md`. The optional pose model is not needed by default.

No generated video should be opened automatically. Review previews, when requested
after the next measurement milestone, should be approximately 12–15 seconds.
