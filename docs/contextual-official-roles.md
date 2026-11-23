# Contextual official-role correction — November 23, 2026

The existing detector can confidently label a cyan-shirted referee as an outfield
player. Shirt chromaticity alone also puts that crop near the dark-blue team. A
new causal post-processing stage uses the match's own referee and team kit evidence
without hard-coded shirt colors or another downloaded network.

## Method and boundaries

`TeamRoleClassifier` now enables `ClassificationConfig.contextual_roles` by default;
set it to false for the previous baseline. It learns relative RGB brightness from
readable torso crops, normalized to sampled grass brightness. Features require
players at least 35 pixels tall, unclipped boxes, visible grass and non-overlapping
torsos. No features means the existing classifier is retained.

Only confirmed, continuity-safe, high-confidence underlying detector/classifier
consensus enters the kit bank. At least eight official samples and three samples
from each of at least three tracks per team are required. Per-track medians and
team medians reduce isolated contamination. Inferred corrections never train their
own official prototype. An identity-segment change discards that identity's bank;
old entries expire after two seconds, and shot/time-gap boundaries clear the bank.

A current crop must be substantially closer to an official kit than to either team
kit, for three consecutive observations no more than 0.12 seconds apart. Keeper
candidates are excluded. Corrections emit `role_evidence=experimental_contextual_kit`,
`classification_reason=inferred_official_kit_consensus`, and an unknown team.
The confidence value remains a heuristic, not a probability or verified role.

## Results on retained detections

The initial unscreened trial scored 85/96 reviewed roles but also affected a small
distant track. That version was not enabled. Visibility and identity safeguards
exclude that track, reducing the selected score to 82/96. Those safeguards were
retained rather than tuning to the requested 86% threshold.

| Selected review, frames 180–195 | Previous classifier | Integrated correction |
| --- | ---: | ---: |
| Correct roles / 96 | 73 | 82 |
| Wrong roles | 16 | 14 |
| Unknown roles | 7 | 0 |
| Role accuracy, unknowns counted wrong | 76.04% | 85.42% |
| Correct team labels on four reviewed blue players / 64 | 64 | 64 |
| Wrong team assigned to an official / 32 | 16 | 14 |

These are agent-reviewed selected development crops from one recording, not
independent, held-out or full-match accuracy. No overall 86% claim is established.
The safeguarded correction changed only original tracks 21 and 26 in the 375-frame
integrated replay (26 and 78 inferred-role observations respectively); these tracks
were visually reviewed as officials at sampled times. That is not exhaustive
identity validation. The consistent central-referee error remains on many frames.

The integrated replay includes the prior tracker boundary reset and removes stale
per-observation telemetry before rewriting track records. A `--no-preview` option
was added to replay_tracking.py; the completed replay generated no video. Original
job artifacts were not changed. New analyses use the correction automatically;
existing completed dashboard analyses remain historical.

## Physical measurements and events

Recomputed measurement review on all 375 frames: 8,487 person observations,
56 discarded short fragments, zero mature speed measurements. The longest accepted
experimental position fragment is still 0.40 seconds, below the 0.50-second speed
window. Ground contact is not verified. Strict event extraction also returns
unavailable with no events. These results show that the role correction alone does
not resolve physical speed, sprints, tackles, or duels. Zero exported events is not
a claim that the match contained no events.

Local artifacts are under data/upload-review/context-integrated-replay and
context-integrated-measurements. The role-score file fingerprints the reference
labels and predictions. Video/model data and review crops are not published.

Tests cover learning without self-training, insufficient team/official support,
identity/shot/time boundaries, absent/overlapping crops, similar kits and goalkeeper
exclusion. The full Python suite passes 244 tests. Further held-out role evaluation,
continuous ground localization, independent metric calibration/contact validation,
and event reference labels remain necessary.
