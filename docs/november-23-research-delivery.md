# November 23 research presentation

Updated November 19, 2026. The user selected **research presentation with measured
results and limitations** as the deadline deliverable. This is the working delivery
scope, not a promise that physical accuracy research will finish in four days.

## Research claim boundary

The original smartphone-versus-professional-camera accuracy question has not been
answered. Current recordings are development material, not a paired, synchronized
phone/professional-camera experiment. Present that comparison as the proposed study.
The completed contribution is an automatic prototype plus reproducible component
diagnostics, measured failures, rejected experiments and targeted software fixes.

## Deliverables and acceptance criteria

| Deliverable | Acceptance criterion | Current gap |
|---|---|---|
| Research presentation | Methods, evidence denominators, limitations and next experiment are explicit | Deck not yet authored |
| Demonstrable local pipeline | Known video completes upload, analysis, review and export | Final rehearsal with current code pending |
| Player tracking evidence | Report identity metrics only against reviewed identities; distinguish raw counts | Independent identity annotations incomplete |
| Geometry evidence | Compare with visible independent markings; show abstentions | No reliable checked positions on the tested upload segment |
| Radar / heatmaps | Show only supported positions and report coverage; disclose unavailable outputs | Uploaded-video outputs remain unavailable |
| Events | Describe implemented candidate rules and missing measurements | No validated real sprint/duel results; confirmed tackles unimplemented |
| Reproducibility | Source/model fingerprints, scripts, test results and commands retained | Consolidated presentation evidence packet pending |
| Offline fallback | Local saved evidence and walkthrough available without a server | Final presentation fallback pending |

## Work order toward the deadline

1. Complete and save the current tracker correction with its paired replay.
2. Review player continuity and pitch landmarks; prioritize measured failures,
   not new model searches. Specialist ball sequence work remains paused.
3. Integrate supported map results only if geometry evidence permits. Otherwise,
   present the measured failure and the reason for abstention; do not fabricate maps.
4. Rehearse upload/review/export with the release candidate and document runtime.
5. Prepare the research narrative and figures, including the proposed paired-camera
   protocol. Freeze presentation evidence and rehearse before November 23.

Mac/Windows installers, public hosting, confirmed tackle/possession recognition and
validated full-match speed are outside this research deadline scope unless the user
explicitly changes the deliverable. Keep them on the longer-term product backlog.
Do not silently substitute synthetic success for a real-video result. If a synthetic
example explains the algorithm, label it as such.

## Proposed paired-camera study

Record the same play simultaneously with phone and reference camera; synchronize
frames, document viewpoint/resolution/frame rate and obtain necessary permissions.
Label visible players, ball visibility and identity independently. Use separate
matches for tuning and testing. Compare detection precision/recall, identity
continuity, landmark error and usable-position coverage. Speed accuracy additionally
needs an appropriate independent physical reference and synchronization assessment.
Report uncertainty and runtime, with missing/occluded observations handled explicitly.
No quantitative phone-camera accuracy loss can be claimed from current evidence.
