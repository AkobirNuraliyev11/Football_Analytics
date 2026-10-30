# Step 6 — physical telemetry engine

Follow-up: [real-video measurement review](real-video-measurements.md) adds a separate
experimental mode. The strict behavior described below remains the default. Reported
peak speed now excludes partial smoothing windows at startup, and a fragment must
span both the minimum track duration and a complete smoothing window.

The engine calculates speed, observed distance, and sustained sprint bursts from
eligible ground-plane observations. It is integrated into `analyze-video` and can
also replay existing tracks without running a detector. This step does not implement
radar, heatmaps, video highlights, the API, or the dashboard.

**Current real-video limitation:** the detector pipeline still supplies provisional
pitch fits and unverified ground contact. These inputs produce unavailable physical
measurements. There is no automatic foot-contact/jump detector or independent geometry
validation in this step. The module withholds uncertain aerial observations; it does
not claim to distinguish every jump from running. The known-motion demo below tests
the calculator separately and must never be presented as results from a match.

## Run and review

New video runs automatically produce telemetry alongside the usual preview:

```sh
.venv/bin/python -m football_intelligence analyze-video /path/to/match.mp4 --match-id my-match --output data/my-match/step06-001 --config configs/default.json
```

The preview displays a speed only when eligible and mature; otherwise it shows
`-- km/h`. The header reports whether a measurement is available in the current frame.
No pixel coordinates, resolution, or manual bounding boxes are requested.

To test the engine without video or model dependencies:

```sh
python3 scripts/demo_telemetry.py --output data/demo-step06-new
python3 -m unittest discover -s tests -p 'test_telemetry.py' -v
```

Add `--plot` to the demo command if matplotlib is installed. The demo creates 201
synthetic frames covering eight seconds and checks exact expected results:

| Synthetic track | Motion | Result |
|---|---|---|
| 1 | 3 meters per second | 10.8 km/h, 24 meters, zero sprints |
| 2 | 6 meters per second | 21.6 km/h, 48 meters, one sprint |
| 3 | Visible for only 0.4 seconds | Excluded as a short fragment |
| 4 | Ground contact unverified | Measurements withheld |

Replay saved track records with:

```sh
.venv/bin/python -m football_intelligence compute-telemetry data/tracking-review/revised-final/tracks.jsonl --output data/my-telemetry-review --config configs/default.json
```

All output directories must be new. Match the configuration's pitch dimensions to
those used to project the source coordinates; changing dimensions cannot rescale
already projected records. The replay consumes the supplied JSONL as a bounded
observed interval, not as proof that a full match was processed. Its manifest records
the exact input hash. Malformed records or backward timestamps fail the job; partial
artifacts are not published under the final filenames. Consumers must check the
manifest's completed status before reading results.

## Mathematics and limits

For consecutive positions separated by `dt` seconds, displacement is the straight-line
distance in meters. Raw velocity is `(new_position - old_position) / dt`. Multiplying
meters per second by 3.6 gives kilometers per hour. A raw displacement implying more
than the configurable 36 km/h cap is rejected **before** smoothing, rather than
clamped to the cap. The rejected point cannot seed the next fragment.

The engine averages velocity vectors over a trailing 0.5-second window, weighting
each interval by its actual overlap with the window. This handles variable frame
rates and partially overlapping intervals. Distance integrates the magnitude of this
smoothed velocity over accepted time intervals. This reduces alternating position
jitter, but introduces lag and can underestimate sharp turns. It is an estimate of
observed movement, not exact path length. No movement outside observed intervals is
invented, and thresholds are configurable quality controls, not universal limits.

Above 18 km/h, a sprint candidate begins. At least one second of uninterrupted
above-threshold smoothed speed is required. Falling to or below the threshold ends
the burst. A discontinuity or end of input terminates it with a `truncated` marker;
the marker does not imply the player physically stopped. Interrupted short bursts
cannot combine into a sprint. Sprint timestamps refer to intervals classified by
the causal smoothed speed, so onset/offset have smoothing uncertainty. These are
high-speed bursts, not proven acceleration or counterattacks.

