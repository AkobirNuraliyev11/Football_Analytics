from copy import deepcopy
import unittest

from football_intelligence.events import EventEngine
from test_telemetry import frame


def pair(t, *, distance=1., **changes):
    row = frame(t, x=0)
    other = deepcopy(row['detections'][0])
    other.update(track_id=2, team='B')
    other['pitch_position_candidate']['x_m'] += distance
    other.update(changes)
    row['detections'].append(other)
    return row


class EventTests(unittest.TestCase):
    def test_pair_is_single_candidate_after_maturity(self):
        engine = EventEngine()
        for i in range(31):
            engine.update(pair(i/10))
        engine.update(pair(3.1, distance=2))
        result = engine.finish()
        event, = result['events']
        self.assertEqual(event['kind'], 'duel_candidate')
        self.assertAlmostEqual(event['start_s'], 2)
        self.assertAlmostEqual(event['end_s'], 3)
        self.assertFalse(event['truncated'])
        self.assertEqual(result, engine.finish())
        with self.assertRaises(ValueError):
            engine.update(pair(3.2))

    def test_quality_identity_and_reference_boundaries_break_pairs(self):
        for changes in [dict(ground_contact_reliable=False), dict(continuity_segment=1),
                        dict(coordinate_reference_id='other'), dict(team='A'), dict(role='official')]:
            engine = EventEngine()
            for i in range(24):
                engine.update(pair(i/10))
            engine.update(pair(2.4, **changes))
            for i in range(25, 28):
                engine.update(pair(i/10))
            self.assertEqual(engine.finish()['events'], [])

    def test_missing_frames_shot_changes_and_time_gaps_break_pairs(self):
        for boundary in ['missing', 'shot', 'gap']:
            engine = EventEngine()
            for i in range(24):
                engine.update(pair(i/10))
            if boundary == 'missing':
                engine.update(frame(2.4, x=0))
            for i in range(25 if boundary != 'gap' else 28, 31):
                row = pair(i/10)
                if boundary == 'shot':
                    row['shot_id'] = 1
                engine.update(row)
            self.assertEqual(engine.finish()['events'], [])

    def test_sprints_exclude_officials_and_unverified_positions(self):
        for changes, expected in [({}, 1), ({'role':'official'}, 0),
                                  ({'ground_contact_reliable':False}, 0)]:
            engine = EventEngine()
            for i in range(31):
                engine.update(frame(i/10, x=.6*i, **changes))
            result = engine.finish()
            self.assertEqual(len(result['events']), expected)
            if expected:
                event = result['events'][0]
                self.assertEqual(event['kind'], 'sprint_candidate')
                self.assertAlmostEqual(event['peak_speed_kmh'], 21.6)
                self.assertTrue(event['truncated'])
            elif changes.get('ground_contact_reliable') is False:
                self.assertEqual(result['status'], 'unavailable')

    def test_exact_distance_and_short_encounters_do_not_qualify(self):
        for distance, length in [(1.3, 31), (1., 24)]:
            engine = EventEngine()
            for i in range(length):
                engine.update(pair(i/10, distance=distance))
            self.assertEqual(engine.finish()['events'], [])
