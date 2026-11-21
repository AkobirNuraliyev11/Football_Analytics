# Consecutive-frame classification review — November 21, 2026

Six visually inspected person crops across frames 180–195 of the retained
15-second recording give 96 reviewed observations: two cyan-shirted officials and
four dark-blue outfield players. Labels were assigned by agent visual inspection
of the raw full frame and consecutive crop sheet, not copied from predicted roles.
This is a selected development subset, not independent, exhaustive or held-out
annotation. Original numeric track IDs locate fixed crops; they are not reference
athlete identities. Crop selection does not validate detection accuracy.

Baseline role results: 73 correct, 16 wrong, seven unknown (73/96, 76.04%).
The central referee is consistently predicted as outfield. The assistant official
becomes unknown when detector role votes conflict. All 64 reviewed dark-blue
player team labels are correct; this selected single-team subset does not establish
overall team accuracy. One official receives an incorrect team on 16 observations.

## Rejected changes

Two changes were replayed on all 375 frames using identical retained detections:

| Method | Known-team outputs | Central track 21 with a team | Reviewed role correct / 96 |
| --- | ---: | ---: | ---: |
| Existing classifier | 7,465 | 362 | 73 |
| Relative shirt brightness, weight 0.15 | 7,240 | 240 | 73 |
| Immediately clear a team when current kit is rejected | 6,234 | 324 | 73 |

Neither changes the central referee's wrong role or wrong team in the reviewed
16-frame interval. Immediate rejection also withholds genuine red and blue players
in the inspected full frame. Counts elsewhere are diagnostics, not independently
labeled accuracy. Neither candidate was enabled or retained in production code.
Private trial implementations, outputs and crop sheet stay in data/upload-review.

## Repeatable regression scoring

`score_classification_review` evaluates explicit role/team references against the
same fixed crops. Unknown and missing outputs remain in accuracy denominators.
Officials are excluded from team accuracy but their incorrect team assignments are
counted separately. Source mismatches, duplicate crops/frames, changed boxes and
non-finite coordinates fail. This tool must not score tracker changes as identities.

```sh
.venv/bin/python scripts/score_classification_review.py \
  data/upload-review/kit-sequence-references.json \
  data/upload-review/baseline-kit-replay.jsonl \
  data/backend/jobs/413e40e1-2318-4b13-90b2-331d2aab81fd/source.video \
  /tmp/classification-review-score.json
```

The reference document contains `source_sha256`, `review_method`, and
`observations`: each observation has `frame_index`, `source_track_id`, `bbox`,
`role`, and `team` (A, B, or explicit `not_applicable`). Prediction JSONL contains
`frame_index` and `detections` with the original box and classification. Replay
outputs with new local IDs must retain `source_track_id`. Output also fingerprints
the reference and prediction files and never certifies the 86% target.

## Speed and event dependency

The existing ridge-paint review's longest accepted measurement fragment is 0.40 s
(11 samples); the next longest is 0.28 s. Even the longest is below the 0.50 s
velocity smoothing window, before the stricter two-second track maturity rule.
These are experimental visibility/geometry screens, not verified ground contact.
Reducing the duration thresholds would not establish reliable physical speed.
Real speed, sprint and duel results therefore remain unavailable on this recording.

Next model work must address the consistent detector role confusion and improve
continuous, independently checked ground positions. Further threshold-only changes
on this clip are not a substitute. Neither classification nor speed/events is closed.
