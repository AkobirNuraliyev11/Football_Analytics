"""Image-space landmark comparison; independent of a model's homography fit score."""
import math
from statistics import median


def compare_landmarks(predictions, references, *, confidence_threshold=.5):
    """Compare two modes on the same reviewed points, retaining missing predictions.

    Annotation radii express reviewer uncertainty, not statistical confidence.
    No pitch distance, athlete speed or geometry validation is inferred.
    """
    if not 0 <= confidence_threshold <= 1:
        raise ValueError('Confidence threshold must lie in [0, 1]')
    indexed = {}
    modes = set()
    for row in predictions:
        key = (row['mode'], row['frame'])
        if key in indexed:
            raise ValueError('Duplicate prediction frame/mode')
        indexed[key] = row.get('points', [])
        modes.add(row['mode'])
    if len(modes) != 2 or not references:
        raise ValueError('Need two modes and nonempty independent references')
    cases = []
    seen = set()
    for ref in references:
        key = (ref['frame'], ref['keypoint_index'])
        xy = ref['pixel']
        radius = ref['uncertainty_px']
        if (key in seen or type(key[0]) is not int or key[0] < 0
                or type(key[1]) is not int or not 0 <= key[1] < 32
                or len(xy) != 2 or not all(math.isfinite(v) for v in xy)
                or not math.isfinite(radius) or radius < 0):
            raise ValueError('Invalid or duplicate reviewed landmark')
        seen.add(key)
        errors = {}
        for mode in sorted(modes):
            points = indexed.get((mode, key[0]), [])
            point = points[key[1]] if key[1] < len(points) else None
            error = None
            if (point is not None and len(point) == 3
                    and all(math.isfinite(v) for v in point)
                    and confidence_threshold <= point[2] <= 1):
                error = math.dist(point[:2], xy)
            errors[mode] = {'error_px': error,
                            'review_uncertainty_interval_px':
                            [max(0., error-radius), error+radius] if error is not None else None}
        cases.append(dict(ref, predictions=errors))
    summaries = {}
    for mode in sorted(modes):
        values = [c['predictions'][mode]['error_px'] for c in cases]
        available = [v for v in values if v is not None]
        summaries[mode] = {'reference_count': len(values), 'available': len(available),
                           'missing': len(values)-len(available),
                           'median_error_px': median(available) if available else None,
                           'max_error_px': max(available) if available else None}
    return {'cases': cases, 'modes': summaries,
            'scope': 'Assistant-reviewed image landmarks on development footage. '
                     'Approximate labels; not independent human validation or physical accuracy. '
                     'Errors summarize available points; missing points remain in the denominator.'}
