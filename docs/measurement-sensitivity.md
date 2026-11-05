# Player-anchor and speed-sensitivity audit

November 5, 2026. Data-only work. No generated viewing sample.

## What the new evidence shows

Twelve source frames, five frames apart, were visually reviewed for the same red-shirt
track in the first development clip. Lowest-visible-shoe points were marked before
computing comparison metrics. Labels have approximate +/-3-pixel coordinate uncertainty.
They are not contact labels, body-center positions, or independent metric ground truth.
The raw labels, provenance and per-sample results are in
`evaluations/anchor-sequence-reference.json` and `anchor-sequence-results.json`.

All 12 points fall within checked midfield geometry. Box-bottom and visible-shoe
proxies differ by 0.077–0.321 m when projected through the same saved mapping.
Their mean net-speed differences are 1.71 km/h over 0.2 s, 0.72 over 0.4 s, 0.38 over
1 s, and 0.59 over 2 s. There are respectively 11, 10, 7 and 2 overlapping intervals.
This tiny development sequence cannot establish generalized player-speed accuracy.

## What changed in the software

The visibility stage now records `pixel_localization_radius_m`: the greatest movement
of a projected point when either image coordinate changes by up to three pixels,
with the mapping held fixed. The calculation checks the four corners of that square
and rejects a square crossing the projective horizon. This is an explicit scenario
assumption, not a calibrated error model. The existing cardinal-direction gate and
its threshold are unchanged.

Telemetry propagates endpoint radii through its exact timestamp-weighted velocity
window. Its mean velocity telescopes to displacement between the current endpoint
and the interpolated window-start endpoint. The latter radius is interpolated with
the same time weights. Their sum divided by the elapsed time supplies a conservative
conditional speed radius, converted to km/h.

New observation fields:

- `speed_pixel_sensitivity_kmh`: conditional +/- speed radius.
- `speed_pixel_range_kmh`: nonnegative lower and upper values.
- Both remain null during warmup, withholding, or missing endpoint-radius evidence.

The bounds exclude camera/calibration, scale, identity, and ground-contact error.
They are not confidence intervals. They do not change nominal speed, eligibility,
sprint decisions, or the strict ground-contact gate. Distance uncertainty is not
estimated. Older saved reviews lack these radii until recomputed or audited explicitly.

## Replays on the two existing sources

| Quantity | First source | Second source |
| --- | ---: | ---: |
| Eligible experimental observations | 367 | 87 |
| Observations with new sensitivity bounds | 367 | 87 |
| Median conditional speed radius | 6.26 km/h | 6.84 km/h |
| 90th percentile radius | 6.68 km/h | 7.46 km/h |
| Bounds crossing the 18 km/h sprint threshold | 28 | 36 |
| Maximum change to nominal speed | 0 km/h | 0 km/h |

These counts are observations, not distinct sprints or independent trials. The
usual half-second window amplifies localization uncertainty. In the manually
reviewed sequence the median radius is 7.34 km/h over 0.4 s and 1.48 over 2 s.
Longer net-displacement intervals reduce this particular sensitivity, but hide turns
and acceleration. This result does not justify simply increasing smoothing or
publishing previously withheld measurements.

## Reproduce

Use unused output filenames:

```sh
.venv/bin/python scripts/audit_anchor_sequence.py data/continuity-review/first-analysis/tracks.jsonl data/continuity-review/first-geometry evaluations/anchor-sequence-reference.json data/anchor-audit.json
.venv/bin/python scripts/audit_speed_sensitivity.py data/continuity-review/first-analysis/tracks.jsonl data/continuity-review/first-geometry data/speed-audit.json
.venv/bin/python -m unittest discover -s tests -q
```

All 134 tests passed with no skips. New tests cover affine units, projective bounds,
projection-horizon rejection, invalid inputs, variable-time endpoint interpolation,
and absent uncertainty evidence. Download tests verify pinned hashes and reject
unexpected archive contents. Actual replays verify unchanged eligibility and speed.

## Independent reference acquisition and next gate

The [SoccerTrack paper](https://openaccess.thecvf.com/content/CVPR2022W/CVSports/html/Scott_SoccerTrack_A_Dataset_and_Tracking_Algorithm_for_Soccer_With_Fish-Eye_CVPRW_2022_paper.html)
describes synchronized football video and wearable GNSS data. The author's
[dataset](https://www.kaggle.com/datasets/atomscott/soccertrack), version 6,
supplies a first 30-second GNSS file, drone video and annotations, and separate GNSS/pitch
and image/pitch keypoints. These were downloaded for validation. Local files remain
under ignored `data/soccertrack-reference/`. The committed sample manifest records
URLs, version, hashes, acquisition status, and timing concerns.

The GNSS file has 307 rows but 298 unique timestamps spanning 29.9 seconds. Three
timestamps have conflicting repeated rows, creating nine non-increasing steps.
Two intervals span 0.2 s instead of 0.1 s. Do not silently average or discard conflicts
and then claim valid speed ground truth. The annotation file has 900 one-based frame
rows. The downloaded source decodes to 900 frames at 29.97 fps, ending at
29.996663 s. Use decoded timestamps rather than assuming exactly 30 fps. Its filename uses 20220220 while the GNSS filename uses 20200220. Verify the
published pairing and clock offset before comparison. GNSS measurements also have
sensor error and represent a wearable body location, not an instantaneous shoe point.

Next: validate synchronization and coordinate orientation, isolate unambiguous sensor
intervals, and compare camera-derived displacement against those intervals with
missing predictions retained. Do not tune clock offsets on the evaluation interval.
Reserve another sequence for final testing. The Step 8 foundation stays available,
but measurement validation is the active priority. Ground contact and actual speed
accuracy remain unresolved pending that comparison.

Restore the exact independent reference sample after a fresh clone with:

```sh
.venv/bin/python scripts/restore_sensor_sample.py
```

This retrieves approximately 36 MB and verifies pinned file hashes. It downloads
original source footage and generates no preview. GNSS-derived box annotations may
help establish identity correspondence, but must not be presented as an independent
camera-speed reference. Reference speed should come from the sensor series with
its own timing, noise and coordinate assumptions explicitly accounted for.
