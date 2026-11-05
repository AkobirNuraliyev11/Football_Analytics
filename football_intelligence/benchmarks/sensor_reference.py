"""Strict sampling of timestamped sensor coordinates without conflicting-row averaging."""
from bisect import bisect_left
from collections import Counter
import csv
from datetime import time
import math


class SensorSeries:
    def __init__(self, samples, max_gap_s=.100001):
        samples = list(samples)
        grouped = {}
        counts = Counter()
        self.max_gap_s = max_gap_s
        if not math.isfinite(max_gap_s) or max_gap_s <= 0:
            raise ValueError('Sensor gap limit must be positive and finite')
        for timestamp, point in samples:
            if not math.isfinite(timestamp) or len(point) != 2 or not all(math.isfinite(v) for v in point):
                raise ValueError('Sensor samples must be finite 2D coordinates with timestamps')
            grouped.setdefault(timestamp, set()).add(tuple(point))
            counts[timestamp] += 1
        self.conflicts = sorted(t for t, points in grouped.items() if len(points) > 1)
        self.times = sorted(t for t, points in grouped.items() if len(points) == 1)
        self.points = [next(iter(grouped[t])) for t in self.times]
        self.duplicate_rows = len(samples)-len(grouped)
        self.identical_duplicates = sum(counts[t]-1 for t, points in grouped.items() if len(points) == 1)

    def sample(self, timestamp):
        if not math.isfinite(timestamp):
            raise ValueError('Sample timestamp must be finite')
        if timestamp in self.conflicts or not self.times:
            return None
        index = bisect_left(self.times, timestamp)
        if index < len(self.times) and abs(self.times[index]-timestamp) <= 1e-8:
            return self.points[index]
        if index == 0 or index == len(self.times):
            return None
        a, b = self.times[index-1:index+1]
        if b-a > self.max_gap_s:
            return None
        if any(a <= t <= b for t in self.conflicts):
            return None
        fraction = (timestamp-a)/(b-a)
        return tuple(x+(y-x)*fraction for x, y in zip(self.points[index-1], self.points[index]))

    def interval(self, start, end):
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            raise ValueError('Sensor interval must have increasing finite times')
        a, b = self.sample(start), self.sample(end)
        if a is None or b is None or any(start <= t <= end for t in self.conflicts):
            return None
        timestamps = [start]+[t for t in self.times if start < t < end]+[end]
        if any(y-x > self.max_gap_s for x, y in zip(timestamps, timestamps[1:])):
            return None
        return a, b


def read_gnss(path):
    with path.open() as stream:
        rows = list(csv.reader(stream))
    if len(rows) < 5 or len(rows[0]) < 3 or (len(rows[0])-1)%2:
        raise ValueError('Invalid GNSS multi-header CSV')
    if any(len(row) != len(rows[0]) for row in rows):
        raise ValueError('Inconsistent GNSS columns')
    def seconds(text):
        value = time.fromisoformat(text)
        return value.hour*3600+value.minute*60+value.second+value.microsecond/1e6
    times = [seconds(row[0]) for row in rows[4:]]
    if any(b<a for a,b in zip(times,times[1:])):
        raise ValueError('GNSS clock moves backwards')
    origin = times[0]
    result = {}
    for col in range(1, len(rows[0]), 2):
        if rows[2][col:col+2] != ['Lat', 'Lon']:
            raise ValueError('Expected Lat/Lon column pair')
        key = rows[0][col], rows[1][col]
        if key in result or (rows[0][col+1],rows[1][col+1]) != key:
            raise ValueError('Duplicate or mismatched sensor identity columns')
        # Keypoint files use longitude, latitude order.
        result[key] = SensorSeries([(round(t-origin, 6), (float(row[col+1]),float(row[col])))
                                    for t,row in zip(times,rows[4:])])
    return origin, result
