"""Replay track JSONL into strict event candidate JSON. Never creates media."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from football_intelligence.events import EventEngine
from football_intelligence.model_assets import sha256
from football_intelligence.tactical_io import input_frames


def build_events(tracks, output):
    tracks, output = Path(tracks), Path(output)
    if output.exists():
        raise FileExistsError(output)
    before = sha256(tracks)
    engine = EventEngine()
    for frame in input_frames(tracks):
        engine.update(frame)
    result = engine.finish()
    if not result['telemetry']['processed_frames']:
        raise ValueError('Input contains no frames')
    if sha256(tracks) != before:
        raise ValueError('Input changed during event processing')
    result['tracks_sha256'] = before
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tracks', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build_events(args.tracks, args.output)
