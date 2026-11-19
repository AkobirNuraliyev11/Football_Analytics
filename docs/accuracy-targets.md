# Measuring the 86% target

The target is not yet demonstrated. Do not average unrelated components into one
accuracy percentage or substitute software tests for performance on labeled video.

| Component | Target / required report | Evidence still needed |
|---|---|---|
| Player detection | Precision AND recall >= .86 at IoU .5 | Exhaustive boxes in a declared evaluation region, including relevant officials |
| Team classification | >= .86, unknown/missing predictions counted as errors | Independently reviewed teams and fixed A/B mapping |
| Identity continuity | IDF1 >= .86 | Real-person identities across reviewed sequences |
| Role classification | Report accuracy including missed people | Outfield/goalkeeper/official labels |
| Geometry / radar | Position error and usable coverage | Independent pitch landmarks and positional reference |
| Heatmaps | Position coverage and agreement with reference occupancy | Validated spatial mapping and reference trajectories |
| Events | Precision AND recall against labeled intervals | Event labels and adequate physical inputs |

No geometry tolerance, occupancy agreement tolerance or event timing tolerance has
yet been established as a validated application requirement. These must be declared
before judging test performance. The target cannot certify every part of the app.

## Player scorer

```sh
.venv/bin/python scripts/score_players.py data/labeled-evaluation.json data/player-scores.json
```

The JSON has a `frames` array. Each record contains `frame_index`,
`annotation_complete: true`, `references` and `predictions`. Each person record has
`identity`, `bbox: {x_min,y_min,x_max,y_max}`, `role` and optional `team` A/B.
Reference roles are outfield, goalkeeper or official. Predicted roles/teams may
be unknown. IDs must be unique within a frame; reference identities must persist
for the same real person across the sequence. Scope identities to one recording.
All visible target people in the declared evaluation region must be labeled;
filter both references and predictions using the same fixed region. Ignored/crowd
annotations are unsupported. Never copy predicted boxes or IDs into references
and describe that as independent validation.

Detection scoring maximizes admissible IoU match count before overlap quality.
Identity scoring uses global one-to-one assignment of identity overlap counts,
following the definition in [TrackEval's identity implementation](https://github.com/JonathonLuiten/TrackEval/blob/master/trackeval/metrics/identity.py).
Unknown team labels and missed labeled players count as classification errors.
A/B mapping must be fixed separately, not optimized per frame to hide mistakes.
Empty denominators are unavailable, not 100%. This scorer does not implement HOTA
or certify an evaluation split; high development scores alone cannot pass release.

## Required evidence before claiming the target

1. Independently reviewed labels, visibility rules and frame/recording identifiers.
2. Separate matches for development and final evaluation; no threshold tuning on
   the final evaluation set. Document possible pretrained-data overlap.
3. Model/source/annotation fingerprints and complete scoring denominators.
4. Precision, recall and identity/classification scores reported separately, with
   sample counts and limitations. The November 23 presentation must mark targets
   not reached or not measured as such.

The currently inspected upload contains a recurring referee-as-outfield error.
A simple official-shirt color veto was inspected but not adopted: its features
can overlap blue-team kits. It is not acceptable to hide that trade-off by removing
uncertain players from the evaluation denominator.
