# Step 2 — Video ingestion and timing

This module turns one local video stream into correctly timed RGB frames and a
reviewable timing/segment index. It does not yet detect players or calibrate a pitch.

## Engineering concepts

A codec stores presentation timestamps (PTS) as integer ticks. Each tick has a rational
duration called the time base. Source time is `PTS × time_base`; elapsed match-video
time is source time minus the first decoded frame's source time. For example, PTS
5000 at time base 1/1000 is 5 seconds; PTS 5040 is 5.04 seconds and becomes elapsed
time 0.04. The original PTS, exact rational time base, and source time are all retained.
This is video elapsed time, not the referee's match clock.

Nominal or average FPS is descriptive metadata, not the clock. A variable-rate stream
may have intervals of 0.04, 0.10, and 0.04 seconds. Computing time as frame index / FPS
would distort later speed estimates. The decoder emits frames in presentation order;
we require strictly increasing presentation times. Missing, duplicate, or backwards
times fail ingestion rather than silently inventing timestamps. Negative source origins
are permitted, but elapsed time always begins at zero.

The implementation follows [PyAV's time model](https://pyav.org/docs/stable/api/time.html)
and [RGB frame conversion API](https://pyav.org/docs/stable/api/video.html).

## Implementation

- `football_intelligence/video.py`: optional dependency loading, local-source validation,
  video-stream selection, metadata probing, rational clock validation, and RGB decoding.
- `football_intelligence/shots.py`: candidate visual cuts and timestamp-gap boundaries.
- `football_intelligence/ingestion.py`: source fingerprinting, streaming JSONL records,
  and atomically replaced status manifests.
- `football_intelligence/cli.py`: `probe-video` and `ingest-video` commands.
- `tests/test_video.py`: clock tests plus real lossless video encode/decode integration tests.

PyAV 16.x and NumPy 2.x are optional dependencies. Step 1 still works without them.
The implementation was exercised with PyAV 16.0.1 and NumPy 2.4.6. A separate `ffmpeg`
executable is not required for this module; PyAV provides the codec bindings.

## Running it

From the project root, install video support if it is not already available:

```sh
python3 -m pip install -e ".[video]"
python3 -m football_intelligence probe-video /absolute/path/to/match.mp4
python3 -m football_intelligence ingest-video /absolute/path/to/match.mp4 --match-id match-001 --output data/match-001/run-001
python3 -m unittest discover -s tests -v
```

`--video-stream 0` selects the first video stream (ordinal among video streams, not
the container stream index). Cover-art streams are rejected. Input must be a local file.
The output directory must not exist, which prevents accidental replacement of earlier runs.
No match footage is bundled; the test suite creates its own tiny synthetic fixture.

Two optional ingestion controls are available:

```sh
python3 -m football_intelligence ingest-video /absolute/path/to/match.mp4 --match-id match-001 --output data/match-001/run-002 --cut-threshold 0.30 --max-gap-s 0.25
```

These are ingestion controls, independent of Step 1's telemetry configuration. Future
pipeline orchestration must explicitly pass its desired gap policy to both modules.

For Python pipeline use:

```python
from contextlib import closing
from pathlib import Path
from football_intelligence.video import iter_frames

with closing(iter_frames(Path("/absolute/path/to/match.mp4"))) as frames:
    for frame in frames:
        # uint8 array, shape (height, width, 3), RGB channel order
        rgb = frame.rgb
        print(frame.frame_index, frame.timestamp_s, rgb.shape)
```

The generator holds the decoder open until exhausted or closed. Using `closing` ensures
cleanup even when a consumer breaks early. Frames retain native raster dimensions;
display rotation and non-square-pixel aspect corrections are not applied. Later
calibration must use this same raster, and any displayed overlays must apply the same
display transform. Midstream dimension changes are rejected. Audio is not decoded here.

## Candidate shot boundaries

For each frame, sample a fixed 64×36 RGB grid. The cut score is the average absolute
channel difference from the previous grid, divided by 255. It ranges from 0 to 1.
Scores at or above the threshold flag a candidate cut. A time interval strictly greater
than the gap limit also starts a new segment, even if the image is unchanged.

The first frame starts shot 0. Each subsequent boundary increments the shot ID once,
including when both a visual cut and timestamp gap occur. The JSONL includes the score
and reasons so boundaries can be reviewed. Shot IDs are conservative processing segments,
not assertions that the camera definitely changed.

This lightweight heuristic can misclassify flashes, close-ups, pans, or compression changes,
and miss similar-looking cuts or dissolves. It is not yet evaluated on football broadcasts.
Later calibration should also validate geometry and camera motion; this detector is not a
replacement for those checks. There is deliberately no cooldown that would suppress a
second genuine cut. It does not classify replay footage or distinguish live play.

## Output and failure behavior

`manifest.json` records the match/job IDs, source path and SHA-256, stream metadata,
decoder versions, parameters, UTC creation/completion times, decoded-frame count,
segment count, timestamp origin, and observed minimum/maximum frame intervals.
Declared duration and frame count can be missing or inaccurate; they are distinguished
from measured decoded-frame count. `last_frame_timestamp_s` is the last frame's start,
not the clip's end or the full duration of its final frame.

`frames.jsonl` has one record per decoded frame: frame index, PTS/time base, source and
elapsed times, frame interval, shot ID, boundary reasons, and cut score. Writing one
record at a time avoids collecting a full match's index or decoded pixels in RAM.
Reading the complete source for SHA-256 adds a sequential I/O pass.

While running, frame records use `frames.partial.jsonl`. Only a successful complete
decode renames it to `frames.jsonl` and publishes `status: completed`. Consumers must
check the manifest status before using output. On caught failures or Ctrl-C, the
manifest becomes `failed` and partial records remain for diagnostics. A force-killed
process can leave `running`; crash recovery and resume are not implemented yet. Preflight
errors such as unreadable video or invalid stream selection occur before creating a job.
The manifest is atomically replaced on the same filesystem; this is not a distributed
job queue or a guarantee against storage hardware failure.

Source size and modification time are checked across hashing/decoding to catch ordinary
concurrent changes. This is not a snapshot guarantee; callers must leave input files
unchanged while processing. Decoder-marked corrupt frames and explicit decoder errors
fail the job. A decoder may conceal damage without flagging it, so success is not proof
that the original video contains every expected frame.

## Verification

Tests cover nonzero origins, variable intervals, missing/duplicate/backwards timestamps,
real lossless decoding, a black-to-white synthetic cut, unchanged-image timestamp gaps,
bad inputs, invalid stream selection, output collision protection, manifest consistency,
and simulated midstream failure. Optional integration tests skip with an explicit message
if video dependencies are unavailable; clock and foundation tests remain runnable.

No athlete accuracy or real-match cut-detection accuracy is claimed by these tests.
Step 3 (pitch calibration) remains gated on user review.
