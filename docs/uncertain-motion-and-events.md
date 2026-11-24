# Uncertainty-aware motion and event thresholds

## Default event correction

Sprints previously used nominal windowed speed even when a supplied pixel-localization
bound overlapped the sprint threshold. Now the lower speed bound must exceed the
threshold when that bound is available. Ambiguous samples terminate the current
sprint interval. Known uncertainty therefore cannot be ignored to create a sprint.

Proximity candidates similarly require nominal separation plus the sum of available
endpoint radii to remain below the duel threshold. Ambiguous proximity splits the
encounter; two short encounters cannot be joined across that boundary. This is a
proximity candidate, not a detected tackle.

Events identify whether threshold evidence had complete pixel bounds or was nominal.
Missing bounds are not silently represented as zero uncertainty. These are only
pixel-localization screens; calibration/contact/identity errors remain excluded.

## Opt-in motion experiment on existing footage

TelemetryEngine(uncertainty_aware_displacement=True) requires experimental=True.
Default production displacement gates remain unchanged. The experiment retains a
large observed jump only if its endpoint localization radii admit displacement at
or below the configured maximum speed. Missing bounds retain the nominal gate;
impossible jumps, identity changes, missing positions and reference gaps still split
fragments. No old positions are filled into gaps. The smoothing window remains0.5s,
identity maturity2s and speed ceiling36km/h. Identity maturity is measured separately
from geometry availability in BOTH arms of this comparison.

This is a conditional change to observation eligibility, not a proof that the anchor
is accurate. The assumed +/-3 pixel bounds are not independently measured. Pairwise
compatibility does not establish a globally consistent feasible trajectory.

Paired replay: same375 frames, tracks and geometry, evaluated in
scripts/compare_uncertain_motion.py. See evaluations/uncertain-motion-nov24.json
for exact input hashes and every estimate.

| Outcome | Nominal displacement | Pixel-compatible displacement |
| --- | ---: | ---: |
| Mature experimental speed samples | 0 | 58 |
| Longest accepted fragment | 0.40 s | 1.44 s |
| Fragments reaching experimental speed maturity | 0 | 5 |
| Nominally excessive intervals retained using assumed bounds | 0 | 37 |
| Qualifying sprints | 0 | 0 |

Exploratory windowed speeds range10.72–27.76km/h. Example16.9997km/h has a pixel-only
range10.2891–23.7103km/h. These are not confidence intervals and exclude geometry,
camera, scale, identity and ground-contact errors. Do not present them as reliable
physical measurements or mix them into the default match telemetry.

Across the experimental stream30 nominal threshold crossings are ambiguous under
pixel uncertainty;5 clear the lower bound, but none lasts the required1s. These are
frame/interval decisions, not counts of actual sprints. Physical duel candidates in
strict EventEngine remain unavailable; tackles and possession are not implemented.

## Verification and limits

257 tests pass, including compatible jitter, impossible jumps, missing-position
boundaries, no strict opt-in, uncertain sprint/proximity rejection, and encounter
splitting. Existing software fixtures preserve expected exact motion outputs.
No new clip, model download or detector training was performed.

This fixes event threshold handling and produces inspectable experimental motion
estimates from the existing footage. It does not solve independent real-speed
accuracy or establish ground contact. Those remain unresolved with this footage.