## Eligibility contract

Frame records contain `match_id`, increasing `frame_index` and `timestamp_s`,
nondecreasing `shot_id`, and `detections`. A run contains one match. Eligible person
records require all of the following:

- Confirmed tracks, `continuity_safe: true`, and `measurement_link_eligible: true`.
- `classification_conflict: false` and `team_changed: false`.
- A known role: outfield, goalkeeper, or official. Officials remain separate by role;
  unknown team membership is allowed and must not be guessed.
- Frame `calibration_status: "validated"`, a nonempty per-frame `calibration_id`,
  and a nonempty `coordinate_reference_id` identifying the same physical pitch axes
  and scale across successive fits.
- `ground_contact_reliable: true` and `projection_state: "validated_ground_position"`.
- Finite `pitch_position_candidate: {"x_m": ..., "y_m": ...}` inside the configured pitch.
- A nonnegative integer `continuity_segment`.

These are assertions from an upstream validator, not facts proven by this calculator.
Setting flags to true does not validate footage. The synthetic fixture can assert
them because its geometry and motion are defined exactly. Automatic video analysis
deliberately does not promote its current provisional evidence to this contract.
Unknown/absent flags fail closed. Ball observations are never treated as planar athletes.

Both endpoints must pass. A camera cut, missing observation, excessive gap (default
0.25 seconds), quality failure, changed continuity segment, role/team change, or changed
coordinate reference terminates the fragment. Different per-frame calibration IDs are
allowed only within an unchanged reference. Unreported intervals up to the gap limit
use their actual elapsed time; an explicit missing observation always breaks continuity.
Same-team identity swaps that evade the tracker remain an unresolved risk.

## Outputs and maturity

- `telemetry.jsonl`: one record per input frame, with per-track measurement status,
  reasons, fragment ID, speed, observed distance/duration, sprint count and sprint state.
- `telemetry-summary.json`: configuration, coverage diagnostics, rejection counts,
  discarded short-fragment count, and eligible fragment summaries with sprint intervals.
- `tracks.jsonl` in new analysis jobs also contains each detection's `telemetry` result.

Unavailable values are JSON null. A genuinely stationary eligible track has numeric
zero speed/distance. Each uninterrupted eligible fragment must reach two seconds
before any measurements become visible. Its final totals include the eligible warmup
interval, but historical JSONL rows are not retrospectively rewritten. Brief fragments
never enter the summary. A fragment is scoped to match, shot, and track; separate
fragments are never silently merged into a player's full-match total.

`measured_observation_fraction` is the fraction of emitted person observations with
published measurements after warmup, not percentage of match time or athletes covered.
Rejection counts may overlap because one observation can fail several gates. Eligible
fragment durations are reported separately; summing durations across people is not
video duration. `metric_telemetry_enabled` means the engine ran; the separate
`metric_measurements_available` flag says whether a video run produced eligible totals.

## Validation performed

73 regression tests passed. Added cases cover variable timing, stationary zero versus
missing, exact known motion, jitter smoothing, two sprint bursts, threshold boundaries,
interrupted bursts, raw displacement caps, ghost tracks, cuts, gaps, quality failures,
reference changes, malformed sequences, output publishing, and pipeline integration.

The revised 750-frame football sample was replayed: all 17,460 person observations
were withheld because calibration and ground contact are unverified (some also fail
other gates). A fresh 25-frame model-inference run completed and exported the new
telemetry files and preview. The synthetic eight-second demonstration reproduced its
expected speed, distance, and sprint totals. These tests validate implementation behavior,
not real-match measurement accuracy. Results are recorded in `evaluations/step06-results.json`.

The calculation module is ready for review. Trusted automatic real-video telemetry
still needs independently checked calibration, ground-contact evidence, and representative
trajectory evaluation; those prerequisites are explicitly unresolved.
