"""Indexed, bounded result queries. Original quality labels and nulls are preserved."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

STREAMS = {'tracks': 'tracks.jsonl', 'telemetry': 'telemetry.jsonl', 'radar': 'tactics/radar.jsonl'}
SORTS = {'start_s', 'top_speed_kmh', 'observed_distance_m', 'sprint_count'}


def build_index(output, *, check=lambda: None):
    path = output / 'queries.sqlite3'
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE frames (kind TEXT, frame INTEGER, time REAL, payload TEXT, PRIMARY KEY(kind,frame))')
        db.execute('CREATE INDEX frames_time ON frames(kind,time,frame)')
        for kind, file in STREAMS.items():
            with (output / file).open() as source:
                for line in source:
                    check()
                    row = json.loads(line)
                    db.execute('INSERT INTO frames VALUES (?,?,?,?)',
                               (kind, row['frame_index'], row['timestamp_s'], line))
        db.execute('CREATE TABLE fragments (id INTEGER PRIMARY KEY, track_id INTEGER, start_s REAL, top_speed_kmh REAL, observed_distance_m REAL, sprint_count INTEGER, payload TEXT)')
        summary = json.loads((output / 'telemetry-summary.json').read_text())
        for row in summary['fragments']:
            db.execute('INSERT INTO fragments VALUES (?,?,?,?,?,?,?)', (row['fragment_id'],row['track_id'],
                row['start_s'],row['top_speed_kmh'],row['observed_distance_m'],row['sprint_count'],json.dumps(row)))
        db.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, payload TEXT)')
        plan = json.loads((output / 'highlight-plan.json').read_text())
        for row in plan['events']:
            db.execute('INSERT INTO events VALUES (?,?)', (row['event_id'], json.dumps(row)))
        check()


def query(output, kind, *, offset=0, limit=100, start_s=0., end_s=None,
          track_id=None, sort='start_s', descending=False):
    path = Path(output) / 'queries.sqlite3'
    if not path.is_file() or path.is_symlink():
        raise ValueError('This job has no query index; submit a new job to enable queries')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        if kind in STREAMS:
            sql = 'SELECT payload FROM frames WHERE kind=? AND time>=?'
            args = [kind, start_s]
            if end_s is not None:
                sql += ' AND time<=?'
                args.append(end_s)
            sql += ' ORDER BY frame'
        elif kind == 'fragments':
            if sort not in SORTS:
                raise ValueError('Unsupported fragment sort')
            sql, args = 'SELECT payload FROM fragments', []
            if track_id is not None:
                sql += ' WHERE track_id=?'
                args.append(track_id)
            sql += f' ORDER BY {sort} {"DESC" if descending else "ASC"}, id ASC'
        elif kind == 'events':
            sql, args = 'SELECT payload FROM events ORDER BY id', []
        else:
            raise ValueError('Unknown stream')
        rows = db.execute(sql+' LIMIT ? OFFSET ?', args+[limit+1, offset]).fetchall()
    more = len(rows) > limit
    return {'items': [json.loads(r[0]) for r in rows[:limit]],
            'offset': offset, 'limit': limit, 'next_offset': offset+limit if more else None}
