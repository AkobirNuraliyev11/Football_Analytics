# Football Intelligence

An incremental implementation of a single-camera football analytics platform.

[Complete results review: videos, tracking, classification, telemetry and evaluation archive](docs/current-results.md).
**Status: Steps 1–8 core engineering implemented; accuracy validation open. Step 9 local result workflow and initial Step 10 dashboard implemented; Step 11 local reliability started.**
The local backend supports upload, durable jobs, progress, cancellation/retry and results.
The first React/TypeScript dashboard is implemented: [run it locally](docs/step-10-dashboard.md). Automatic analysis produces an
annotated preview, track records, and telemetry outputs. Validated real-video metric readings
remain unavailable until geometry and ground contact are validated; automatic pitch
fits alone do not satisfy those requirements.
This foundation is not a production-ready analytics platform.

**Current validation status:** [Step 7 closure assessment](docs/step07-closure.md).
Automatic full-pitch overhead geometry now uses visible boundaries and native
paint-line refinement. Dense tracking improved, but usable coverage and physical
speed/contact validation remain release blockers. Step 8 engineering is authorized
to proceed separately, with strict measurement gates preserved.
Use `analyze-video --no-preview` for data-only analysis.

Tracking/classification reliability guards are implemented: ambiguous associations now
carry continuity warnings, conflicting kits can remain unknown, and kit tolerances
adapt to the observed groups. See [the measured comparison and limits](docs/tracking-reliability-review.md).

Step 6 adds a [telemetry engine and known-motion demo](docs/step-06-telemetry.md).
Run `python3 scripts/demo_telemetry.py --output data/my-telemetry-demo` to see checked
synthetic speed/distance/sprint results. New `analyze-video` runs export telemetry
automatically; unavailable measurements remain null, with explicit reasons.

A [real-video measurement review](docs/real-video-measurements.md) now provides a
separate experimental mode with visible-paint refinement, camera-motion checks, and
foot-visibility screening. The 30-second development clip produced four short
estimated movement segments. Coverage remains low and ground contact is unverified;
these are not trusted player totals. The normal analysis mode retains its strict gates.

The [optional foot-position trial](docs/foot-position-review.md) now compares pose-guided
ankles/shoes on two clips. It improves visible-shoe localization on a small paired sample,
but reduces continuous measurement coverage; it is therefore **not the default**.

[Step 7](docs/step-07-tactical-visualization.md) exports timestamped radar positions,
video overlays, observed-occupancy grids, and Gaussian heatmap PNGs for teams and local
tracks. It preserves strict/experimental quality labels and unavailable states. It
does not resolve the real-video measurement limitations or implement pitch control.

The latest continuity trial separates the age of a reliably tracked identity from the
duration of its current measurement segment. With a two-second identity history and
a fresh half-second of eligible positions, the experimental policy published 367 of
17,460 observations on the first development clip and 87 of 3,606 on the second.
Independent athlete-position and speed validation is still pending.
[See the measured comparison](evaluations/identity-maturity-real.json).

To compare the policies on existing records, run
`python3 scripts/compare_maturity.py TRACKS.jsonl REVIEW_DIR --output comparison.json`.
For a data-only geometry review, add `--no-preview` to `review-measurements`.
The optional tactical replay flag is `--separate-identity-maturity` together with
`--review`. Missing position frames stay empty under either policy.

Full implemented-versus-validated status: [illustrated project report](docs/project-status-report.md).

## Architectural roadmap and review gates

The user authorized Step 8 engineering on November 10 while Step 7 accuracy
validation continues separately. Commit and push completed, tested milestones
and documentation to GitHub. Candidate replay, window planning and explicit silent
clip extraction are implemented. Real-video validation remains a release blocker. No user
preview clips should be generated without a new request.

