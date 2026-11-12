# Temporal ball selection — November 13, 2026

## What changed

A new causal selector operates after tracking. It ranks only currently observed ball candidates using exponentially smoothed confidence (0.12-second half-life). Competing candidates require three observations for the leading track and a score margin of at least 0.15. Ties, immature leaders and close rivals remain unresolved. History expires after 0.25 seconds and resets at shot changes. Missing observations never produce an invented ball. A single observed candidate remains available immediately, explicitly unverified; isolated false positives are not solved by this change.

The first trial delayed every new ball for three observations and lost three of the six first-recording controls. That behavior was rejected. Maturity now applies only when resolving competing candidates. Both recordings informed the final implementation; neither is a held-out validation set.

The pipeline exports `ball_selection` on each frame and `ball_selection_state` on every ball record. Raw candidates remain in JSON, including alternatives. Future requested previews omit alternatives only when a winner is selected. Unresolved candidates are retained and all ball labels say “ball candidate.” No selected ball is marked verified, projected onto the ground, or used to justify possession/tackle metrics. This is a post-processing change, not detector retraining or recovery of missing objects.

## Measured result

| Reviewed subset | Original retained candidates | Temporal selection |
| --- | --- | --- |
| Second recording, frames 41/60/78 | 3 ball + 3 false turf-object candidates | 2 ball selected; 0 turf objects selected; frame 41 unresolved |
| First recording, six ball controls | 6 ball candidates | All 6 retained |

The confidence-only 0.5 cutoff previously retained only one of the three second-recording true candidates. Temporal selection retains two while selecting none of the three reviewed false candidates. In frame 41, neither candidate is selected; this is an abstention, not a successful ball localization.

Both reports replay complete retained sequences (750 and 150 frames), but the accuracy labels cover only the listed small subsets. The first recording includes visually blurred balls. Frame 394 was additionally inspected at frames 390/394/398: the central object moves away from the passing player, supporting the ball label. Labels are assistant-reviewed development annotations, not independent ground truth. Complete per-frame precision/recall, missing-detection recall and held-out generalization are not measured. Known selection risks include persistent high-confidence false positives, wrong tracker identities and temporarily suppressing a true ball when a rival dominates.

Files: `evaluations/ball-selection-first.json`, `evaluations/ball-selection-second.json`, `evaluations/ball-other-match-review.json` and the prior `ball-candidate-review.json`. Source/track/review fingerprints support reproducibility. The paired still at `docs/design/ball-selection-comparison.png` shows frame 78 before and after selection. It uses source pixels and saved observations; no new video or neural inference was generated.

```sh
.venv/bin/python scripts/evaluate_ball_selection.py data/continuity-review/second-analysis/tracks.jsonl evaluations/ball-candidate-review.json data/new-ball-selection-report.json
```

## Validation and next work

205 Python tests passed. Selector regressions cover true-candidate retention, weak competing boxes, unresolved ties, missing observations, shot resets, expired history and monotonic timing. Pipeline integration preserves all raw ball candidates and the unverified physical-depth contract. Cached dashboard video is unchanged; restart the worker before new analyses to use this code.

Next model work: expand independent annotations of missed players, false isolated balls, occlusions and camera motion; compare detector candidates on that dataset. No claim is made that ball detection, tracking, classification or physical speed is fully solved. The user requests Mac and Windows applications only at the final packaging stage, after model/system reliability work.
