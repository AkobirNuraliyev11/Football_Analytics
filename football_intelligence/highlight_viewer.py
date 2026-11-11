"""Local candidate playlist and observed-frame overlays. No inferred positions."""
from html import escape
import json
import re

LABELS = {'sprint_candidate': 'Sprint candidate', 'duel_candidate': 'Duel candidate'}


def active_events(events, window, timestamp_s):
    return [e for e in events if e['event_id'] in window['event_ids']
            and e['shot_id'] == window['shot_id']
            and e['start_s']-1e-9 <= timestamp_s <= e['end_s']+1e-9]


def overlay_candidate(rgb, frame, events, window):
    import cv2
    from .validation import finite
    output = rgb.copy()
    active = active_events(events, window, frame['timestamp_s'])
    ids = {identity for e in active for identity in e['track_ids']}
    height, width = output.shape[:2]
    for item in frame['detections']:
        if item['track_id'] not in ids or item.get('bbox') is None:
            continue
        b = item['bbox']
        coords = [b[k] for k in ('x_min','y_min','x_max','y_max')]
        for value in coords: finite('overlay coordinate',value)
        x1,y1,x2,y2 = coords
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError('Overlay box falls outside source raster')
        cv2.rectangle(output,(int(x1),int(y1)),(min(width-1,int(x2)),min(height-1,int(y2))),(255,205,80),2)
        cv2.putText(output,f'#{item["track_id"]}',(int(x1),max(12,int(y1)-4)),
                    cv2.FONT_HERSHEY_SIMPLEX,.45,(255,205,80),1)
    title = ' / '.join(dict.fromkeys(LABELS[e['kind']] for e in active)) if active else 'Context padding'
    title += f' | source {frame["timestamp_s"]:.2f}s'
    scale = min(.65, max(.15, width/1200))
    text_width = cv2.getTextSize(title,cv2.FONT_HERSHEY_SIMPLEX,scale,1)[0][0]
    scale *= min(1.,(width-8)/max(1,text_width))
    bar_height = min(height, max(16,round(35*width/1280)))
    cv2.rectangle(output,(0,0),(width-1,bar_height-1),(20,27,40),-1)
    cv2.putText(output,title,(4,bar_height-5),cv2.FONT_HERSHEY_SIMPLEX,scale,(255,230,170),1)
    return output


def write_viewer(directory, result):
    """Self-contained HTML with relative MP4 links; no scripts or remote assets."""
    by_id = {e['event_id']:e for e in result['events']}
    clips, cards = [], []
    for window in result['windows']:
        filename = window['file']
        if not re.fullmatch(r'clip-[0-9]{4,}\.mp4',filename):
            raise ValueError('Playlist requires generated local clip filenames')
        cues = []
        for identity in window['event_ids']:
            e = by_id[identity]
            cues.append(dict(event_id=identity,kind=e['kind'],label=LABELS[e['kind']],
                track_ids=e['track_ids'],truncated=e.get('truncated',False),
                source_start_s=e['start_s'],source_end_s=e['end_s'],
                clip_start_s=max(0.,e['start_s']-window['start_s']),
                clip_end_s=min(window['end_s'],e['end_s'])-window['start_s']))
        clips.append(dict(clip_id=window['clip_id'],file=filename,sha256=window['sha256'],
            shot_id=window['shot_id'],source_start_s=window['start_s'],source_end_s=window['end_s'],
            frame_count=window['frame_count'],events=cues))
        rows = ''.join('<li>'+escape(f'{e["label"]} #{e["event_id"]} · local tracks '+
                ', '.join(map(str,e['track_ids']))+f' · clip {e["clip_start_s"]:.2f}–{e["clip_end_s"]:.2f}s'+
                (' · cut short at a recording or measurement boundary' if e['truncated'] else ''))+'</li>' for e in cues)
        cards.append(f'<article><h2>Clip {window["clip_id"]}</h2><p>Source {window["start_s"]:.2f}–'
            f'{window["end_s"]:.2f}s · shot {window["shot_id"]}</p>'
            f'<video controls preload="none" playsinline aria-label="Clip {window["clip_id"]}" src="{filename}"></video>'
            f'<ul>{rows}</ul><a href="{filename}" download>Download clip</a></article>')
    playlist = dict(schema_version=1,status=result['status'],match_id=result['match_id'],
        source_sha256=result['source_sha256'],overlays_included=result['overlays_included'],
        audio_included=False,clips=clips,
        scope='Candidate events, not confirmed tackles or counterattacks. Local track IDs. '
              'Context padding is not event duration; end timestamps denote last selected frame start.')
    (directory/'playlist.json').write_text(json.dumps(playlist,indent=2,allow_nan=False)+'\n')
    empty = ('Measurements unavailable. No candidate clips can be shown.' if result['status']=='unavailable'
             else 'No qualifying candidates were found in the available measurements.')
    html = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Football candidate clips</title><style>
body{font:16px system-ui,sans-serif;background:#101722;color:#eaf0f8;margin:0;padding:24px;max-width:1100px;margin-inline:auto}
h1{font-size:28px}p,li{line-height:1.6;color:#becadb}a{color:#8bcdff}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:20px}
article{background:#1b2635;border:1px solid #354257;border-radius:12px;padding:20px}video{width:100%;background:#000;border-radius:8px}
</style><h1>Football candidate clips</h1>'''
    html += '<p>Match: '+escape(str(result['match_id']))+'</p>'
    html += '<p>Candidate events, not confirmed tackles or counterattacks. Track IDs are local. Clips are silent.</p>'
    html += '<main>'+(''.join(cards) if cards else '<p>'+empty+'</p>')+'</main></html>'
    (directory/'index.html').write_text(html,encoding='utf-8')
    return playlist
