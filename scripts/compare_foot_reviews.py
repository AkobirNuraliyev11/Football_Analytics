"""Compare foot-localization trials only when source, tracks and geometry match."""
import argparse
import json
from pathlib import Path


def compare(directories):
    shared=None;timing=None;results=[]
    for directory in map(Path,directories):
        m=json.loads((directory/'manifest.json').read_text())
        if m['status']!='completed':raise ValueError('Completed foot reviews required')
        identity=tuple(m[k] for k in ('source_sha256','tracks_sha256','quality_sha256'))
        if shared is not None and identity!=shared:raise ValueError('Source, tracks or geometry differ; rescore before comparing')
        shared=identity
        c=json.loads((directory/'comparison.json').read_text())
        rows=[json.loads(l) for l in (directory/'feet.jsonl').read_text().splitlines()]
        times=[(r['frame_index'],r['timestamp_s']) for r in rows]
        if len(rows)!=m['processed_frames'] or (timing is not None and times!=timing):raise ValueError('Review frame windows differ')
        timing=times
        runs={}
        for r in rows:
            for o in r['pose_estimates']['observations']:
                if o['fragment_id'] is not None:
                    run=runs.setdefault(o['fragment_id'],[r['timestamp_s'],r['timestamp_s']]);run[1]=r['timestamp_s']
        results.append(dict(review=directory.name,pose_image_size=m.get('pose_image_size',256),
            eligible_samples=sum(o['fragment_id'] is not None for r in rows for o in r['pose_estimates']['observations']),
            longest_fragment_s=max((b-a for a,b in runs.values()),default=0),
            measured_samples=c['pose']['measured_observations'],
            shoe_candidates=c['foot_status_counts'].get('shoe_candidate',0),
            box_samples=sum(o['fragment_id'] is not None for r in rows for o in r['baseline']['observations'])))
    if not results:raise ValueError('At least one review required')
    return dict(source_sha256=shared[0],tracks_sha256=shared[1],quality_sha256=shared[2],
        frames=len(timing),results=results,scope='Matched input availability comparison, not independent accuracy or verified ground contact.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('reviews',nargs='+',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=compare(a.reviews)
    with a.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
