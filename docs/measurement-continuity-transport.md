# Measurement continuity work — November 23, 2026

## Camera transport with current evidence

When full midfield refinement fails on a consecutive frame, the experimental
measurement review can transport the last checked calibration through current
optical flow. This addresses loss of the near touchline while the circle and
halfway markings remain visible. It does not retain old player positions.

The fallback requires current ridge-paint pixels near both local markings (at least
80 per marking), nine circle sectors, forward/backward optical-flow agreement,
at least 12 consistent field features, RANSAC support and spatial spread. The
existing current-paint residual ceiling of 0.30 m and stationary-ground motion
ceiling of 0.08 m remain unchanged. No current evidence means rejection. It is
available only on consecutive frames in the same shot; geometry gaps cannot be
bridged by holding stale matrices.

This is still `line_checked_estimate`, with method
`current_paint_checked_camera_transport`, limited to the center-circle area. Optical flow and paint checks can share image content; these are not statistically
independent measurements. Current paint checks do not independently establish player-position accuracy or ground
contact. The fallback is enabled in experimental measurement reviews, including
new upload-job reviews. `review-measurements --no-camera-transport` restores the
previous baseline for paired comparisons. Strict physical telemetry is unchanged.

Same 375 frames, corrected tracking/classification, source and configured gates:

| Diagnostic | Previous review | With fallback |
| --- | ---: | ---: |
| Frames with checked geometry | 195 | 214 |
| Frames with camera-stability evidence | 171 | 197 |
| Position samples entering measurement fragments | 173 | 193 |
| Longest accepted position fragment | 0.40 s | 0.40 s |
| Mature speed samples | 0 | 0 |

The new result contains 30 fallback frames and 184 full-refinement frames. Because
transport changes subsequent seeds, the net increase is 19 frames, not 30. No
independent accuracy improvement is claimed from increased availability alone.

## Foot localization comparison

A bounded comparison used the exact same saved geometry and tracks on frames
296–374 (79 frames, source times 11.84–14.96 s). The checksum-pinned YOLO11n pose
model localized ankles; the existing shoe screen and recently observed shoe-offset
variant were compared against box anchors. The offset trial reused cached pose
predictions and performed no new neural inference.

| Method | Samples entering measurement fragments | Longest fragment | Mature speed samples |
| --- | ---: | ---: | ---: |
| Box anchor baseline | 159 | 0.40 s | 0 |
| Pose-guided visible shoes | 5 | 0.04 s | 0 |
| Current ankle plus recent shoe offset | 9 | 0.04 s | 0 |

The shoe method found 53 shoe candidates across the window, and the offset method
77, before geometry/visibility gates. Most pose outputs could not separate shoes
at this resolution. Neither method improves speed continuity; neither was enabled
in the default measurement pipeline. No preview video was generated.

`review-feet --no-preview` now runs the data comparison without constructing a
video writer. Its manifest records rendering policy and lists only files generated.
A regression checks identical numerical output with rendering disabled.

## Remaining bottleneck and exported diagnostics

Telemetry summaries now include `continuity_diagnostics`: longest accepted position
fragment (including warmup), required velocity window, minimum identity duration,
and reasons short fragments ended. These remain diagnostics, never inferred speed.
For the new camera-transport review, 27 short fragments end at implausible
inter-frame displacement; another 18 end without a current position/reference.
The 0.40 s maximum is below the 0.50 s velocity window and two-second identity
maturity rule. Visible feet still do not establish ground contact.

Reliable real-player speed, sprints, and duels therefore remain unavailable. There
is no validated tackle or possession result. The code does not lower thresholds,
fill missing positions, or convert these failed comparisons into accuracy claims.

Private outputs: data/upload-review/context-shoe-comparison,
context-ankle-proxy-comparison, context-transport-measurements and
current-continuity-comparison.json. Original analysis results remain intact.

Validation: all 246 Python tests pass, including known synthetic camera motion,
missing-paint rejection, no-render review equivalence, and non-bridging continuity diagnostics.
