"""Explain missing outputs and track continuity from a completed local analysis.

No inference, video rendering, or ground-truth accuracy claims. Output stays local.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def diagnose(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest['status'] != 'completed':
        raise ValueError('Diagnosis requires a completed analysis')
    tracks = defaultdict(list)
    association = Counter()
    projections = Counter()
    frames = 0
    with (directory / 'tracks.jsonl').open() as stream:
        for line in stream:
            row = json.loads(line)
            frames += 1
            for item in row['detections']:
                if item['kind'] != 'person':
                    continue
                tracks[(row['shot_id'], item['track_id'])].append(row['timestamp_s'])
                association[item.get('association_reason', 'unknown')] += 1
                projections[item.get('projection_state', 'unknown')] += 1
    if frames != manifest['processed_frames']:
        raise ValueError('Track records do not match completed manifest')
    telemetry = json.loads((directory / 'telemetry-summary.json').read_text())
    continuity = []
    for (shot, identity), times in tracks.items():
        # Observed runs only; no hidden interpolation through missing frames.
        gaps = [b - a for a, b in zip(times, times[1:])]
        continuity.append({'shot_id': shot, 'track_id': identity,
                           'observations': len(times),
                           'first_seen_s': times[0], 'last_seen_s': times[-1],
                           'gaps_over_0_12s': sum(gap > .120001 for gap in gaps)})
    return {'status': 'diagnosed', 'frames': frames,
            'frames_with_pitch_fit': manifest.get('frames_with_pitch_fit'),
            'detection_quality': manifest.get('detection_quality'),
            'person_track_count': len(tracks),
            'short_person_tracks_under_3_observations': sum(len(t) < 3 for t in tracks.values()),
            'association_reasons': dict(association), 'projection_states': dict(projections),
            'measurement_status': telemetry['status'],
            'measurement_rejections': telemetry['rejection_counts'],
            'person_tracks': continuity,
            'scope': 'Diagnostic counts, not detection precision, identity-switch accuracy or verified athlete counts. '
                     'Pitch fits do not establish validated calibration. Strict maps and events need eligible measurements.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('analysis', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = diagnose(args.analysis)
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(f'Diagnostic report saved to {args.output}')
