"""Cache a bounded sensor-benchmark detection run, with no rendering or tracking claims."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.detection import FootballDetector
from football_intelligence.model_assets import sha256
from football_intelligence.video import iter_frames

DEFAULT_FRAMES = [300,315,330,600,615,630,780,795,810]


def run(root, output, *, mode='auto', frames=DEFAULT_FRAMES, tile_size=None):
    import torch
    torch.set_num_threads(4)
    source=root/'D_20220220_1_0000_0030.mp4'
    expected=json.loads((Path(__file__).resolve().parents[1]/'evaluations/soccertrack-sample.json').read_text())
    video_record=next(r for r in expected['files'] if r['file'].endswith('.mp4'))
    if sha256(source)!=video_record['sha256']:raise ValueError('Wrong benchmark video')
    if output.exists():raise FileExistsError(output)
    detector=FootballDetector(Path('data/models'))
    manifest=dict(status='running',source_sha256=video_record['sha256'],models=detector.fingerprints,
                  tile_size=tile_size,
                  mode=mode,requested_frames=frames,processed_frames=0)
    path=output.with_suffix('.manifest.json')
    if path.exists():raise FileExistsError(path)
    path.write_text(json.dumps(manifest,indent=2))
    before=time.monotonic()
    try:
        with output.open('x') as stream:
            for frame in iter_frames(source):
                if frame.frame_index not in frames:continue
                detected=detector.detect(frame.rgb,tile_size=0 if mode=='original' else tile_size)
                stream.write(json.dumps(dict(frame_index=frame.frame_index,timestamp_s=frame.timestamp_s,
                    detections=[dict(bbox=vars(d.bbox),kind=d.kind,confidence=d.confidence,
                                     role_candidate=d.role.value) for d in detected]))+'\n')
                stream.flush();manifest['processed_frames']+=1
                print(manifest['processed_frames'],'/',len(frames),'frames',flush=True)
                if frame.frame_index>=max(frames):break
        if manifest['processed_frames']!=len(frames):raise ValueError('Incomplete benchmark')
        manifest.update(status='completed',elapsed_seconds=time.monotonic()-before,detections_sha256=sha256(output))
    except BaseException as exc:
        manifest.update(status='failed',error=str(exc))
        raise
    finally:path.write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--mode',choices=['auto','original'],default='auto')
    p.add_argument('--tile-size',type=int)
    a=p.parse_args();run(a.root,a.output,mode=a.mode,tile_size=a.tile_size)
