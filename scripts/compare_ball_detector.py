"""Bounded paired raw-ball inference; keeps labels separate from predictions."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.benchmarks.ball_detector import SpecialistBallDetector, BALL_SHA256
from football_intelligence.detection import FootballDetector
from football_intelligence.model_assets import sha256
from football_intelligence.video import iter_frames


def compare(source, output, frames, model_dir=Path('data/models')):
    frames=set(frames)
    if not frames or len(frames)>10 or min(frames)<0:
        raise ValueError('Choose between one and ten nonnegative frame indices')
    if output.exists():raise ValueError('Output already exists')
    baseline=FootballDetector(model_dir)
    specialist=SpecialistBallDetector(model_dir/'experimental/football-ball-detection.pt')
    rows=[]
    for frame in iter_frames(source):
        if frame.frame_index in frames:
            for mode in ('baseline','specialist_full','specialist_tiled'):
                start=time.perf_counter()
                items=(baseline.detect(frame.rgb) if mode=='baseline' else
                       specialist.detect(frame.rgb,tiled=mode=='specialist_tiled'))
                elapsed=time.perf_counter()-start
                row={'frame_index':frame.frame_index,'mode':mode,'seconds':elapsed,
                     'detections':[asdict(d) for d in items if d.kind=='ball']}
                rows.append(row)
                print(frame.frame_index,mode,len(row['detections']),round(elapsed,3),flush=True)
        if frame.frame_index>=max(frames):break
    if {r['frame_index'] for r in rows}!=frames:raise ValueError('Requested frame not in video')
    report={'source_sha256':sha256(source),'model_hashes':baseline.fingerprints|{'specialist_ball':BALL_SHA256},
            'rows':rows,'scope':'Raw candidate comparison, not temporal tracking or verified match-ball identity. '
            'CPU timings include warm-up; baseline also detects people. No labels enter inference.'}
    with output.open('x') as stream:json.dump(report,stream,indent=2)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--frames',type=int,nargs='+',required=True)
    p.add_argument('--model-dir',type=Path,default=Path('data/models'))
    a=p.parse_args();compare(a.source,a.output,a.frames,a.model_dir)
