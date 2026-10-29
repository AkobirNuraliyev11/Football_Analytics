# Tracking and classification reliability review

This pass improves Steps 4–5 before physical telemetry. It does not implement Step 6.
Baseline: `a287b360dc22f383c3ef4392c8c71bfaa4ba618f`.

## Changes

- Kit clustering filters isolated colors, checks separation against group variation,
  and learns bounded acceptance radii. This reduces number/sleeve contamination and
  permits compact dark-blue/white groups that previously failed initialization.
- Conflicting usable kit evidence produces unknown output while temporal correction
  is pending. The classifier exposes the conflict instead of silently keeping a label.
- Tracking rejects strong kit mismatches on established tracks and allows explicit
  unmatched assignments. Ambiguous, weak, and reacquired associations mark a continuity
  break; they cannot update the stored appearance descriptor.
- Records expose association reasons, continuity segments, and a preliminary
  `measurement_link_eligible` flag. New/unconfirmed tracks, uncertain associations,
  team conflicts, and team changes fail this gate.

`continuity_safe` is a heuristic, not verified athlete identity. Future telemetry must
check both endpoints, matching shot/track/segment, the preliminary gate, elapsed time,
displacement plausibility, calibrated support, and reliable ground contact. A false
gate must reset any accumulation across that observation. In particular, the new flag
can be true while `ground_contact_reliable` remains false; that is not a valid speed
measurement. There is no physical telemetry in this pass.

## Measured results

| Review | Before: correct / wrong / unknown | After: correct / wrong / unknown |
|---|---|---|
| Original clip: 91 visible-kit observations at five frames | 88 / 3 / 0 | 88 / 1 / 2 |
| Second clip: 19 visible-kit observations at frame 49 | 0 / 0 / 19 | 18 / 1 / 0 |

The first replay covers all 750 frames (30 seconds). The second covers 50 frames
(two seconds). These are small assistant-reviewed development samples. Unclear and
overlapping crops were excluded. Both clips informed changes, so neither is an
independent held-out accuracy benchmark. Labels describe visible kits, not athlete IDs.
The first result reduces false team output by abstaining; it does not increase the
number of correct labels. The second improves coverage but introduces one wrong label.

There were 334 rejected preliminary measurement links in the first replay and 69 in
the second. Track counts changed from 68 to 65 on the first and stayed 27 on the second;
fewer tracks do not establish fewer identity switches. IDF1/HOTA and per-athlete
trajectories have not been measured. Same-team crossings and long occlusions remain
unresolved risks. A broader manually labeled evaluation is required before claiming
full-match accuracy. Similar/patterned kits and misdetected roles remain limitations.

All 58 regression tests passed, including new cases for ambiguous crossings,
reacquisition gaps, opposing-kit takeover, desaturated number crops, isolated third
colors, and compact low-saturation groups. The integration fixture verifies the new
fields are exported while ground contact remains unverified.

## Reproduce and inspect

`evaluations/kit-review.json` and `evaluations/second-kit-review.json` contain the
review labels and exact source fingerprints. `evaluations/reliability-results.json`
stores the resulting counts, parameters, and learned colors.

The diagnostic replay uses retained detections from completed baseline runs, preserving
the old geometry. It does not rerun the detector or recover detections discarded by
the baseline tracker. Therefore it isolates downstream changes but is not a full
detector evaluation. Preview pitch-fit status is retained; landmark dots are omitted.
Baseline media, records, and generated previews remain local under ignored `data/`.

```sh
.venv/bin/python scripts/replay_tracking.py data/demo-step-04/source.mp4 data/demo-step-05/full-30s data/tracking-review/revised-final --labels evaluations/kit-review.json
.venv/bin/python scripts/replay_tracking.py data/tracking-review/second-source.mp4 data/tracking-review/second-baseline data/tracking-review/second-final --labels evaluations/second-kit-review.json
.venv/bin/python -m unittest discover -s tests -v
```

Use new output directories when repeating these commands. The replay checks the
source hash, frame timestamps, completed baseline status, and complete label coverage.
Revised previews are `data/tracking-review/revised-final/preview.mp4` and
`data/tracking-review/second-final/preview.mp4`. New uploads analyzed through the normal
`analyze-video` command use the updated tracker and classifier automatically.

The next module can consume these explicit uncertainty signals, but must continue to
withhold unsupported physical measurements. Step 6 remains subject to user review.
