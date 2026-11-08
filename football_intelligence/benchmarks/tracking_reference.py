"""Image-space identity continuity diagnostics; no reference input to tracking."""
from collections import defaultdict
import numpy as np
from scipy.optimize import linear_sum_assignment
from ..validation import finite


def score_tracking(records, references, max_gap_s=.12):
    finite('max_gap_s',max_gap_s,minimum=.000001)
    previous = {}; previous_truth = set(); last_time = None; last_index = None
    total = matched = emitted = links = comparable = stable = eligible = switches = 0
    seen = defaultdict(set)
    durations = {}; longest = 0.; sustained = set()
    for row in records:
        timestamp, index = row['timestamp_s'], row['frame_index']
        if not np.isfinite(timestamp) or timestamp < 0:
            raise ValueError('Invalid timestamp')
        if last_time is not None and (timestamp <= last_time or index <= last_index):
            raise ValueError('Frames and timestamps must increase')
        truth = references[index]; keys = sorted(truth)
        items = [d for d in row['detections'] if d['kind'] == 'person']
        if len({d['track_id'] for d in items}) != len(items):
            raise ValueError('Duplicate track ID within a frame')
        total += len(keys); emitted += len(items)
        current = {}
        if keys and items:
            centers = np.array([[(d['bbox']['x_min']+d['bbox']['x_max'])/2,
                                 (d['bbox']['y_min']+d['bbox']['y_max'])/2] for d in items])
            cost = np.linalg.norm(np.array([truth[k] for k in keys])[:, None]-centers[None], axis=2)
            rows, cols = linear_sum_assignment(np.column_stack([cost, np.full((len(keys), len(keys)), 40.001)]))
            for i, j in zip(rows, cols):
                if j >= len(items) or cost[i, j] > 40:
                    continue
                rivals = np.r_[np.delete(cost[:, j], i), np.delete(cost[i], j)]
                if len(rivals) and rivals.min()-cost[i, j] < 10:
                    continue
                current[keys[i]] = items[j]
                seen[items[j]['track_id']].add(keys[i])
        matched += len(current)
        current_durations = {}
        if last_time is not None and timestamp-last_time <= max_gap_s+1e-6:
            links += len(set(truth) & previous_truth)
            for key in set(current) & set(previous):
                comparable += 1
                a, b = previous[key], current[key]
                same = a['track_id'] == b['track_id']
                stable += same; switches += not same
                safe = bool(same and a['confirmed'] and b['confirmed'] and b['continuity_safe']
                            and a['continuity_segment'] == b['continuity_segment'])
                eligible += safe
                if safe:
                    duration = durations.get(key,0.)+timestamp-last_time
                    current_durations[key] = duration
                    longest = max(longest,duration)
                    if duration >= 2.-1e-6:
                        sustained.add(key)
        durations = current_durations
        previous, previous_truth = current, set(truth)
        last_time, last_index = timestamp, index
    return dict(reference_observations=total, matched_observations=matched,
        emitted_person_observations=emitted, unmatched_emitted_observations=emitted-matched,
        reference_adjacent_links=links, matched_adjacent_links=comparable,
        same_id_adjacent_links=stable, eligible_same_id_links=eligible,
        adjacent_id_changes=switches, tracks_associated_with_multiple_references=sum(len(v)>1 for v in seen.values()),
        longest_eligible_continuity_s=longest,reference_players_with_two_second_continuity=len(sustained),
        observation_coverage=matched/total if total else None,
        eligible_link_coverage=eligible/links if links else None)