1. **Foundation (implemented):** Python package, strict configuration, coordinate and athlete observation contracts, CLI, tests.
2. **Video ingestion (implemented):** Probe metadata, decode timestamped frames, handle variable frame rates, flag candidate camera cuts, define job manifests.
3. **Calibration (implemented):** Supplied landmark correspondences, homography estimation, outlier rejection, quality checks, guarded optical-flow updates, and shot reset enforcement.
4. **Detection and tracking (implemented):** Football-specific detector, separate ball observations, timestamp-aware tracking, short-occlusion association, automatic pitch keypoints, calibration updates, and review-video export.
5. **Team and role classification (implemented):** Automatic torso-color clustering, temporal team assignments, official separation, and goalkeeper color/position checks with uncertainty.
6. **Telemetry (engine implemented):** Time-based smoothing, displacement and observation-gap gates, ground-contact uncertainty, track maturation, speed, distance, and sprint state machines. Automatic evidence needed to enable trusted real-video measurements remains unresolved.
7. **Tactical visualization (implemented):** Synchronized radar, pitch markings, occupancy grids, time-weighted Gaussian heatmaps, and image exports. Real-video output remains limited to eligible observations.
8. **Events and clips (core engineering implemented):** Strict sprint/duel candidates, padded shot-bounded windows, explicit silent MP4 extraction, optional observed-participant overlays and an offline viewer/JSON playlist are implemented. Real-event accuracy remains unvalidated. See [Step 8](docs/step-08-events.md).
9. **Backend (local workflow implemented):** Authenticated uploads, durable jobs, a worker, progress, cancellation/retry, indexed telemetry queries, heatmaps, event metadata and opt-in video/highlight streaming with HTTP ranges. See [setup and remaining work](docs/step-09-backend.md).
10. **Dashboard (first implementation):** React/TypeScript upload and job controls, video/radar review, current observations, sorted telemetry fragments, heatmaps, candidate clips and labeled cached results. See [setup and limits](docs/step-10-dashboard.md).
11. **Deployment and validation:** End-to-end fixtures, labeled-video evaluation, resource limits, access control, storage lifecycle, packaging, observability, and deployment documentation.

The intended data flow is video → timestamped frames → calibrated tracks →
team/role observations → telemetry and event records → media artifacts → API → UI.
Python will own the analytics pipeline. The future API will expose versioned JSON
contracts to a TypeScript frontend. Detector weights, model licenses, hardware
requirements, and deployment targets must be established in their respective steps.

## Run Step 1

Python 3.11+ is required. Step 1 uses only the standard library and needs no downloads.
From the project directory:

```sh
python3 -m football_intelligence default-config
python3 -m football_intelligence validate-config configs/default.json
python3 -m unittest discover -s tests -v
```

The CLI prints the effective JSON configuration. Validation errors go to stderr
with exit code 2. Optional editable installation (`python3 -m pip install -e .`)
exposes the same CLI as `football-intelligence`; this may require downloading the
build dependency. Installation is unnecessary for the commands above.

## Core concepts and mathematics

**Units are part of the contract.** Image coordinates are pixels; pitch coordinates
are meters; timestamps and durations are seconds; displayed speeds are km/h.
Distinct `PixelPoint` and `PitchPoint` types prevent implicit coordinate mixing.

**Pitch coordinates stay fixed.** The default playing surface is the requested
105 × 68 m rectangle, configurable for actual measured dimensions. In the canonical
top-down drawing, `(0, 0)` is the upper-left corner, x increases along pitch length
to the right, and y increases across pitch width downward. Calibration must establish
which real-world end maps to x=0 and preserve it across shots and halves. Attacking
direction belongs to team/period metadata, not jersey color or track ID.
A future display transform may rotate both axes by 180 degrees
(`x_display = length - x`, `y_display = width - y`) to match a chosen viewing orientation;
it must not alter stored physical coordinates. Screen-right orientation for changing
broadcast views requires calibration metadata, not a universal automatic assumption.

