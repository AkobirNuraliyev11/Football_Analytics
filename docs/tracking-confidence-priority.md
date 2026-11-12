# Confidence-priority tracking — November 12, 2026

## Change

The tracker previously assigned all detections together. A weak near-duplicate could take an existing ID, leaving the stronger observation to start another ID. The new default matches confidence >= 0.4 detections first, then lets weaker detections recover remaining tracks. The existing new-track threshold stays 0.4. Motion, appearance, kit checks and unmatched choices remain unchanged. All competing observations still contribute to ambiguity checks, so confidence priority cannot turn an uncertain link into a safe physical measurement by hiding its rival.

`MultiObjectTracker(prioritize_confidence=False)` and evaluator `--legacy-association` reproduce the prior association. No detector retraining or new model inference was performed. This is a tracker repair, not a fix for missed detections. Running workers must restart to load the code; existing cached reviews remain unchanged.

## Paired saved-detection checks

| Diagnostic | Before | After |
| --- | ---: | ---: |
| Tiled frames 0–90: matched observations / 682 | 330 | 332 |
| Tiled: eligible adjacent links / 660 | 206 | 208 |
| Tiled: adjacent ID changes | 1 | 0 |
| Tiled: IDs used for multiple references | 0 | 0 |
| Tiled: longest eligible continuity | 1.802 s | 1.802 s |
| Later original-cache frames 96–234: matches / 1,034 | 34 | 34 |
| Later: eligible links / 1,012 | 9 | 9 |
| Later: adjacent ID changes | 0 | 0 |
| Later: IDs used for multiple references | 1 | 1 |

Both are small same-recording diagnostics, not independent-match validation. The second has very poor detection coverage, so unchanged scores provide only weak regression evidence. Fewer unmatched outputs are not claimed to be fewer false positives because reference labels exclude some people. No player achieves two seconds of eligible continuity. Speed/contact and full-match identity remain unvalidated.

Reports include source/cache/reference fingerprints in `evaluations/tracking-confidence-priority.json`. Reproduce with `scripts/evaluate_cached_tracking.py`, respective cache/range arguments, and optionally `--legacy-association`. Outputs must use new paths.

## Ball failure review

Source-image review of three broadcast frames (41, 60, 78) shows a separate white turf object detected alongside the ball near a red player. The six retained candidate labels are assistant-reviewed development examples in `evaluations/ball-candidate-review.json`, tied to the exact tracks file by SHA-256. This is not exhaustive frame annotation or independent ground truth.

The reproducible confidence check retains three true / three false candidates at baseline. A 0.4 cutoff retains one true / one false; a 0.5 cutoff retains one true / zero false. Both discard two genuine reviewed ball observations. Therefore no blanket ball threshold increase was deployed. A proper ball improvement needs more labeled motion sequences, absent/occluded examples, and a separate evaluation recording.

Reproduce without inference or media generation:

```sh
.venv/bin/python scripts/evaluate_ball_candidates.py data/continuity-review/second-analysis/tracks.jsonl evaluations/ball-candidate-review.json data/new-ball-review.json
```

Validation: 192 existing Python tests passed after the tracking change; the new ball-review test also passed (193 total). New tracking regression reproduces a weak-box ID takeover while preserving uncertainty. No video was generated.
