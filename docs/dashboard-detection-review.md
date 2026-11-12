# Dashboard and detection review — November 12, 2026

User reported that only the dashboard was visible and Players/Heatmaps were difficult to access, plus player and ball mistakes.

## Completed repairs

Players, Heatmaps and Events now hide the overview video/radar and expose their own content directly. Their observation-time slider preserves access to current-frame observations. Navigating pauses video; Overview retains its playback position. Compact navigation shows text labels. Reopening the selected job no longer clears its results without triggering a reload. Aborted cached-review requests cannot replace a newly selected analysis; team filters reset on loading a review.

The model returns separate player, referee and goalkeeper classes, but the tracker treats all as people. Full-frame inference previously retained near-identical boxes across these classes, allowing competing IDs for one image region. Kind-specific suppression at IoU > 0.85 now removes near-identical person detections before tracking, retaining the highest confidence candidate. Ball/person boxes remain separate. Existing tile-merging threshold remains 0.5. A regression test exercises the actual full-frame adapter with conflicting role boxes, a nearby person and a ball.

This is a conservative duplicate-handling change, not a retrained model or demonstrated general accuracy gain. Severe overlap between distinct people can still cause suppression; an annotated crowded-player benchmark is needed. Existing cached predictions and videos are deliberately unchanged. A running worker must be restarted before it uses updated detector code.

## Saved-output diagnostic (not ground truth)

Read-only audit of `data/continuity-review/{first,second}-analysis/tracks.jsonl`:

| Saved analysis | Frames | No ball candidate | One ball candidate | Two ball candidates | Person-box pairs with IoU > 0.8 |
| --- | ---: | ---: | ---: | ---: | ---: |
| First | 750 | 295 | 449 | 6 | 34 |
| Second | 150 | 39 | 79 | 32 | 20 |

Counts describe predictions, not recall or precision. No-ball frames may include genuine occlusion. Two candidates cannot be resolved by always choosing the highest score. Very high person overlaps include IoU 0.98–0.99 in both recordings and support investigating duplicate IDs; they do not certify every overlap as a duplicate.

Next detection work needs frame-level player/ball labels (including occluded/absent ball), a held-out sequence, and separately reported missed detections, false detections and identity errors. Existing Step 7 limits remain open. Do not repeat expensive tile sweeps or claim code tests establish real accuracy.

## Validation

191 Python tests and three frontend tests passed. TypeScript/Vite production build passed. Browser checks confirmed direct Players table and Heatmaps content; Events unavailable state was also observed. No new inference or review video was generated.
