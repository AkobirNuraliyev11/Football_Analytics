# Diagnose a completed upload

Run without loading models or generating media:

```sh
.venv/bin/python scripts/diagnose_analysis.py data/backend/jobs/JOB_ID/analysis --output data/diagnosis.json
```

The output is created exclusively (existing reports are not overwritten). It
records frame counts, prediction diagnostics, person track IDs scoped to shots,
short tracks, gaps over 0.12 seconds, projection states and telemetry rejection
counts. The completed manifest's frame count must match the track records.

These counts are not detection accuracy or verified identity switches. More local
IDs can result from entrances/exits, officials, false detections or fragmentation.
A fitted pitch does not establish a validated physical coordinate system. Strict
radar, occupancy and events remain unavailable when positions fail their checks.
The separately prepared demo can contain experimental review outputs that the
normal strict upload path does not produce.

For geometry investigation, `review-measurements --help` describes the existing
experimental paint/foot review. Run without preview and with a bounded frame limit.
It may still reject all positions. Never promote candidate geometry merely to make
the dashboard nonempty. Keep uploaded footage and diagnostic reports local unless
sharing is explicitly requested.
