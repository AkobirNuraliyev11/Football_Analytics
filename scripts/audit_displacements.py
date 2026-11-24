"""Decompose rejected position jumps without changing measurement eligibility."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from football_intelligence.calibration import transform
from football_intelligence.config import AppConfig
from football_intelligence.model_assets import sha256
from football_intelligence.tactical_io import input_frames
from football_intelligence.telemetry import TelemetryEngine


def decompose(previous_matrix, matrix, previous_anchor, anchor, dt):
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError('Positive finite interval required')
    old = transform(previous_matrix, [previous_anchor])[0]
    fixed = transform(matrix, [previous_anchor])[0]
    new = transform(matrix, [anchor])[0]
    anchor_delta, mapping_delta = new-fixed, fixed-old
    total = new-old
    return dict(interval_s=dt, anchor_delta_px=(np.array(anchor)-previous_anchor).tolist(),
        anchor_component_m=anchor_delta.tolist(), mapping_component_m=mapping_delta.tolist(),
        total_displacement_m=total.tolist(), apparent_speed_kmh=float(np.linalg.norm(total)/dt*3.6),
        anchor_component_norm_m=float(np.linalg.norm(anchor_delta)),
        mapping_component_norm_m=float(np.linalg.norm(mapping_delta)))


def audit(tracks, review):
    meta=json.loads((review/'manifest.json').read_text())
    if meta['status']!='completed' or meta['tracks_sha256']!=sha256(tracks):
        raise ValueError('Completed review for exact tracks required')
    engine=TelemetryEngine(AppConfig.from_dict(meta['config']),experimental=True)
    previous={}; jumps=[]
    with (review/'quality.jsonl').open() as quality:
        for frame,line in zip(input_frames(tracks,review),quality):
            matrix=json.loads(line)['matrix']; result=engine.update(frame); current={}
            for item,value in zip(frame['detections'],result['observations']):
                key=(frame['shot_id'],item['track_id']); old=previous.get(key)
                anchor=item.get('measurement_evidence',{}).get('anchor_px')
                if 'implausible_displacement' in value['reasons'] and old and anchor is not None:
                    old_matrix,old_anchor,old_time,old_index=old
                    jumps.append(dict(frame_index=frame['frame_index'],previous_frame_index=old_index,
                        timestamp_s=frame['timestamp_s'],track_id=item['track_id'],
                        **decompose(old_matrix,matrix,old_anchor,anchor,frame['timestamp_s']-old_time)))
                if value['fragment_id'] is not None and anchor is not None:
                    current[key]=(matrix,anchor,frame['timestamp_s'],frame['frame_index'])
            previous=current
    summary=engine.finish()
    return dict(source_sha256=meta['source_sha256'],tracks_sha256=sha256(tracks),
        quality_sha256=sha256(review/'quality.jsonl'),jumps=jumps,jump_count=len(jumps),
        affected_tracks=dict(Counter(j['track_id'] for j in jumps)),
        median_anchor_component_m=float(np.median([j['anchor_component_norm_m'] for j in jumps])) if jumps else None,
        median_mapping_component_m=float(np.median([j['mapping_component_norm_m'] for j in jumps])) if jumps else None,
        telemetry_summary=summary,
        scope='Exact vector decomposition, not error attribution or validated player speed. Mapping component includes legitimate camera compensation; anchor component includes actual player motion and gait. Vector norms must not be added. No gate changes, smoothing or missing-position filling.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('tracks',type=Path);p.add_argument('review',type=Path);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();result=audit(args.tracks,args.review)
    with args.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:result[k] for k in ('jump_count','median_anchor_component_m','median_mapping_component_m')}))
