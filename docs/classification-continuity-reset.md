# Classification follows identity continuity

The tracker deliberately keeps a numeric local ID through some uncertain matches
and short occlusions, but increments `continuity_segment` when physical identity
continuity is unsafe. Previously, the team/role classifier keyed history only by
numeric ID. Old team and role evidence could therefore survive an explicit
continuity break.

The classifier now clears the affected track's temporal team and role state and
unfinished kit-bootstrap contribution when the segment changes. It records
`identity_continuity_reset` on that observation. The current observation begins
fresh evidence; normal minimum-sample requirements apply before emitting labels.
Learned team prototypes and unrelated tracks are preserved. Inputs without segment
metadata retain legacy compatibility, but cannot trigger this protection.

This is a stale-evidence correction, not detection recall, re-identification or
measured classification accuracy. It intentionally trades some label availability
for avoiding inherited labels after uncertain identity. Existing saved analyses
are not rewritten. Running workers need restarting before new analyses use it.

Regression tests cover immediate abstention, preserved other-track labels, retained
team prototypes, recovery on fresh evidence and removal of unfinished bootstrap
votes. A paired replay on the same local upload boxes verifies the behavior without
rerunning detection or generating footage; private counts stay in
`data/upload-review/classification-continuity.json`.

Priority remains player tracking, pitch geometry, radar/heatmaps and events.
Specialist ball recovery experiments are paused at the user's request. A separate
bounded geometry trial widening only touchline seed search did not improve the
checked frames and was not promoted. Acceptance thresholds remain unchanged.
