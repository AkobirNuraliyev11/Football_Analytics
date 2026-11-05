# Sensor comparison and high-resolution detection fix

November 5, 2026. Step 8 expansion is paused while physical measurement validation
is unresolved. This work produced a detection fix and a conditional sensor comparison.
It did not complete real-speed or ground-contact validation.

## Concrete defect and fix

The original detector resized a complete 3840 × 2160 frame to its 1280-pixel inference
size. In the overhead sample, most players became too small to detect. Some lettering
around the field was incorrectly detected as people. Two native-resolution crops
at frame 450 recovered players missed by the full-frame pass.

`FootballDetector.detect` now automatically uses overlapping 1280-pixel crops when
an input dimension exceeds 2560 pixels. It restores global box coordinates, rejects
boxes cut by internal crop edges, and merges duplicate detections by confidence and
same-kind intersection-over-union. Ordinary 1920 × 1080 input uses the old path.
No video dimensions or player pixel coordinates are requested from the user.
Analysis manifests record the detection policy. Calling `detect(..., tile_size=0)`
reproduces the original method for comparisons.

This is an accuracy/runtime tradeoff: the 4K sample uses eight inference crops per
frame. The nine-frame CPU trial took about 230 seconds including decoding/setup.
That is not real-time processing. This environment reports no available MPS device.
No claim about throughput on other hardware is made.

## Fixed same-frame comparison

The nine frames were selected before tiled inference: 300, 315, 330, 600, 615, 630,
780, 795 and 810. They form three approximately one-second intervals. Frame 450,
used for the crop experiment, is excluded. Both methods use the same model hashes,
confidence threshold, source frames, reference geometry, and identity matching.
This is a development comparison within one match, not an unseen-match benchmark.

| Quantity | Original full-frame | Overlapping crops |
| --- | ---: | ---: |
| Reference player observations | 198 | 198 |
| Matched detector observations | 16 (8.1%) | 121 (61.1%) |
| Total person detections, including unmatched/off-field | 100 | 275 |
| Usable three-sample, one-second comparisons | 0 | 24 |
| Mean net-speed difference from GNSS, box-bottom anchor | unavailable | 0.885 km/h |
| 90th percentile net-speed difference | unavailable | 1.551 km/h |
| Median position difference from GNSS | 2.726 m | 2.931 m |

The different available subsets make the position columns unsuitable for claiming
an accuracy improvement. Unmatched detections include officials, off-field people,
and false positives. The matched-observation fraction is not a precision score.
The 24 intervals are correlated samples, not 24 independent matches or validated
sprints. Ground contact is not established by this comparison.

## Reference problems found and handled

The sensor reader now handles each player separately. Identical repeated samples
collapse to one sample. Conflicting repeated coordinates stay unavailable. Neither
interpolation nor interval scoring crosses a conflicting timestamp or a missing
10 Hz sample. It does not extrapolate beyond available sensor data.

Video annotations and GNSS files use different player-number conventions. A fixed
within-team identity correspondence is inferred using seconds 2–5. A single clock
offset is then fitted from motion on that same setup segment. The best candidate
is GNSS-relative time = video time + 0.85 s, with neighboring 0.8–0.95 s candidates
having similar costs. It is an inferred offset, not independent synchronization
proof. Evaluation uses seconds 10–28 and never refits the offset there.

GNSS and drone coordinates use the publisher's separate keypoint files. Each has
65 correspondences, with 64 retained by the reference fit. This supplies reference
geometry for isolating detection/anchor effects. It does not test our automatic
pitch calibration, identity tracking, or whole pipeline.

The tiled detections' centers differ from the publisher's video annotation centers
by a median **0.230 m** on the 121 paired observations. Those annotation centers
already differ from the aligned GNSS positions by a median **2.946 m**. Therefore
the roughly three-meter discrepancy cannot be attributed to our detector alone.
Sensor noise, coordinate alignment, timing and reference construction remain possible
causes. Video annotations were partly derived using GNSS in the original dataset,
so their agreement with our detector is not independent physical ground truth.

A further inexpensive coordinate check fitted one global affine correction on
seconds 2–5 and tested annotation/reference agreement on seconds 10–28. Across
1,980 paired positions, median discrepancy changed from 2.985 m to 2.389 m, with
5.137 m at the 90th percentile after correction. This does not resolve the reference
problem. No such correction was applied to production predictions. See
`evaluations/sensor-coordinate-check.json` for the exact procedure and input hashes.

**Decision:** the sensor comparison remains diagnostic. Do not tune player positions
to remove this unexplained reference discrepancy, and do not certify speed from the
small subset of good intervals. Reports explicitly set `can_certify_real_speed: false`.

## Reproduce without rendering media

Restore the hash-pinned source with `scripts/restore_sensor_sample.py`, then use new
output names. The cache command defaults to exactly the nine comparison frames:

```sh
.venv/bin/python scripts/cache_sensor_detections.py data/soccertrack-reference data/soccertrack-reference/new-original.jsonl --mode original
.venv/bin/python scripts/cache_sensor_detections.py data/soccertrack-reference data/soccertrack-reference/new-tiled.jsonl --mode auto
.venv/bin/python scripts/evaluate_sensor_baseline.py data/soccertrack-reference data/soccertrack-reference/new-original.jsonl data/original-score.json
.venv/bin/python scripts/evaluate_sensor_baseline.py data/soccertrack-reference data/soccertrack-reference/new-tiled.jsonl data/tiled-score.json
```

Caches record source/model hashes, requested frames, method, completion state and
output hash. A failed/incomplete cache is rejected by the scorer. Full detections
and original footage stay in ignored local storage. Evaluation summaries are tracked.
No generated video or viewing sample was produced.

## Readiness before more Step 8 work

Closed in this pass: the high-resolution downscaling defect, conflicting sensor-row
handling, silent extrapolation/gap risks in the new reference reader, and mixing
setup-clock fitting with later evaluation intervals.

Still open: independently verified reference timing/coordinates, ground-contact or
empirically validated position-proxy evidence, broader camera/calibration coverage,
held-out tracking/classification accuracy, and practical high-resolution throughput.
The existing rules keep unknown teams, broken tracks and unsupported positions
unavailable. These guards prevent misleading output but do not prove model accuracy.

Next useful measurement action: resolve the reference disagreement before tuning
physical metrics. A corrected/synchronized reference and a separate evaluation
sequence are required to make an accuracy claim. Additional highlights, dashboard
work, and cosmetic previews do not address this gate and remain paused.

Validation: all 142 tests passed with no skips. New tests exercise duplicate and
conflicting sensor rows, time interpolation, gap/extrapolation rejection, crop
coverage, seam rejection, coordinate restoration, duplicate suppression, and the
unchanged normal-resolution detection path.
