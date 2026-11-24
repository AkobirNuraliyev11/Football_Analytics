"""Paired opt-in motion trial: pixel-compatible jumps are not validated motion."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.telemetry import TelemetryEngine
from football_intelligence.tactical_io import input_frames
from football_intelligence.config import AppConfig
from football_intelligence.model_assets import sha256


def compare(tracks,review):
    meta=json.loads((review/'manifest.json').read_text())
    if meta['status']!='completed' or meta['tracks_sha256']!=sha256(tracks):raise ValueError('Completed review for exact tracks required')
    engines={name:TelemetryEngine(AppConfig.from_dict(meta['config']),experimental=True,
        separate_identity_maturity=True,uncertainty_aware_displacement=enabled)
        for name,enabled in [('baseline',False),('pixel_bound',True)]}
    rows=[]
    for frame in input_frames(tracks,review):
        for name,engine in engines.items():
            result=engine.update(frame)
            for value in result['observations']:
                if value['status']=='measured':rows.append(dict(method=name,frame_index=frame['frame_index'],timestamp_s=frame['timestamp_s'],**value))
    return dict(source_sha256=meta['source_sha256'],tracks_sha256=sha256(tracks),quality_sha256=sha256(review/'quality.jsonl'),
        summaries={k:e.finish() for k,e in engines.items()},measured_samples=rows,
        scope='Experimental pixel-only compatibility, not validated speed. Geometry and ground contact remain unverified. No interpolation. Conditional displacement eligibility changes: observed jumps can be retained when their assumed endpoint bounds permit physically plausible motion. Pairwise compatibility does not prove a globally consistent trajectory. Assumed pixel bounds are not independently measured.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('tracks',type=Path);p.add_argument('review',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=compare(a.tracks,a.review)
    with a.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
