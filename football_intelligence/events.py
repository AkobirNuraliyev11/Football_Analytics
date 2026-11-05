"""Data-only event candidates from strict telemetry. No tackle or possession inference."""
from itertools import combinations
from math import hypot

from .telemetry import TelemetryEngine


class EventEngine:
    def __init__(self, config=None):
        self.telemetry = TelemetryEngine(config)
        self.active = {}
        self.events = []
        self.result = None

    def _end_pair(self, key, reason):
        row = self.active.pop(key)
        duration = row['end_s'] - row['start_s']
        if duration + 1e-9 >= self.telemetry.config.analytics.min_duel_duration_s:
            self.events.append(dict(row, kind='duel_candidate', duration_s=duration,
                                    end_reason=reason, truncated=reason != 'separated'))

    def update(self, frame):
        # Recompute the gates from observations. Do not trust supplied speed/event flags.
        measured = self.telemetry.update(frame)
        items = {item['track_id']: item for item in frame['detections']}
        eligible = {}
        for row in measured['observations']:
            item = items[row['track_id']]
            if (row['status'] == 'measured' and item.get('team') in {'A', 'B'}
                    and item.get('role') in {'outfield', 'goalkeeper'}):
                eligible[row['track_id']] = (item, row['fragment_id'])
        current = set()
        comparable = set()
        t = frame['timestamp_s']
        for a, b in combinations(sorted(eligible), 2):
            first, fa = eligible[a]
            second, fb = eligible[b]
            reference = first['coordinate_reference_id']
            if first['team'] == second['team'] or reference != second['coordinate_reference_id']:
                continue
            key = (frame['shot_id'], fa, fb)
            comparable.add(key)
            p, q = first['pitch_position_candidate'], second['pitch_position_candidate']
            distance = hypot(p['x_m']-q['x_m'], p['y_m']-q['y_m'])
            if distance >= self.telemetry.config.analytics.duel_distance_m:
                continue
            current.add(key)
            if key not in self.active:
                self.active[key] = dict(match_id=frame['match_id'], shot_id=frame['shot_id'],
                    track_ids=[a, b], fragment_ids=[fa, fb], coordinate_reference_id=reference,
                    start_s=t, end_s=t, min_separation_m=distance)
            else:
                row = self.active[key]
                row['end_s'] = t
                row['min_separation_m'] = min(row['min_separation_m'], distance)
        for key in list(self.active):
            if key not in current:
                self._end_pair(key, 'separated' if key in comparable else 'measurement_boundary')

    def finish(self):
        if self.result is not None:
            return self.result
        for key in list(self.active):
            self._end_pair(key, 'end_of_input')
        summary = self.telemetry.finish()
        for fragment in summary['fragments']:
            if fragment['team'] not in {'A', 'B'} or fragment['role'] not in {'outfield', 'goalkeeper'}:
                continue
            for sprint in fragment['sprints']:
                self.events.append(dict(sprint, kind='sprint_candidate',
                    match_id=fragment['match_id'], shot_id=fragment['shot_id'],
                    track_ids=[fragment['track_id']], fragment_ids=[fragment['fragment_id']],
                    coordinate_reference_id=fragment['coordinate_reference_id']))
        self.events.sort(key=lambda row: (row['start_s'], row['shot_id'], row['kind'], row['track_ids']))
        for index, row in enumerate(self.events, 1):
            row.update(event_id=index, measurement_quality='input_validated')
        self.result = dict(schema_version=1,
            status='available' if summary['measured_observations'] else 'unavailable',
            events=self.events, telemetry=summary,
            scope='Candidates on observed local tracks. Proximity does not establish a tackle. '
                  'Speed does not establish a counterattack. Input quality assertions are not independently verified.')
        return self.result
