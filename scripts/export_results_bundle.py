"""Package saved results into an offline gallery; never rerun inference or invent events."""
import argparse
import html
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from football_intelligence.model_assets import sha256


def export(output):
    output = output.resolve()
    if output.exists() or output.with_suffix('.zip').exists():
        raise FileExistsError('Choose a new output directory')
    # Select before creating output, so exports cannot recursively package themselves.
    selected = list((ROOT / 'evaluations').glob('*.json')) + list((ROOT / 'docs').glob('*.md'))
    selected += [ROOT / 'README.md', ROOT / 'docs/ORIGINAL_REQUEST.txt']
    for p in (ROOT / 'data').rglob('*'):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(ROOT / 'data')
        if rel.parts[0] in ('models', 'backend') or any('bundle' in part for part in rel.parts):
            continue
        if p.suffix in ('.json', '.jsonl', '.png', '.jpg', '.html'):
            selected.append(p)
        elif p.suffix == '.mp4' and (p.name == 'preview.mp4' or p.name.startswith(('clip-', 'tracking-'))):
            selected.append(p)
    output.mkdir(parents=True)
    inventory = []
    for source in sorted(set(selected)):
        relative = source.relative_to(ROOT)
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        inventory.append({'file': relative.as_posix(), 'bytes': target.stat().st_size, 'sha256': sha256(target)})
    def link(path, label):
        return f'<a href="{html.escape(path, quote=True)}">{html.escape(label)}</a>'
    def video(path, title, note):
        if not (output/path).exists():
            return f'<p>{html.escape(title)}: artifact not available locally.</p>'
        return f'<article><h3>{html.escape(title)}</h3><p>{html.escape(note)}</p><video controls preload="none" src="{path}"></video></article>'
    def maps(folder, label):
        occupancy = output/folder/'occupancy.json'
        if not occupancy.exists():
            return '<p>No saved heatmaps in this category.</p>'
        data = json.loads(occupancy.read_text())
        cards=[]
        for group in data['groups']:
            identity=group['identity']
            title=(f"Team {identity['team']}" if identity['type']=='team' else
                   f"Local track {identity['track_id']} · {identity.get('role','unknown')} · team {identity.get('team','unknown')}")
            file=f"{folder}/heatmap-{group['id']}.png"
            if not (output/file).is_file():
                continue
            cards.append(f'<article><h3>{html.escape(title)}</h3><p>{label} · {group["observed_person_seconds"]:.2f} observed person-seconds</p><a href="{file}"><img loading="lazy" src="{file}" alt="{html.escape(title)} occupancy heatmap"></a></article>')
        return '<div class="grid">'+''.join(cards)+'</div>'
    body='''<h1>Football Analytics — all saved results</h1>
<p>Results snapshot: 11 November 2026. This is an offline results gallery, not the future product dashboard.</p>
<div class="notice"><strong>Read the labels:</strong> Real-video tracking predictions exist. Trusted real-player speed, distance, sprint and tackle statistics do not yet exist. Experimental estimates and synthetic demonstrations are separate below. Missing results mean unavailable, not zero events.</div>
<nav><a href="#tracking">Tracking</a><a href="#heatmaps">Real heatmaps</a><a href="#telemetry">Speed & sprints</a><a href="#events">Tackles & events</a><a href="#synthetic">Synthetic demonstrations</a><a href="#archive">All files</a></nav>
<h2>Where the project stands</h2><p>Steps 1–8 have core software implementations; measurement accuracy remains open. Step 9 has a first backend milestone: uploads, persistent jobs, a worker, progress and result downloads. The last full suite passed 182 tests. The full dashboard and public deployment are not implemented.</p>
<h2 id="tracking">Real-video tracking, ball detection and classification</h2><p>Boxes and A/B team, role and local ID labels are predictions. A/B are not club names. Fragmented IDs are not unique athletes. Unavailable speed is shown as -- km/h.</p><div class="grid">'''
    body+=video('data/results-review/tracking-12s.mp4','First match — 12-second review','Saved analysis; 30 seconds were analyzed. No new inference.')
    body+=video('data/continuity-review/second-analysis/preview.mp4','Second match — 6-second analysis','Outfield, officials, goalkeeper and ball predictions where detected.')
    body+='</div><h2 id="heatmaps">All available real-video heatmaps</h2><p><strong>EXPERIMENTAL:</strong> Only 87 of 3,606 person observations (2.41%) supplied positions in this second-clip trial. These are sparse observed occupancy, not full-match movement, possession or pitch control. There is no valid team A map for this run. Empty data were not filled in.</p>'
    body+=maps('data/continuity-review/second-tactics','EXPERIMENTAL REAL VIDEO')
    body+=video('data/continuity-review/second-tactics/preview.mp4','Experimental real-video radar','Gaps intentionally stay empty. Positions and geometry are not independently validated.')
    body+='''<h2 id="telemetry">Real-video speed, distance and sprint outputs</h2><p><strong>Strict output: unavailable on both broadcast runs.</strong> No validated player leaderboard can be produced. Below are all five saved experimental fragments from the second clip, provided for inspection, not as verified athlete statistics. Fragment distances include eligible warmup samples; heatmaps count mature intervals only.</p><table><tr><th>Local ID</th><th>Role</th><th>Interval (s)</th><th>Estimated distance (m)</th><th>Estimated peak (km/h)</th><th>Fragment sprint candidates</th></tr>'''
    occupancy=json.loads((output/'data/continuity-review/second-tactics/occupancy.json').read_text())
    for r in occupancy['telemetry']['fragments']:
        body+=f'<tr><td>{r["track_id"]}</td><td>{html.escape(r["role"])}</td><td>{r["start_s"]:.2f}–{r["end_s"]:.2f}</td><td>{r["observed_distance_m"]:.2f}</td><td>{r["top_speed_kmh"]:.2f}</td><td>{r["sprint_count"]}</td></tr>'
    body+='''</table><h2 id="events">Tackles, duels, sprints and other events</h2><table><tr><th>Requested result</th><th>Actual state</th></tr>
<tr><td>Confirmed tackles</td><td>Not implemented. No tackle count or tackle clips exist.</td></tr>
<tr><td>Defensive duel candidates</td><td>Opposing-player proximity logic is implemented and unit-tested. No eligible candidates from the strict real-video runs. Proximity does not establish a tackle.</td></tr>
<tr><td>Real sprints and sprint clips</td><td>Unavailable because physical measurements do not pass quality checks. This does not mean nobody sprinted.</td></tr>
<tr><td>Synthetic sprint highlights</td><td>Two test clips available below. These are test footage, not real football events.</td></tr>
<tr><td>Counterattacks, possession, passes, shots, goals and xG</td><td>No event detectors or results for these features. A sprint is not proof of a counterattack.</td></tr>
<tr><td>Heatmap territory / pitch control</td><td>Observed occupancy only; no inferred control or possession.</td></tr></table>
<h2 id="synthetic">Synthetic demonstrations — not match statistics</h2><p>Known-motion track 1: 10.8 km/h, 24 m, zero sprints. Track 2: 21.6 km/h, 48 m, one sprint still active at the end of the 8-second fixture. This verifies calculations, not real-camera accuracy.</p>
<img class="chart" src="data/results-review/synthetic/telemetry-demo.png" alt="Synthetic speed and distance chart">'''
    body+=maps('data/results-review/synthetic/tactics','SYNTHETIC KNOWN MOTION')
    body+=video('data/results-review/synthetic/tactics/preview.mp4','Synthetic radar','Exact simulated coordinates; not real footage.')
    body+='<p>'+link('data/step08-browser-check/clips/index.html','Open synthetic candidate clip playlist')+'</p>'
    body+='''<h2>Geometry, contact, tracking and classification evaluations</h2><p>All reports and historical trials are below. Use corrected reference reports for the latest detection comparisons. Old GNSS comparisons are not physical speed ground truth. Overhead paint checks passed on 38 sampled frames; this does not validate athlete contact. The tiled aerial tracking diagnostic matched 330/682 reference observations and had 1.80 s maximum eligible continuity. Kit checks were small development reviews, not independent general accuracy measurements.</p>'''
    body+='<p>'+link('docs/current-results.md','Detailed written results report')+'</p>'
    body+='''<h2 id="archive">Complete file archive</h2><p>Includes all saved JSON/JSONL result and reference metadata, evaluation reports, rendered figures and derived preview clips found in the working copy. Historical results may use older methods. Raw input videos, model weights, backend credentials/databases and source code are excluded. Source code is in the GitHub repository. Each packaged file has a hash in bundle-manifest.json.</p>'''
    groups={}
    for row in inventory:
        path=row['file'];parts=Path(path).parts
        key='/'.join(parts[:2]) if parts[0]=='data' else parts[0]
        groups.setdefault(key,[]).append(row)
    for group,rows in sorted(groups.items()):
        body+=f'<details><summary>{html.escape(group)} ({len(rows)} files)</summary><ul>'
        for row in rows:
            body+='<li>'+link(row['file'],row['file'])+f' — {row["bytes"]:,} bytes</li>'
        body+='</ul></details>'
    css='''body{font:16px/1.6 system-ui;background:#101722;color:#e9eef6;max-width:1280px;margin:auto;padding:32px}h1,h2,h3{line-height:1.2}h2{margin-top:48px}a{color:#74dccc}nav{display:flex;flex-wrap:wrap;gap:20px;padding:20px 0}.notice{padding:22px;background:#30291b;border-left:4px solid #efbc63}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,390px),1fr));gap:24px}article{background:#192433;padding:20px;border-radius:12px}img,video{width:100%;height:auto;border-radius:8px}video{max-height:550px}.chart{max-width:1100px}table{border-collapse:collapse;width:100%;display:block;overflow:auto}td,th{text-align:left;border-bottom:1px solid #384454;padding:12px}th{color:#efbc63}details{padding:12px;background:#192433;margin:10px 0}summary{cursor:pointer}li{overflow-wrap:anywhere}p{max-width:1050px}'''
    (output/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>All Football Analytics Results</title><style>'+css+'</style><body>'+body+'</body></html>')
    (output/'bundle-manifest.json').write_text(json.dumps({'scope':'Saved outputs and reference metadata; not all requested product capabilities are implemented','files':inventory},indent=2))
    with zipfile.ZipFile(output.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=5) as archive:
        for p in sorted(output.rglob('*')):
            if p.is_file(): archive.write(p,Path(output.name)/p.relative_to(output))
    return {'files':len(inventory),'gallery':str(output/'index.html'),'zip':str(output.with_suffix('.zip')),'zip_bytes':output.with_suffix('.zip').stat().st_size}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(export(parser.parse_args().output),indent=2))