**The tracking anchor represents feet.** For bounding-box edges `(left, top, right,
bottom)`, the foot anchor is `((left + right) / 2, bottom)`. A later calibration module
will use a homography: multiply `[pixel_x, pixel_y, 1]` by a 3×3 matrix, then divide the
first two components by the third to obtain pitch meters. That model applies to the
ground plane. Jumping players, clipped boxes, and occluded feet violate its assumptions.
`ground_contact_reliable` therefore defaults to false; this flag does not itself
detect airborne players. That decision will require temporal evidence in later steps.

**Time drives physical measurements.** Telemetry uses actual presentation
timestamps: distance is `sqrt(dx² + dy²)`, speed is `distance / elapsed_seconds`, and
km/h is m/s multiplied by 3.6. A 36 km/h gate corresponds to 10 m/s; at a 0.04-second
interval, displacement above 0.4 m is suspicious. These are configurable quality gates,
not universal physiological limits. Step 6 implements these gates and validates monotonic
time and observation gaps. Missing evidence produces null measurements, not zero speed.

**Unknown is meaningful.** Team and role stay unknown until classified. A missing
projection is `None`, never a fabricated `(0, 0)`. Projected samples require a calibration
identifier. Officials cannot be assigned to a playing team. Match + shot + track ID
forms the local identity key; cross-shot athlete re-identification will need a separate,
confidence-aware association. Ball observations require a different anchor and will be
introduced with detection rather than forced into the athlete contract.

**Reject rather than clamp.** Pitch boundaries are inclusive. Out-of-bounds projections
can be retained for diagnostics but fail the planar eligibility check. Clamping would
create false touchline activity. Eligibility checks in Step 1 are necessary, not sufficient:
calibration quality, detection confidence, track duration, timestamp gaps, and displacement
checks will also be required before measurements enter final analytics.

## Implementation map

- `football_intelligence/config.py`: immutable, versioned defaults; strict JSON loader;
  rejects unknown fields, duplicate keys, invalid thresholds, and non-finite numbers.
- `football_intelligence/models.py`: geometry, roles, teams, and validated per-frame observations.
- `football_intelligence/validation.py`: reusable primitive validators.
- `football_intelligence/cli.py`: default configuration and validation commands.
- `football_intelligence/telemetry.py`: quality gates, timestamp-based smoothing, fragment distances and sprints.
- `football_intelligence/telemetry_io.py`: replay saved tracks and publish telemetry artifacts.
- `configs/default.json`: checked-in configuration matching the code defaults.
- `tests/test_foundation.py`: contract, boundary, quality-gating, and CLI regression tests.

Frozen dataclasses prevent in-place mutation; create updated observations with
`dataclasses.replace`. `AthleteObservation.to_dict()` produces JSON-safe data.
Sequence validation and external observation deserialization belong to later pipeline/API modules.

## Measurement limits that affect the architecture

Single-camera footage does not observe every athlete continuously. Off-camera movement
must remain missing; distance totals must eventually be accompanied by coverage information.
Camera motion, calibration error, occlusion, identity switches, and aerial movement can all
contaminate physical estimates. Ground-plane mapping cannot correctly locate an airborne
ball without additional assumptions. Production accuracy requires representative labeled
video and explicit evaluation, not just passing unit tests.

Opponents within 1.3 m create a **candidate duel**, not a verified tackle. Sustained speed
above 18 km/h indicates a sprint candidate, not necessarily acceleration or a counterattack.
Density heatmaps describe occupancy; true pitch control requires a separate model of
reachability and possession. Calibration accuracy must be reported with an actual metric
and validation sample count, never an invented percentage.

## Step 2: video ingestion

See [the Step 2 guide](docs/step-02-video-ingestion.md) for mathematics, data contracts,
limitations, and integration test coverage. Install optional video dependencies if needed:

```sh
python3 -m pip install -e ".[video]"
python3 -m football_intelligence probe-video /absolute/path/to/match.mp4
python3 -m football_intelligence ingest-video /absolute/path/to/match.mp4 --match-id match-001 --output data/match-001/ingestion-001
python3 -m unittest discover -s tests -v
```

