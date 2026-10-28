# Intended final product

This is the delivery target, not a statement that these features all exist today.

## Analyst workflow

1. Upload a local match video, give the match a name, and start processing.
2. The system reads resolution and presentation timestamps automatically, detects visible
   people/ball and pitch landmarks, fits the visible ground plane, and tracks objects.
   Routine operation does not ask for player boxes or pixel coordinates.
3. See progress and any sections with insufficient camera geometry or tracking confidence.
4. Open the dark-mode dashboard and review synchronized results.

## Dashboard and downloads

| Area | Intended result |
| --- | --- |
| Video stage | Seekable match video with athlete boxes, tags, and synchronized pitch radar |
| KPI summary | Confirmed observed tracks, peak valid speed, highlight count, calibration quality/coverage |
| Telemetry | Sortable per-track/player table of observed distance, speed and sustained sprint count |
| Teams and roles | Stable two-team colors plus goalkeeper/official classifications and uncertainty |
| Tactical maps | Team and individual occupancy heatmaps with time-window filters |
| Speed chart | Comparison of athletes using quality-gated measurements |
| Highlights | Reviewable candidate duels and sustained sprints, padded MP4 clips with titles |
| Exports | CSV, analysis JSON, heatmap images, highlight videos, and technical match report |
| Demo mode | Clearly labeled cached example results when no backend job is connected |

## Honest measurement rules

Automatic input handling does not make all scenes measurable. No usable pitch landmarks
means no reliable metric position or speed for that interval. Ground-contact uncertainty,
camera cuts, jumps, occlusions, and implausible displacement must reduce coverage rather
than inflate statistics. Movement outside the camera view cannot be recovered from a
single camera; displayed distance must identify observed coverage.

The default pitch size is 105×68 m, an explicit assumption. Real-world scale cannot be
determined reliably from arbitrary pixels alone without known geometry. Nonstandard or
youth pitches may require selecting the actual dimensions; this is optional match metadata,
not manual pixel annotation. Physical-end orientation across camera shots also requires
verification before cross-shot team direction or territorial comparisons are trusted.

Track IDs are hypotheses, not verified identities or names. Long occlusions, substitutions,
and visually identical kits can cause fragmentation or swaps. Quality and continuity must
be reported, with optional analyst corrections where useful.

Nearby opponents form a candidate duel, not proof of a tackle. Sustained high speed does
not prove a counterattack. Occupancy density is not a validated pitch-control model.

## Review and release

Every completed implementation step is tested, committed, and pushed to GitHub before
review. Production readiness additionally requires representative real-match evaluation,
model license review, performance profiling, secure media ingestion/storage, and the
deployment work in the roadmap. An automated dashboard will not be described as accurate
or production-ready solely because its synthetic tests pass.
