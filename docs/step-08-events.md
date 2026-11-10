# Step 8 — candidate events and highlight extraction

Started November 5, 2026. On November 10 the user authorized Step 8 engineering
separately from Step 7's unresolved accuracy validation. Candidate timestamps,
shot-bounded window planning and explicit silent extraction are implemented.
Overlays and viewer playlists remain pending. Replay and planning create JSON only.

Run from the project root with an unused output filename:

```sh
.venv/bin/python scripts/build_events.py data/continuity-review/first-analysis/tracks.jsonl data/continuity-review/my-events.json
```

The script recomputes strict telemetry from source observations and records their
SHA-256. It rejects an empty input, changed input, and existing output. Experimental
paint estimates do not satisfy strict calibration and ground-contact requirements.
An unavailable result is distinct from eligible measurements with zero events.

## Candidate definitions

- Sprint candidates inherit the telemetry engine's causal velocity smoothing,
  greater-than-18 km/h threshold, minimum one-second duration, and fragment maturity.
  Only known A/B team outfield players and goalkeepers qualify. Accepted mature
  fragments can include earlier eligible samples from their warmup period.
- Duel candidates require two mature opposing-team tracks in the same coordinate
  reference, closer than 1.3 m for at least 0.5 s. Each continuous encounter yields
  one candidate. Missing observations, failed quality, identity/reference changes,
  camera cuts, and excessive time gaps terminate an encounter.
- Terminal or quality-interrupted candidates retain truncation flags. Close proximity
  alone does not demonstrate a tackle. Sustained speed does not prove a counterattack.

Track identities remain local to their shots/fragments. The engine consumes quality
assertions and does not independently establish whether those assertions are true.
There is no ball-contact or possession inference in this slice.

## Validation and remaining work

Analytic tests cover a 21.6 km/h sprint, mature paired encounters, duplicate avoidance,
short encounters, exact distance limits, shot changes, missing observations, time gaps,
classification/reference boundaries, officials, and unverified ground contact.
The full suite passed 126 tests with no skips in the current environment.

`evaluations/step08-strict-replay.json` records replays of 750 and 150 real frames.
Both return unavailable measurements and zero events. This is a quality-gate check,
not a demonstration of real-event detection accuracy.

## Plan highlights without media

```sh
.venv/bin/python -m football_intelligence plan-highlights data/continuity-review/first-analysis --output data/my-highlight-plan.json
```

The planner checks a completed analysis manifest, frame count, match identity,
contiguous frame indices and increasing timestamps. It recomputes strict events
using the analysis configuration; it does not accept edited event JSON as proof
of eligibility. Output includes hashes, event records, observed timing and clip
windows. Padding defaults to the configured 1.5 seconds (`--padding-s` overrides).
Windows stop at observed shot boundaries and analysis endpoints. Overlapping or
adjacent windows merge within a shot, retaining distinct event IDs.

Unavailable measurements remain distinct from valid measurements with no events.
Padding is contextual footage, not additional validated event duration. Upstream
quality flags remain assertions, not independent physical validation.

## Explicit extraction

Only invoke this command when media output is wanted:

```sh
.venv/bin/python -m football_intelligence extract-highlights SOURCE.mp4 --analysis ANALYSIS_DIRECTORY --output NEW_CLIP_DIRECTORY
```

Extraction recomputes the plan, verifies the source-video hash, and checks decoded
timestamps against analysis. Inclusive observed frame ranges preserve variable
presentation intervals and each clip starts at zero. Native-raster MP4s are silent,
without overlays. The last frame's encoded duration uses the nominal rate; the
plan's end time is the last selected frame's start, not exact container duration.
The manifest records source timing, frame counts, event IDs and output hashes.

All clips are staged and inputs rechecked before publishing a new output folder.
Existing outputs are refused; failures clean up staged media. Empty plans produce
only a manifest and never open an encoder. No model inference is repeated.

Tests use temporary synthetic videos: variable timing, nonzero source origins,
multiple shots, merged windows, invalid ranges, experimental inputs, source/timing
mismatches and late-failure cleanup. `evaluations/step08-highlight-planning.json`
records data-only replays of 750 and 150 real frames: both remain unavailable with
zero windows. No real-video clip was generated or shown.

November 10 validation: **170 tests passed with no skips**, including seven
highlight-planning/extraction tests. Synthetic media is temporary and removed by
the tests. These checks establish software behavior, not real-event accuracy.

Next Step 8 work: candidate overlays and a viewer-friendly playlist/index. Physical
speed/event accuracy remains a separate Step 7 validation task. Do not generate a
user review clip until requested.
