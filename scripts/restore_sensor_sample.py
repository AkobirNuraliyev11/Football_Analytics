"""Restore the pinned SoccerTrack validation sample. Downloads source data, renders no media."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

MANIFEST = Path(__file__).resolve().parents[1]/'evaluations/soccertrack-sample.json'


def verified_payload(payload, record):
    if len(payload) > record['bytes']+1024*1024:
        raise ValueError('Download exceeds expected size')
    if payload[:2] == b'PK':
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.infolist()
            if len(entries) != 1 or entries[0].file_size != record['bytes']:
                raise ValueError('Unexpected archive contents')
            payload = archive.read(entries[0])
    if len(payload) != record['bytes'] or hashlib.sha256(payload).hexdigest() != record['sha256']:
        raise ValueError('Sensor sample differs from pinned source')
    return payload


def restore(output):
    manifest = json.loads(MANIFEST.read_text())
    output.mkdir(parents=True, exist_ok=True)
    for record in manifest['files']:
        target = output/Path(record['file']).name
        if target.exists():
            payload = target.read_bytes()
            if len(payload) != record['bytes'] or hashlib.sha256(payload).hexdigest() != record['sha256']:
                raise ValueError('Existing sample differs from pinned source; refusing to overwrite')
        else:
            with urllib.request.urlopen(record['url'], timeout=45) as response:
                payload = response.read(record['bytes']+1024*1024+1)
            payload = verified_payload(payload, record)
            with target.open('xb') as stream:
                stream.write(payload)
        print('Verified', target, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('data/soccertrack-reference'))
    restore(parser.parse_args().output)
