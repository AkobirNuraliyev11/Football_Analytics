# Step 5 — Stable team and role classification

Implemented in `football_intelligence/classification.py` and integrated into the existing
`analyze-video` pipeline. No additional model downloads or manual kit selection are required.

## Run

Use the existing detection environment and cached models:

```sh
.venv/bin/python -m football_intelligence analyze-video /path/to/match.mp4 --match-id my-match --output data/my-match/step05-001 --max-frames 100
.venv/bin/python -m unittest discover -s tests -v
```

The output directory must be new. Remove the frame limit to process the full match.
The default command performs detection, tracking, calibration, and classification together.
The video is silent, as in Step 4. No retrospective relabeling is performed: warmup frames
remain unknown in the exported records and preview, preserving what was known at that time.

## Color mathematics

The classifier crops the central upper torso to reduce head, shorts, and grass contamination.
It rejects tiny crops, very dark pixels, and completely clipped highlights. Each remaining
RGB pixel is divided by its channel sum: `[R,G,B] / (R+G+B)`. A uniform brightness change
multiplies all channels by the same amount, so the ratios remain similar. The median ratio
across the crop is the kit feature. This is a simple exposure-resistant descriptor, not a
general solution to arbitrary shadows, white-balance shifts, or multicolored jerseys.

One averaged feature per tracked person prevents a frequently visible player from dominating
initialization. At least eight supported outfield tracks are required, each with repeated
observations. A deterministic two-cluster fit needs at least three tracks per cluster,
sufficient separation, and limited within-cluster spread. If those checks fail, the system
keeps collecting evidence and returns unknown rather than forcing a split.
The reliability pass filters isolated color samples before fitting and compares separation
with within-group variation. Learned per-team acceptance radii and a separation-dependent
margin allow compact, less saturated groups without accepting every nearest color.

The more chromatic group is labeled A; ties use deterministic feature ordering. The two
reference colors are then frozen for the match, preventing A/B swaps at camera cuts.
These are anonymous team labels, not club names. Display colors are fixed red/white and
need not reproduce the actual jerseys. The manifest stores the learned color references,
track support, configuration, and readiness status for inspection.

## Temporal stability

A current feature must be close enough to one team reference and sufficiently farther
from the other to be usable. Initial assignment requires three consecutive usable samples.
Changing an already assigned team additionally requires 0.8 seconds of consistent opposing
evidence. Such changes emit `team_changed: true`, which later telemetry can use to flag
possible tracker identity errors. Unknown or conflicting evidence breaks the pending streak.
An opposing usable color immediately hides the old team label while the correction is
pending and sets `classification_conflict`; internal hysteresis still prevents one-frame
team switches. Repeated consistent opposing evidence can complete the correction.

For a short missing-color interval, a previous team label may remain with a decaying quality
score. After two seconds without supporting evidence it becomes unknown. Track histories
are removed after two seconds of absence. Camera cuts and gaps over 0.25 seconds clear
track-level votes while retaining the match-level team references. If initialization is
still incomplete, its samples are cleared at a cut to avoid double-counting track fragments.

Scores describe feature separation or role consensus; they are not calibrated probabilities.
All time-based decisions use source presentation timestamps, not processing wall time.

## Officials and goalkeepers

Role evidence comes from the football detector and is smoothed across observations.
At least three valid role observations and 75% weighted agreement are required. Missing
role evidence expires; unknown detections cannot manufacture consensus. A new conflicting
official/goalkeeper candidate immediately blocks team output even before role consensus
changes, preventing a confidently displayed team on a likely official.

Officials and goalkeeper candidates are excluded from kit-cluster initialization. Officials
never receive a playing-team label. A goalkeeper role additionally requires a kit feature
distinct from both outfield team references and a current candidate pitch position within
either penalty area. Without usable geometry or distinct color, the role remains unknown.
This uses Step 3/4's provisional geometry and is not independent evidence that the geometry
is accurate. Goalkeepers outside the box can therefore remain unknown. Goalkeeper team
membership remains unknown: a penalty-area location alone does not establish which team
the keeper belongs to, especially across halves or camera orientations.

## Output changes

Each detection in `tracks.jsonl` now includes `team`, `role`, `team_confidence`,
`role_confidence`, `classification_reason`, and `team_changed`. The original
`role_candidate` is retained for comparison. Non-person objects retain unknown team/role.
The reliability pass adds `classification_conflict`, `continuity_segment`,
`continuity_safe`, `association_reason`, and `measurement_link_eligible`.
The last field is only a preliminary association gate, not permission to calculate speed;
geometry and ground-contact checks remain necessary. See the reliability review for details.
`manifest.json` contains a `classification` section with readiness, parameters, learned
reference features, and initialization support. The preview draws officials in cyan,
goalkeepers and the ball in gold, outfield teams in red/white, and unknown tracks in gray.

This does not change `ground_contact_reliable` or enable metric telemetry. Classifying a
jersey cannot prove that a track lies on the pitch or that its measured displacement is valid.
Known out-of-pitch records are excluded from team learning and output; image tracks with
unavailable pitch geometry can still receive kit labels, but remain unfit for metric analytics.

## Validation and limits

Tests cover automatic two-team learning, uniform shadow exposure, single-frame color errors,
sustained team correction and its change flag, one-kit ambiguity, shot resets, official
exclusion, goalkeeper appearance/geometry requirements, stale evidence, and tiny crops.

In the one-second football smoke sample, the classifier learned two groups supported by ten
outfield tracks each. The final frame contained ten outfield observations per team, three
officials with no team assignment, and one ball observation. No team switches occurred.
The sample has no visible goalkeeper to validate in real footage; keeper behavior is covered
by synthetic tests. The updated preview is under `data/demo-step-05/`, outside Git.

Important limitations: black and white jerseys can share similar normalized color, patterned
or very similar kits may remain unknown, colored lighting can alter ratios, and early
misclassifications can contaminate the frozen references. There is no club-name recognition,
trained jersey re-identification, goalkeeper-to-team association, or verified cross-shot
athlete identity. The short sample and synthetic tests do not establish full-match accuracy.
Step 6 adds quality-gated physical telemetry after review.
