"""Replay dense cached detections through the tracker; write JSON only."""
import argparse
import csv
from dataclasses import asdict
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from football_intelligence.benchmarks.tracking_reference import score_tracking
from football_intelligence.detection import Detection
from football_intelligence.model_assets import sha256
from football_intelligence.models import BoundingBox
from football_intelligence.tracking import MultiObjectTracker
from football_intelligence.video import iter_frames


def run(root, cache, output):
    if output.exists():
        raise FileExistsError(output)
    spec = json.loads((Path(__file__).resolve().parents[1]/'evaluations/soccertrack-sample.json').read_text())
    pinned = {Path(v['file']).name:v['sha256'] for v in spec['files']}
    source = root/'D_20220220_1_0000_0030.mp4'; label = root/'D_20220220_1_0000_0030.csv'
    proof = json.loads(cache.with_suffix('.manifest.json').read_text())
    if (proof['status'] != 'completed' or proof['detections_sha256'] != sha256(cache)
        or proof['source_sha256'] != sha256(source) or sha256(source) != pinned[source.name]
        or sha256(label) != pinned[label.name]):
        raise ValueError('Cache/source/reference provenance mismatch')
    records = list(map(json.loads, cache.read_text().splitlines()))
    if [r['frame_index'] for r in records] != proof['requested_frames']:
        raise ValueError('Incomplete cache')
    # Fixed contiguous dense segment, not the later half-second-spaced frames.
    cached = {r['frame_index']:r for r in records if r['frame_index'] <= 234}
    if sorted(cached) != list(range(0, 235, 3)):
        raise ValueError('Expected dense 79-frame segment')
    tracker = MultiObjectTracker(); predictions = []
    for frame in iter_frames(source):
        if frame.frame_index not in cached:
            continue
        row = cached[frame.frame_index]
        if abs(row['timestamp_s']-frame.timestamp_s) > 1e-6:
            raise ValueError('Timing mismatch')
        detections = [Detection(BoundingBox(**d['bbox']), d['confidence'], d['kind']) for d in row['detections']]
        tracked = tracker.update(detections, frame.rgb, timestamp_s=frame.timestamp_s, shot_id=0)
        predictions.append(dict(frame_index=frame.frame_index,timestamp_s=frame.timestamp_s,detections=[
            dict(bbox=asdict(t.detection.bbox), kind=t.detection.kind, track_id=t.track_id,
                 confirmed=confirmed, continuity_safe=t.continuity_safe, continuity_segment=t.continuity_segment)
            for t, confirmed in tracked]))
        if frame.frame_index == max(cached):
            break
    if len(predictions) != len(cached):
        raise ValueError('Incomplete replay')
    # References enter only after prediction; never assign tracker IDs from labels.
    with label.open() as stream:
        rows = list(csv.reader(stream))
    references = {}
    for row in rows[4:]:
        index = int(row[0])-1
        if index not in cached:
            continue
        references[index] = {}
        for col in range(1, len(rows[0]), 4):
            if rows[0][col] not in ('0', '1'):
                continue
            if rows[2][col:col+4] != ['bb_height','bb_left','bb_top','bb_width']:
                raise ValueError('Unexpected label schema')
            h, x, y, w = map(float, row[col:col+4])
            references[index][(rows[0][col], rows[1][col])] = [x+w/2,y+h/2]
    report = dict(frames=len(predictions), source_sha256=pinned[source.name], cache_sha256=sha256(cache),
        models=proof['models'], detector_mode=proof['mode'],
        reference_sha256=pinned[label.name], **score_tracking(predictions,references),
        can_certify_real_speed=False, reference_supplied_to_tracker=False,
        limits='79 cached original full-frame detector observations at about 10 Hz, one aerial shot, '
               'same-match development diagnostic. Not tiled-detector or full-frame-rate performance. '
               'Ambiguous image-space reference associations excluded. Adjacent ID changes exclude gaps; '
               'unmatched emitted observations may include officials/nonparticipants, not just false detections. '
               'No calibration, contact, team classification or physical speed validation.')
    with output.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('root','cache','output'):
        parser.add_argument(key,type=Path)
    a=parser.parse_args();run(a.root,a.cache,a.output)
