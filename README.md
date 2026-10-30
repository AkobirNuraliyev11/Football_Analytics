# Football Intelligence

An incremental implementation of a single-camera football analytics platform.
**Status: Steps 1–6 — ingestion, calibration, detection, tracking, classification, and a gated telemetry engine.**
The backend and dashboard are not implemented yet. Automatic analysis produces an
annotated preview, track records, and telemetry outputs. Real-video metric readings
remain unavailable until geometry and ground contact are validated; automatic pitch
fits alone do not satisfy those requirements.
This foundation is not a production-ready analytics platform.

The tracking/classification reliability pass is complete: ambiguous associations now
carry continuity warnings, conflicting kits can remain unknown, and kit tolerances
adapt to the observed groups. See [the measured comparison and limits](docs/tracking-reliability-review.md).

Step 6 adds a [telemetry engine and known-motion demo](docs/step-06-telemetry.md).
Run `python3 scripts/demo_telemetry.py --output data/my-telemetry-demo` to see checked
synthetic speed/distance/sprint results. New `analyze-video` runs export telemetry
automatically; unavailable measurements remain null, with explicit reasons.

## Architectural roadmap and review gates

Each numbered module requires user review and explicit approval before the next.
After completing and validating each step, commit and push its implementation,
tests, and documentation to GitHub before stopping for that review.

1. **Foundation (implemented):** Python package, strict configuration, coordinate and athlete observation contracts, CLI, tests.
2. **Video ingestion (implemented):** Probe metadata, decode timestamped frames, handle variable frame rates, flag candidate camera cuts, define job manifests.
3. **Calibration (implemented):** Supplied landmark correspondences, homography estimation, outlier rejection, quality checks, guarded optical-flow updates, and shot reset enforcement.
4. **Detection and tracking (implemented):** Football-specific detector, separate ball observations, timestamp-aware tracking, short-occlusion association, automatic pitch keypoints, calibration updates, and review-video export.
5. **Team and role classification (implemented):** Automatic torso-color clustering, temporal team assignments, official separation, and goalkeeper color/position checks with uncertainty.
6. **Telemetry (engine implemented):** Time-based smoothing, displacement and observation-gap gates, ground-contact uncertainty, track maturation, speed, distance, and sprint state machines. Automatic evidence needed to enable trusted real-video measurements remains unresolved.
7. **Tactical visualization:** Synchronized radar, pitch markings, occupancy grids, time-weighted Gaussian heatmaps, and image exports.
8. **Events and clips:** Candidate duels, sustained sprints, deduplication, padded MP4 extraction, and annotation overlays.
9. **Backend:** FastAPI, durable job records, worker integration, telemetry and artifact endpoints, HTTP range streaming, CORS, and exports.
10. **Dashboard:** React and TypeScript, synchronized video and radar, KPI cards, sortable telemetry, charts, heatmaps, clips, and clearly labeled cached demo data.
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

**Review gate:** stop here. Step 6 begins only after explicit user approval.
