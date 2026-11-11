"""Strict event replay, shot-bounded clip planning, and explicitly invoked extraction."""
from contextlib import closing, nullcontext
from fractions import Fraction
import json
from pathlib import Path
import tempfile

from .config import AppConfig
from .events import EventEngine
from .model_assets import sha256
from .validation import finite


def plan_windows(events, frames, padding_s):
    """Return inclusive observed frame ranges. Padding never crosses a shot."""
    finite('padding_s', padding_s, minimum=0)
    shots = {}
    previous = None
    for row in frames:
        t, index, shot = row['timestamp_s'], row['frame_index'], row['shot_id']
        finite('timestamp_s', t, minimum=0)
        from .validation import integer
        integer('frame_index', index); integer('shot_id', shot)
        if previous and (t <= previous[0] or index != previous[1]+1 or shot < previous[2]):
            raise ValueError('Planning needs contiguous frames with increasing timestamps and shot IDs')
        shots.setdefault(shot, []).append(row)
        previous = t, index, shot
    windows = []
    seen = set()
    for event in events:
        if event['event_id'] in seen:
            raise ValueError('Duplicate event ID')
        seen.add(event['event_id'])
        if event.get('measurement_quality') != 'input_validated':
            raise ValueError('Highlight events require strict input quality')
        if event['kind'] not in ('sprint_candidate', 'duel_candidate'):
            raise ValueError('Unsupported event kind')
        start, end = event['start_s'], event['end_s']
        finite('event start', start, minimum=0); finite('event end', end, minimum=0)
        shot = shots.get(event['shot_id'], [])
        if not shot or end < start or start < shot[0]['timestamp_s']-1e-9 or end > shot[-1]['timestamp_s']+1e-9:
            raise ValueError('Event falls outside its observed shot')
        selected = [r for r in shot if start-padding_s-1e-9 <= r['timestamp_s'] <= end+padding_s+1e-9]
        if not selected:
            raise ValueError('Event window contains no observed frames')
        first, last = selected[0], selected[-1]
        windows.append(dict(shot_id=event['shot_id'], start_frame=first['frame_index'],
            end_frame=last['frame_index'], start_s=first['timestamp_s'], end_s=last['timestamp_s'],
            event_ids=[event['event_id']]))
    merged = []
    for window in sorted(windows, key=lambda w:w['start_frame']):
        if merged and window['shot_id'] == merged[-1]['shot_id'] and window['start_frame'] <= merged[-1]['end_frame']+1:
            old = merged[-1]
            if window['end_frame'] > old['end_frame']:
                old.update(end_frame=window['end_frame'], end_s=window['end_s'])
            old['event_ids'].extend(window['event_ids'])
        else:
            merged.append(dict(window))
    for number, window in enumerate(merged, 1):
        window.update(clip_id=number, file=f'clip-{number:04d}.mp4',
                      frame_count=window['end_frame']-window['start_frame']+1)
    return merged


def plan_highlights(analysis, *, padding_s=None):
    """Recompute strict events; never accept externally edited event eligibility."""
    analysis = Path(analysis)
    manifest_path, tracks = analysis/'manifest.json', analysis/'tracks.jsonl'
    hashes = {str(p):sha256(p) for p in (manifest_path, tracks)}
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('status') != 'completed' or not manifest.get('source_sha256'):
        raise ValueError('Need completed analysis with source provenance')
    config = AppConfig.from_dict(dict(schema_version=1, pitch=manifest['pitch'],
                                     analytics=manifest['analytics']))
    padding_s = config.analytics.highlight_padding_s if padding_s is None else padding_s
    engine, timing = EventEngine(config), []
    with tracks.open() as stream:
        for line in stream:
            row = json.loads(line)
            if row['match_id'] != manifest['match_id']:
                raise ValueError('Track match differs from analysis manifest')
            engine.update(row)
            timing.append({k:row[k] for k in ('frame_index','timestamp_s','shot_id')})
    if not timing or timing[0]['frame_index'] != 0 or len(timing) != manifest['processed_frames']:
        raise ValueError('Incomplete analysis records')
    result = engine.finish()
    windows = plan_windows(result['events'], timing, padding_s)
    if any(sha256(Path(p)) != digest for p,digest in hashes.items()):
        raise ValueError('Analysis changed during planning')
    return dict(schema_version=1, status=result['status'], match_id=manifest['match_id'],
        source_sha256=manifest['source_sha256'], analysis_sha256=hashes,
        padding_s=padding_s, events=result['events'], windows=windows,
        timeline=timing, audio_included=False, overlays_included=False,
        scope='Candidate clips only. Input quality assertions are not independently verified. '
              'Inclusive observed frame ranges; timestamps are relative to first decoded source frame. '
              'Padding is contextual footage, not additional validated event duration.')


