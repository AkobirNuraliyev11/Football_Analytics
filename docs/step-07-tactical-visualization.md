# Step 7 — radar and observed occupancy

The tactical visualization module is implemented. It exports a synchronized radar,
optional source-video overlay, team and individual occupancy grids, Gaussian heatmaps,
and coverage diagnostics. It consumes existing analysis; no new detector download is
needed. The backend, interactive dashboard, and events/clips are later steps.

## Position quality and continuity

Every input is replayed through the existing telemetry gates. Only current mature
observations enter the radar. Missing detections, uncertain associations, implausible
displacements, unverified contact, and insufficient geometry keep positions unavailable.
Dots disappear immediately when evidence fails. The two-second warmup is not backfilled.
There is no extrapolation, interpolation through occlusion, or stale-dot persistence.
The optional pose-foot method remains off by default because its trial reduced continuity.

The strict mode requires the existing validated-input assertions. These assertions
are not independently verified by this renderer. The explicit `--review` mode consumes
completed paint-reviewed estimates and marks all artifacts `experimental_estimate`.
It checks the exact track hash, identity list, frame indices, timestamps, and review
configuration. An optional source video must match the recorded source hash. Input
hashes are recorded and rechecked before completed artifacts are published.

Coverage includes eligible sample counts, the fraction of observed person samples,
warmup/withheld counts, and rejection reasons. Reasons can overlap and are not mutually
exclusive. This fraction is not full-match coverage: off-camera players are absent
from its denominator. Heatmaps separately report observed person-seconds.

## Time weighting and Gaussian smoothing

For two consecutive eligible samples in the same measurement fragment, let
`dt = current_timestamp - previous_timestamp`. Add `dt/2` to the cell of each endpoint.
This is trapezoidal time integration, so a stationary player contributes the same
occupancy at variable frame rates. An interval contributes only when both endpoints
are mature and eligible; gaps, reference changes, and shot changes contribute nothing.
There is no invented duration after the last sample. One isolated dot has zero occupancy.

The default grid is 1 m per cell with rows along pitch width and columns along pitch
length. Coordinates on the far boundary enter the final cell; positions outside the
pitch are rejected before drawing. Gaussian smoothing uses a 2 m standard deviation
and a four-standard-deviation cutoff. Each source-cell kernel is normalized inside
the pitch, conserving person-seconds at pitch boundaries. Divide the smoothed grid by
the group's total person-seconds to obtain probability mass per cell. This is observed
occupancy, **not territorial dominance, possession, or pitch control**.

Groups are separate for each match, shot, and coordinate reference. Track groups also
include continuity segment, role, and team. Team groups include known-team outfield
players and goalkeepers; officials and unknown-team players have individual maps only.
Identity is a local track, not a verified athlete. Team colors are arbitrary A/B labels.
The summed duration of two observed players over one second is two person-seconds.

## Rendering and synchronization

`radar.jsonl` retains the source frame indices and presentation timestamps. Optional
silent H.264 previews preserve those timestamp differences; their first exported frame
is rebased to zero, with its source time recorded in the manifest. A source video is
decoded and checked frame by frame against the radar. Preview duration is independently
limited to 12 seconds by default; analysis and heatmaps still cover the complete input.

Pitch drawings contain stripes, touchlines, halfway line, center circle, penalty areas,
goal areas, penalty spots, and penalty arcs. Outfield teams use red/white, goalkeepers
gold, and officials cyan. `--rotate` rotates both display axes by 180 degrees while
leaving stored coordinates unchanged. The pipeline cannot yet infer attacking direction
or guarantee physical-end identity across broadcast shots; the display states this.

Heatmaps export at 1130 × 830 pixels for the default pitch. Their blue-to-red legend
is normalized to each map's own peak; colors across images are not directly comparable.
Numeric grids retain comparable units. Empty inputs produce an unavailable image,
not a fabricated activity map. Experimental real-video occupancy covers only the
checked center-circle region; blank surrounding areas do not mean no players were there.

