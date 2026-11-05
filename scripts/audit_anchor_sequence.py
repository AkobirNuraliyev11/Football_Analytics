"""Compare visual shoe labels with box anchors and quantify interval pixel sensitivity."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from football_intelligence.config import AppConfig
from football_intelligence.model_assets import sha256
from football_intelligence.position_sensitivity import interval_sensitivity, pixel_square_radius
from football_intelligence.tactical_io import input_frames
from football_intelligence.telemetry import TelemetryEngine


def evaluate(tracks, review, reference):
    labels = json.loads(reference.read_text())
    manifest = json.loads((review/'manifest.json').read_text())
    before = {str(p): sha256(p) for p in [tracks, reference, review/'manifest.json', review/'quality.jsonl']}
    if (manifest.get('status') != 'completed' or manifest['tracks_sha256'] != before[str(tracks)]
            or labels['source_sha256'] != manifest['source_sha256']):
        raise ValueError('Need matching source labels and completed review of these tracks')
    samples = labels['samples']
    keys = [(s['frame_index'], s['track_id']) for s in samples]
    if not samples or len(set(keys)) != len(keys):
        raise ValueError('Need nonempty unique reference samples')
    quality = {r['frame_index']: r for r in map(json.loads, (review/'quality.jsonl').read_text().splitlines())}
    config = AppConfig.from_dict(manifest['config'])
    engine = TelemetryEngine(config, experimental=True, separate_identity_maturity=True)
    cached = {}
    for frame in input_frames(tracks, review):
        output = engine.update(frame)
        for item, value in zip(frame['detections'], output['observations']):
            key = frame['frame_index'], item['track_id']
            if key in keys:
                cached[key] = frame, item, value
    rows, internals = [], []
    for sample, key in zip(samples, keys):
        row = dict(sample, available=False, reason='track_unavailable')
        rows.append(row)
        internal = None
        if key in cached:
            frame, item, value = cached[key]
            row.update(timestamp_s=frame['timestamp_s'], shot_id=frame['shot_id'],
                       telemetry_status=value['status'], telemetry_reasons=value['reasons'])
            matrix = quality[key[0]]['matrix']
            if matrix is None:
                row['reason'] = 'geometry_unavailable'
            else:
                b = item['bbox']
                anchor = [(b['x_min']+b['x_max'])/2, b['y_max']]
                shoe, _ = pixel_square_radius(matrix, sample['pixel'], labels['uncertainty_px'])
                box, _ = pixel_square_radius(matrix, anchor, labels['uncertainty_px'])
                if max(np.linalg.norm(p-[config.pitch.length_m/2, config.pitch.width_m/2]) for p in (shoe, box)) > 9.15:
                    row['reason'] = 'outside_checked_midfield'
                else:
                    row.update(available=True, reason=None, box_anchor_px=anchor,
                        anchor_difference_px=float(np.linalg.norm(np.array(anchor)-sample['pixel'])),
                        anchor_difference_m=float(np.linalg.norm(box-shoe)))
                    # No interval may cross a quality gap, fragment, shot or track boundary.
                    internal = dict(frame=frame, value=value, matrix=matrix, anchor=anchor, sample=sample)
        internals.append(internal)
    intervals = []
    for i, a in enumerate(internals):
        if a is None: continue
        for b in internals[i+1:]:
            if b is None: continue
            if (a['sample']['track_id'] != b['sample']['track_id'] or
                    a['frame']['shot_id'] != b['frame']['shot_id'] or
                    a['value']['fragment_id'] is None or
                    a['value']['fragment_id'] != b['value']['fragment_id']):
                continue
            dt = b['frame']['timestamp_s']-a['frame']['timestamp_s']
            if dt <= 0: raise ValueError('Reference samples must increase per track')
            if not any(abs(dt-target)<1e-6 for target in (.2, .4, 1., 2.)):
                continue
            auto = interval_sensitivity(a['matrix'], a['anchor'], b['matrix'], b['anchor'], dt, labels['uncertainty_px'])
            manual = interval_sensitivity(a['matrix'], a['sample']['pixel'], b['matrix'], b['sample']['pixel'], dt, labels['uncertainty_px'])
            intervals.append(dict(start_frame=a['frame']['frame_index'], end_frame=b['frame']['frame_index'],
                track_id=a['sample']['track_id'], duration_s=dt, automatic=auto, visible_shoe=manual,
                proxy_speed_difference_kmh=abs(auto['nominal_net_speed_kmh']-manual['nominal_net_speed_kmh'])))
    if any(sha256(Path(p)) != value for p, value in before.items()):
        raise ValueError('Audit input changed during processing')
    return dict(source_sha256=labels['source_sha256'], input_sha256=before, samples=rows, intervals=intervals,
        labeled_samples=len(rows), available_samples=sum(r['available'] for r in rows),
        scope='Same-geometry comparison of different position proxies on development footage. '
              'Visible shoes do not establish contact. No independent metric-speed truth. '
              'Intervals require one continuous eligible experimental fragment, including warmup.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('tracks', 'review', 'reference', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    result = evaluate(args.tracks, args.review, args.reference)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
