"""Copy existing reviewed outputs into the frontend; no inference or video rendering."""
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.detection_quality import DetectionQuality

root = Path(__file__).resolve().parents[1]
source = root/'data/continuity-review'
out = root/'frontend/public/demo'
required = [source/'second-analysis/tracks.jsonl', source/'second-analysis/preview.mp4',
            source/'second-tactics/radar.jsonl', source/'second-tactics/occupancy.json']
if not all(p.is_file() for p in required):
    raise SystemExit('Cached demo unavailable. Live API mode still works; restore the reviewed data to prepare the demo.')
out.mkdir(parents=True, exist_ok=True)
tracks = [json.loads(l) for l in required[0].read_text().splitlines()]
radar = [json.loads(l) for l in required[2].read_text().splitlines()]
occupancy = json.loads(required[3].read_text())
# Retain only displayed fields, without machine-local paths or large geometry records.
frames = [{'frame_index': r['frame_index'], 'timestamp_s': r['timestamp_s'], 'shot_id': r['shot_id'],
           'detections': [{k:d.get(k) for k in ('track_id','kind','team','role','telemetry')} for d in r['detections']]} for r in tracks]
quality = DetectionQuality()
for row in tracks:
    quality.update(row["detections"])
heatmaps = []
for g in occupancy['groups']:
    name = f"heatmap-{g['id']}.png"
    shutil.copy2(source/'second-tactics'/name, out/name)
    heatmaps.append({'file':name,'identity':g['identity'],'observed_person_seconds':g['observed_person_seconds'],
                     'quality':'experimental_estimate'})
shutil.copy2(required[1], out/'match.mp4')
(out/'review.json').write_text(json.dumps({'title':'Broadcast sample · 6 seconds', 'frames':frames,'radar':radar,
    'heatmaps':heatmaps,'coverage':occupancy['coverage'],'pitch':occupancy['pitch'],'video':'match.mp4',
    'detection_quality':quality.summary(),'measurement_available':False,'events_status':'unavailable','events':[],
    'scope':'Cached real-video predictions; radar and occupancy are experimental estimates, not validated metrics.'}))
print('Prepared cached review without inference:', out)
