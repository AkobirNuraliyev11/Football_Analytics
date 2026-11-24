"""Build the private results explorer from saved evidence; no inference."""
import argparse,hashlib,json,shutil,subprocess
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def clean(v):
    if isinstance(v,dict):return {clean(k):clean(x) for k,x in v.items() if k.lower() not in {'token','api_token','password','secret','api_key'}}
    if isinstance(v,list):return [clean(x) for x in v]
    if isinstance(v,str):return v.replace(str(ROOT)+'/', '').replace('/Users/akobir/','[local]/')
    return v

def export(destination):
    out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    for p in (ROOT/'web/results').iterdir():
        if p.is_file():shutil.copy2(p,out/p.name)
    assets=out/'assets';assets.mkdir(exist_ok=True)
    evidence=out/'evidence';evidence.mkdir(exist_ok=True)
    root=ROOT/'data/upload-review';replay=root/'context-integrated-replay';geometry=root/'context-transport-measurements';maps=root/'published-position-maps'
    rows=[json.loads(l) for l in (replay/'tracks.jsonl').open()]
    radar=[json.loads(l) for l in (maps/'radar.jsonl').open()]
    occupancy=json.loads((maps/'occupancy.json').read_text());meta=json.loads((geometry/'manifest.json').read_text())
    source=ROOT/'data/backend/jobs/413e40e1-2318-4b13-90b2-331d2aab81fd/source.video'
    if hashlib.sha256(source.read_bytes()).hexdigest()!=meta['source_sha256']:raise ValueError('Video provenance mismatch')
    shutil.copy2(source,assets/'match.mp4')
    keep=('track_id','source_track_id','kind','bbox','team','role','role_candidate','role_evidence','classification_reason','confidence','continuity_safe','continuity_segment','association_reason','confirmed')
    frames=[dict(frame_index=r['frame_index'],timestamp_s=r['timestamp_s'],shot_id=r['shot_id'],detections=[{k:d[k] for k in keep if k in d} for d in r['detections']]) for r in rows]
    groups=[]
    for g in occupancy['groups']:
        filename='heatmap-'+g['id']+'.png';shutil.copy2(maps/filename,assets/filename)
        groups.append(dict(file='assets/'+filename,identity=g['identity'],observed_person_seconds=g['observed_person_seconds'],intervals=g['intervals']))
    counts=Counter();people=set()
    for r in rows:
        persons=[d for d in r['detections'] if d['kind']=='person'];balls=[d for d in r['detections'] if d['kind']=='ball']
        people.update(d['track_id'] for d in persons);counts['person_observations']+=len(persons);counts['ball_observations']+=len(balls)
        counts['frames_without_ball']+=not balls;counts['unsafe_person_observations']+=sum(not d.get('continuity_safe') for d in persons)
    counts['person_tracks']=len(people)
    catalog=[];selected=list((ROOT/'evaluations').glob('*.json'))+list(root.glob('*.json'))
    for folder in [replay,geometry,root/'context-integrated-measurements',root/'context-shoe-comparison',root/'context-ankle-proxy-comparison',root/'pose512-shoe-comparison',root/'pose256-current-geometry',maps]:selected+=list(folder.glob('*.json'))
    for p in sorted(set(selected)):
        if p.name in {'kit-features.json','official-kit-trial.json'}:continue
        relative=p.relative_to(ROOT).as_posix();name=hashlib.sha256(relative.encode()).hexdigest()[:12]+'.json'
        text=json.dumps(clean(json.loads(p.read_text())),indent=2,allow_nan=False);(evidence/name).write_text(text)
        catalog.append(dict(title=p.stem.replace('-',' ').replace('_',' '),path=relative,url='evidence/'+name,category='Historical evaluation' if relative.startswith('evaluations/') else 'Latest experiments',sha256=hashlib.sha256(text.encode()).hexdigest(),bytes=len(text.encode())))
    docs=[];commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    for p in sorted((ROOT/'docs').glob('*.md')):
        (evidence/p.name).write_text(clean(p.read_text()))
        docs.append(dict(title=p.stem.replace('-',' '),url='evidence/'+p.name,source='https://github.com/AkobirNuraliyev11/Football_Analytics/blob/'+commit+'/docs/'+p.name))
    manifest=dict(updated='2026-11-24',source_commit=commit,source_sha256=meta['source_sha256'],width=1280,height=720,fps=25,frames=frames,radar=radar,groups=groups,coverage=occupancy['coverage'],counts=dict(counts),pitch=occupancy['pitch'],video='assets/match.mp4',catalog=catalog,documents=docs,role_score=json.loads((replay/'role-score.json').read_text()),continuity=json.loads((root/'current-continuity-comparison.json').read_text()),measurements=json.loads((geometry/'summary.json').read_text()),events=json.loads((replay/'events.json').read_text()),motion_trial=json.loads((ROOT/'evaluations/uncertain-motion-nov24.json').read_text()),scope='Retained-detection replay. Experimental positions only; physical measurements unavailable.',excluded_artifacts=['Model weights, databases, credentials, raw feature dumps, and unavailable historical local videos'])
    (out/'results.json').write_text(json.dumps(clean(manifest),separators=(',',':'),allow_nan=False))
    with (evidence/'latest-tracks.jsonl').open('w') as f:
        for r in rows:f.write(json.dumps(clean(r),separators=(',',':'))+'\n')
    (evidence/'latest-radar.jsonl').write_text('\n'.join(json.dumps(clean(r)) for r in radar)+'\n')
    (evidence/'catalog.json').write_text(json.dumps(catalog,indent=2))
    print(json.dumps(dict(output=str(out),frames=len(frames),reports=len(catalog),documents=len(docs),maps=len(groups),radar_samples=occupancy['coverage']['radar_samples'])))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('destination',type=Path);export(p.parse_args().destination)
