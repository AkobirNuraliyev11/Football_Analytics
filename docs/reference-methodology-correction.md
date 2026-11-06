# Reference methodology correction — November 6, 2026

The roughly three-meter GNSS/video disagreement is no longer treated as a defect
that our detector must eliminate. Our earlier validation approach overestimated
what this dataset's wearable coordinates could establish.

## Evidence and decision

The [SoccerTrack paper, sections 3.1.3 and 5.1](https://openaccess.thecvf.com/content/CVPR2022W/CVSports/papers/Scott_SoccerTrack_A_Dataset_and_Tracking_Algorithm_for_Soccer_With_Fish-Eye_CVPRW_2022_paper.pdf)
uses drone annotations as its location reference. It reports GNSS position RMSE of
2.77 ± 4.47 m across players after bias correction. Its drone annotation workflow
uses image-based detections, GNSS-assisted identity association, and manual review.
Therefore raw GNSS is not an exact independent position standard for this experiment.
The paper's metric, interval and sample differ from ours. It does not explain every
individual discrepancy in our files or certify either source's absolute accuracy.

A fixed per-player offset fitted on seconds 2–5 reduced median discrepancy on later
frames from about 2.98 to 1.32 m, but did not remove it. A motion-based identity check
also disagreed with two spatially inferred pairings. Neither exploratory adjustment
was applied to production data. More arbitrary offset fitting is not the next task.

Keep the old GNSS reports as secondary cross-source comparisons. Their historical
`error` field names must not be interpreted as validated physical measurement error.
New GNSS report fields use `discrepancy`, and explicitly identify their secondary role.

## Corrected same-frame evaluation

The new scorer uses publisher video annotations on exactly the cached source frames.
It needs no GNSS ID correspondence, clock-offset fitting, or player-specific bias
correction. Both predictions and annotations use the same publisher homography.
It evaluates detection-anchor agreement and interval net-displacement speed only.

| Metric | Original detector | Tiled detector |
| --- | ---: | ---: |
| Matched player observations / reference observations | 16/198 | 121/198 |
| Median center discrepancy | 0.229 m | 0.230 m |
| Median box-bottom discrepancy | 0.743 m | 0.591 m |
| Eligible measured intervals / reference intervals | 0/66 | 24/66 |
| Mean center-based net-speed discrepancy | unavailable | 0.488 km/h |
| 90th percentile center-based net-speed discrepancy | unavailable | 1.046 km/h |
| Mean bottom-based net-speed discrepancy | unavailable | 0.465 km/h |

The available subsets differ. The table demonstrates improved coverage without
claiming a paired accuracy improvement. Missing observations and missing intervals
remain in their respective denominators. Ambiguous identities, observation gaps,
and missing intermediate detections prevent interval scoring.

An overhead-view annotation center differs from a foot-contact point. The center's
better position agreement does not justify replacing foot anchors in broadcast
footage. Production anchor selection and strict quality gates are unchanged.

## Scope and remaining prerequisites

This is a nine-frame, same-match development check using reference-associated
identities and supplied geometry. It excludes our automatic calibration error,
tracker identity errors, ground contact, annotation uncertainty, and model-training
set overlap. Results explicitly retain `can_certify_real_speed: false`.

The reference-role mistake is resolved. The exact sensor/video clock and individual
GNSS discrepancies are not fully resolved, but are no longer prerequisites for this
video-label component benchmark. Stop spending inference or tuning on forcing raw
GNSS and video positions to coincide.

The next meaningful gate is to test automatic calibration and tracking against video
annotations on a separate sequence, keeping reference assistance out of predictions.
Physical speed/contact validation and usable coverage remain open. Step 8 expansion
stays paused. Do not generate previews without a new request.

## Reproduce using cached detections

```sh
.venv/bin/python scripts/evaluate_video_reference.py data/soccertrack-reference data/soccertrack-reference/detections-original-nine.jsonl data/video-reference-original.json
.venv/bin/python scripts/evaluate_video_reference.py data/soccertrack-reference data/soccertrack-reference/detections-tiled.jsonl data/video-reference-tiled.json
```

Use unused output names. The scorer verifies pinned annotation/keypoint hashes,
completed detection-cache provenance, and the exact cached frame set. It generates
JSON only. No detection inference, video rendering, or new model download is needed.

Validation: 147 tests passed with no skips. New analytic tests check pixel-to-meter
units and speed discrepancy, missing-detection denominators, observation-gap rejection,
ambiguous identities, and invalid/non-monotonic timing. Both real cached runs were
rescored with unchanged nominal detections.