def write_plan(analysis, output, *, padding_s=None):
    result = plan_highlights(analysis, padding_s=padding_s)
    with Path(output).open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return result


def extract_highlights(source, analysis, output, *, padding_s=None, overlays=False):
    """Explicit media action. Verify source/timing; atomically publish a new folder."""
    from .analysis import PreviewWriter
    from .video import iter_frames, probe_video
    from .highlight_viewer import overlay_candidate, write_viewer
    source, output = Path(source), Path(output)
    if output.exists():
        raise FileExistsError(output)
    plan = plan_highlights(analysis, padding_s=padding_s)
    if sha256(source) != plan['source_sha256']:
        raise ValueError('Video differs from the analyzed source')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.highlights-', dir=output.parent) as temporary:
        staging = Path(temporary)/'result'
        staging.mkdir()
        windows = plan['windows']
        if windows:
            metadata = probe_video(source)
            window_index, writer, count = 0, None, 0
            try:
                with closing(iter_frames(source)) as frames, \
                     ((Path(analysis)/'tracks.jsonl').open() if overlays else nullcontext()) as tracks:
                    for frame in frames:
                        observed = None
                        if tracks is not None:
                            line = tracks.readline()
                            if not line:
                                raise ValueError('Incomplete overlay records')
                            observed = json.loads(line)
                        expected = plan['timeline'][frame.frame_index]
                        if abs(expected['timestamp_s']-frame.timestamp_s) > 1e-6:
                            raise ValueError('Source timestamps differ from analysis')
                        if observed is not None and (observed['frame_index'] != frame.frame_index or
                            observed['shot_id'] != expected['shot_id'] or
                            abs(observed['timestamp_s']-frame.timestamp_s)>1e-6):
                            raise ValueError('Overlay records differ from source timing')
                        window = windows[window_index]
                        if frame.frame_index >= window['start_frame']:
                            if writer is None:
                                writer = PreviewWriter(staging/window['file'], metadata.width, metadata.height,
                                                       Fraction(metadata.average_rate or '25'))
                            rgb = overlay_candidate(frame.rgb, observed, plan['events'], window) if overlays else frame.rgb
                            writer.write(rgb, frame.timestamp_s-window['start_s'])
                            count += 1
                        if frame.frame_index == window['end_frame']:
                            writer.close(); writer = None
                            if count != window['frame_count']:
                                raise ValueError('Incomplete clip frame range')
                            window['sha256'] = sha256(staging/window['file'])
                            window_index += 1; count = 0
                            if window_index == len(windows):
                                break
                if window_index != len(windows):
                    raise ValueError('Source ended before planned clips were complete')
            finally:
                if writer is not None:
                    writer.close()
        if sha256(source) != plan['source_sha256'] or any(
                sha256(Path(p)) != digest for p,digest in plan['analysis_sha256'].items()):
            raise ValueError('Input changed during extraction')
        result = plan | dict(extraction_status='completed', clips_written=len(windows),
                             overlays_requested=overlays,overlays_included=bool(overlays and windows),
                             viewer_file='index.html',playlist_file='playlist.json')
        write_viewer(staging,result)
        result['viewer_sha256']={name:sha256(staging/name) for name in ('index.html','playlist.json')}
        (staging/'manifest.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
        if output.exists():
            raise FileExistsError(output)
        staging.rename(output)
    return result
