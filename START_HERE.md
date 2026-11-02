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

## What was not recovered

Source videos, model weights, generated previews, detailed per-frame analysis, and the
old Python virtual environment were excluded from Git. They are not present in this
restored copy. macOS denied access to the Trash, including the recovery attempt with
elevated tool permission. Their absence here does not establish that they are permanently
deleted; check the Trash or a separate backup manually if needed.

Models can be downloaded again with the existing CLI. Generated artifacts can be
recomputed once source videos and dependencies are available. Recorded evaluation
summaries are historical evidence, not fresh real-video runs after restoration.

## Current status

Steps 1–7 are implemented: ingestion, calibration, detection/tracking, team and role
classification, gated telemetry, and tactical radar/heatmaps. Step 8 has not begun.

Real-video measurement continuity remains unresolved. Strict real-video outputs remain
unavailable; experimental estimates are sparse. Improving continuity and validating
accuracy is the next task. Do not describe the platform as production-ready.

Read `CONTINUE_PROJECT.md` before continuing development.

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