The output directory must be new. It contains `manifest.json` and, on successful
completion, `frames.jsonl`. Video arrays are streamed for future pipeline consumers,
not exported as images. Generated data stays out of Git when stored under `data/`.

## Step 3: pitch calibration

```sh
python3 -m pip install -e ".[video,calibration]"
python3 -m football_intelligence calibrate-pitch examples/calibration-landmarks.json
python3 -m unittest discover -s tests -v
```

The example is synthetic and exercises the manual calibration API. Step 4's automatic
pipeline supplies model-detected pitch landmarks without asking for pixel coordinates.
See [the Step 3 guide](docs/step-03-pitch-calibration.md) for geometry, quality gates,
camera updates, and usage.

## Step 4: automatic analysis

```sh
python3 -m pip install -e ".[detection]"
python3 -m football_intelligence download-models
python3 -m football_intelligence analyze-video /absolute/path/to/match.mp4 --match-id match-001 --output data/match-001/analysis-001 --max-frames 100
```

Model downloads total about 277 MB and are cached in ignored `data/models/`.
Remove `--max-frames 100` to process the full video. The output includes a silent
`preview.mp4`, `tracks.jsonl`, `calibrations.jsonl`, and `manifest.json`. CPU inference
can be substantially slower than real time. No dimensions or pixel annotations are needed.
Pitch size defaults to an explicit 105×68 m assumption, not a measurement from the video.

See the [Step 4 guide](docs/step-04-detection-tracking.md),
[intended final product](docs/final-product.md), and [model provenance/licensing](THIRD_PARTY.md).

## Step 5: stable teams and roles

The same `analyze-video` command now learns two outfield kit groups automatically and
adds stable `team`, `role`, quality scores, and change flags to each detection. The preview
uses red/white team boxes, cyan officials, gold goalkeepers/ball, and gray unknowns.
Team A/B are arbitrary labels, not club names or attacking directions. Unknown is retained
when evidence is insufficient; goalkeeper team membership is not inferred from position.

See the [Step 5 guide](docs/step-05-team-classification.md) for behavior and test coverage.

**Current status:** Step 8 candidate/clip engineering and its synthetic browser playback check are complete. Step 9 backend foundation is implemented. Real-video metric validation remains open. No user preview clip is authorized.

The [penalty-area junction trial](docs/penalty-area-trial.md) improves local geometry
coverage, with original and audited annotations preserved. It is not yet used for
player telemetry.

The [player-anchor sensitivity audit](docs/measurement-sensitivity.md) now exposes
conditional pixel-localization speed ranges. The later reference-methodology review uses video annotations for component checks.
This does not certify real-player speed or contact.

[Independent sensor comparison and high-resolution fix](docs/sensor-comparison.md):
large inputs now preserve small players using overlapping crops. Step 8 engineering
has proceeded under the updated user authorization. The GNSS benchmark is a secondary source comparison. See the
[reference-methodology correction](docs/reference-methodology-correction.md): video
annotations now provide the component reference, while end-to-end physical accuracy
remains unverified.

## Export all saved results for offline review

With the local result data present, create a portable HTML gallery and ZIP:

```sh
.venv/bin/python scripts/export_results_bundle.py --output data/my-results-bundle
```

Open `index.html` in the generated folder, or extract the adjacent ZIP and open
its `index.html`. The gallery includes every saved heatmap, derived previews,
experimental telemetry, synthetic demonstrations and the evaluation archive.
It explicitly marks unavailable features, including confirmed tackle detection.
It does not run inference or convert unavailable measurements into statistics.
Raw source videos, model weights and backend credentials/databases are excluded.
Choose a new output directory each time; existing exports are not overwritten.

Step 11 local operations, resource limits and prediction diagnostics: [local reliability guide](docs/step-11-local-reliability.md).
