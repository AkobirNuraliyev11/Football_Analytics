# Broader aerial ball/player audit — November 13, 2026

## Result and decision

The broadcast temporal-selector improvement does not generalize to this aerial diagnostic. On 31 cached frames (0–90, three-frame spacing), the default selector chooses no ball: 0 correct, 0 wrong, 31 unresolved. Raw detection includes a ball candidate within 10 pixels of the publisher ball-box center on 29/31 frames. Candidate selection/association, rather than raw ball recall alone, is the bottleneck here.

Two bounded hypotheses were tested, without fresh inference:

| Variant | Correct selections | Wrong selections | Unresolved |
| --- | ---: | ---: | ---: |
| Existing tracker/selector | 0 | 0 | 31 |
| Current overhead pitch context, padded by 3 configured metres | 0 | 1 | 30 |
| Wider ball-motion association plus pitch context | 0 | 2 | 29 |

Wider association alone also resolves no ball. Both trials are rejected as production behavior. Region screening lives under `benchmarks`; the tracker override defaults to zero and the analysis pipeline never enables it. High-confidence false or non-match ball candidates also occur near/on the pitch, so simply removing off-field detections cannot establish match-ball identity. Ball truth is a publisher image annotation, not a physical trajectory reference. The 10-pixel tolerance is an image-localization diagnostic, not mAP.

## Missed-player diagnosis

Using the *same* symmetric assignment rule (40-pixel maximum center distance, 10-pixel ambiguity margin against competing detections and references):

- 682 annotated player observations.
- 358 raw observations matched (52.49%).
- 332 tracked observations matched (48.68%).

This includes unmatched/ambiguous observations in the denominator. Most coverage loss is present before tracking. These are aggregate stage counts, not proof that precisely 26 particular correct detections were discarded; matching can change between stages. The older anchor scorer gives 370 raw matches because its ambiguity rule differs; it must not be compared directly with 332. `ball-aerial-baseline.json` is the canonical paired funnel; the earlier exploratory counts remain explicitly identified in `ball-aerial-audit.json`.

Unmatched emitted people are not all false positives: the publisher references include team players but exclude officials/nonparticipants. Complete person precision and missed-player false-negative rates require exhaustive reference labels and ambiguity review.

## Reproduction

`python scripts/evaluate_field_ball.py data/new-baseline.json` reproduces the baseline and region trial. Add `0.5` to reproduce the rejected movement override. Source, annotation and detection-cache hashes are checked; geometry hashes are recorded. The image-only geometry is the existing per-frame paint-checked overhead cache. References enter only after tracking/selection. This is one existing development recording, not independent-match validation.

208 Python tests pass. New tests protect stale/uncertain geometry abstention and keep the experimental movement change disabled by default. Existing broadcast pipeline behavior is unchanged. No model weights, video previews or expensive tiled inference were generated.

## Next model work

Use the existing annotated player examples to establish a detector fine-tuning/export split by recording, including officials and hard negative backgrounds. Acquire/check a separate annotated recording before model selection; frames from this same clip cannot establish generalization. For ball selection, evaluate active-ball versus spare-ball/static-object sequences and camera-aware motion evidence, including genuine stationary-ball periods. Avoid promoting another confidence, geometry or motion heuristic on these 31 frames alone. Mac/Windows application packaging stays after model/system work.