## Run

Use the existing detection environment, or install the video and calibration extras:

```sh
python3 -m pip install -e '.[video,calibration]'
.venv/bin/python -m football_intelligence build-tactics data/my-match/analysis/tracks.jsonl --output data/my-match/tactics
```

Strict automatic real-video analysis currently produces unavailable radar/occupancy
because validated ground contact and geometry remain unresolved. To explicitly inspect
the separately reviewed experimental estimates:

```sh
.venv/bin/python -m football_intelligence build-tactics data/my-match/analysis/tracks.jsonl --review data/my-match/measurement-review --video /path/to/match.mp4 --output data/my-match/experimental-tactics --preview-seconds 12
```

`--review` must contain a completed `review-measurements` run for the exact complete
tracks file, not a pose-foot trial. Partial review/track length mismatches fail.
Use `--config` for strict inputs with nondefault pitch/analytics settings; experimental
mode inherits its review configuration and rejects conflicting overrides. Other options
are `--cell-m`, `--sigma-m`, `--rotate`, and `--preview-start-s`.

Outputs include `manifest.json`, `radar.jsonl`, `occupancy.json`, and heatmap PNGs. When
the requested preview window contains frames, it also includes `radar.png` and
`preview.mp4`. Failure leaves a failed manifest and partial artifacts; consumers must
require `status=completed`. Output directories must be new. Generated media stay in
ignored `data/`; code, tests, and evaluation summaries are committed.

## Independent reference evaluation

`scripts/evaluate_trajectories.py` scores separately supplied meter-position labels:

```sh
.venv/bin/python scripts/evaluate_trajectories.py data/my-match/tactics/radar.jsonl labels.json --output scores.json
```

Labels contain `predictions_sha256`, `independent_reference: true`, `reference_method`,
and `samples`. Every sample has `match_id`, `shot_id`, `frame_index`, `track_id`,
`coordinate_reference_id`, `timestamp_s`, `x_m`, `y_m`, and `uncertainty_m`.
Reference positions must use the same physical coordinate frame and anchor definition,
and come from independent measurement, not the homography being evaluated. Independence
is a supplier assertion; the script cannot authenticate it. It reports availability,
position MAE/RMSE, and displacement-speed MAE between labeled endpoints in the same
fragment. It does not compare smoothed instantaneous telemetry speeds or full paths.
Missing predictions stay in the availability denominator. Reference uncertainty is
reported per point rather than subtracted to inflate scores.

There are currently **no independent real-video meter-trajectory labels** in this
workspace. The scorer is tested with analytic fixtures; no real speed-accuracy claim
is made. Stronger foot/contact evidence and an independent reference dataset remain
necessary for trustworthy physical telemetry. Step 7 does not make that problem solved.

## Recorded validation

See `evaluations/step07-results.json` for exact input hashes, case results, and preview
timing. The known-motion fixture supplies two mature tracks over six post-warmup
seconds each: 12 person-seconds for their team. Gaussian smoothing conserves that total.
The short ghost track and ungrounded track never appear on the radar.

The first 30-second real clip yields 83 eligible experimental person samples out of
17,460 (0.475%), with 3.16 post-warmup person-seconds across four local tracks. The
second six-second clip yields none. Strict processing of the first clip yields none.
These results preserve the prior measurement behavior; this step does not improve
real-video continuity. It exposes its limits in radar, coverage, and occupancy exports.

All **109 tests passed**. Tests cover known occupancy, variable frame rates, missing observations, cuts, long
gaps, reference/team changes, out-of-bounds positions, teleports, officials, unknown
teams, edge-mass conservation, display rotation, video timestamps, provenance guards,
failed publication, and independent-reference scoring. Run:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/validate_step07.py --root data/step-07 --output data/step-07-validation-new.json
```

The user authorized work through Step 7 without intermediate video previews. Stop for
review after this step; event detection and highlight extraction are Step 8.
