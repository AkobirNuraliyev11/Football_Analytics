# November 24: displacement audit and matched pose trial

The meeting moved to November 24. This update isolates a measurement bottleneck
and rejects a higher-resolution pose variant that did not improve continuity.
No new video was generated and no physical measurement gate was relaxed.

## Exact displacement decomposition

scripts/audit_displacements.py replays current quality inputs through telemetry
and decomposes each rejected jump into vectors: change in anchor under the current
mapping, plus change in mapping at the previous anchor. Their vector sum equals
the total displacement. The two magnitudes must not be added.

All 27 implausible-displacement rejections were reproduced. Median anchor-component
magnitude is 0.5363 m; median mapping-component magnitude is 0.0630 m.
This is not error attribution: actual player motion and gait affect the anchor,
and legitimate camera compensation affects the mapping. It is not speed ground truth.
Private detailed report: data/upload-review/displacement-audit-nov24.json.

## Pose-resolution experiment

Added --pose-image-size 256|512 to review-feet, retaining 256 as default. Model
weights are unchanged and checksum-pinned. The experiment renders no preview.
Current geometry has SHA256 309f0894563b4116e2be3ece61567b8993d6bbe5d719008b6241846e111cf1d3.
The old pose comparison used a different geometry hash. Its 159 box samples must
not be used as today's paired baseline. The cached 256-pixel pose predictions
were rescored with current geometry, identical boxes and existing visibility gates.

| Same 79 frames, 11.84–14.96 s | 256-pixel crops | 512-pixel crops |
| --- | ---: | ---: |
| Visible shoe candidates before measurement gates | 53 | 51 |
| Samples entering measurement fragments | 5 | 3 |
| Longest accepted fragment | 0.04 s | 0.04 s |
| Mature speed samples | 0 | 0 |
| Paired box-anchor samples | 170 | 170 |

Decision: do not promote 512. Upsampling these crops did not create reliable foot
information. Neither pose method establishes ground contact or reliable speed.
Comparison: evaluations/pose-resolution-nov24.json. Private runs:
data/upload-review/pose256-current-geometry and pose512-shoe-comparison.

scripts/compare_foot_reviews.py now rejects comparisons with different source,
track or geometry hashes, different frame windows, or incomplete reviews.
Known synthetic translation/projective tests verify displacement decomposition;
regressions verify comparison provenance and invalid pose resolution rejection.
All 250 tests pass. Tests are software verification, not model accuracy.

## Remaining work

Real-player speed, sprints and physical duels are still unavailable. Tackles and
possession remain unimplemented. No new tracking/classification accuracy gain is
claimed by this experiment. Next useful evidence is consecutive-frame foot/identity
annotation and a controlled recording with known motion, before training or adopting
another model. The current broadcast clip cannot establish smartphone-versus-camera
accuracy loss because there is no paired reference recording.
