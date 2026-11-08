"""Reject pitch hypotheses unsupported by visible paint; never certify accuracy."""
from .calibration import CalibrationError, transform


def marking_samples(pitch):
    import numpy as np
    length, width = pitch.length_m, pitch.width_m
    paths = {}
    def line(name, a, b):
        count = max(2, int(np.linalg.norm(np.array(a)-b)*2)+1)
        paths[name] = np.linspace(a, b, count)
    for x, name in [(0, 'left_goal'), (length/2, 'halfway'), (length, 'right_goal')]:
        line(name, (x, 0), (x, width))
    for y, name in [(0, 'far_touch'), (width, 'near_touch')]:
        line(name, (0, y), (length, y))
    for x, direction, name in [(0, 1, 'left'), (length, -1, 'right')]:
        for depth, half_width, box in [(16.5, 20.16, 'penalty'), (5.5, 9.16, 'goal')]:
            edge = x+direction*depth
            line(f'{name}_{box}_front', (edge, width/2-half_width), (edge, width/2+half_width))
            for sign in (-1, 1):
                y = width/2+sign*half_width
                line(f'{name}_{box}_side_{sign}', (x, y), (edge, y))
    angle = np.linspace(0, 2*np.pi, 116, endpoint=False)
    paths['circle'] = np.column_stack([length/2+9.15*np.cos(angle), width/2+9.15*np.sin(angle)])
    return paths


def paint_mask(rgb):
    """Narrow bright ridges with grass nearby; no geometry or reference input."""
    import cv2
    import numpy as np
    width = rgb.shape[1]
    colors = rgb.astype(np.float32)
    grass = ((colors[:, :, 1] > 1.1*colors[:, :, 0]) &
             (colors[:, :, 1] > 1.1*colors[:, :, 2])).astype(np.uint8)
    # Paint must have grass nearby, reducing stands, advertising and sky support.
    radius = max(3, round(width/320))
    nearby = cv2.dilate(grass, np.ones((2*radius+1, 2*radius+1), np.uint8)) > 0
    # Narrow bright ridges distinguish faded white paint from pale green turf.
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    local = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT,
                           cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*radius+1, 2*radius+1)))
    white = ((colors.min(2) > 100) & (colors.max(2)-colors.min(2) < .22*colors.max(2))
             & (local > 15) & nearby)
    return white


def paint_evidence(rgb, matrix, support_pixels, pitch):
    """Image-only check of projected regulation markings within calibrated support.

    Fixed conservative screen, not an optimized fit. Missing/occluded paint can
    cause abstention. Passing cannot verify semantic orientation or ground contact.
    """
    import cv2
    import numpy as np
    height, width = rgb.shape[:2]
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError as exc:
        raise CalibrationError('Singular pitch hypothesis') from exc
    white = paint_mask(rgb)
    distance = cv2.distanceTransform((~white).astype(np.uint8), cv2.DIST_L2, 3)
    hull = cv2.convexHull(np.asarray(support_pixels, dtype=np.float32))
    tolerance = max(3., width/640.)
    components = {}
    for name, samples in marking_samples(pitch).items():
        try:
            pixels = transform(inverse, samples)
        except CalibrationError:
            continue
        pixels = pixels[(pixels[:, 0] >= 0) & (pixels[:, 0] < width) &
                        (pixels[:, 1] >= 0) & (pixels[:, 1] < height)]
        pixels = np.array([p for p in pixels if cv2.pointPolygonTest(hull, tuple(p), False) >= 0])
        if len(pixels) < 12:
            continue
        # Avoid repeated samples artificially supporting collapsed projections.
        pixels = np.unique(pixels.astype(int), axis=0)
        if len(pixels) < 12:
            continue
        distances = distance[pixels[:, 1], pixels[:, 0]]
        components[name] = dict(samples=len(pixels), supported=int((distances <= tolerance).sum()),
                                fraction=float((distances <= tolerance).mean()))
    total = sum(c['samples'] for c in components.values())
    supported = sum(c['supported'] for c in components.values())
    fraction = supported/total if total else 0.
    good = sum(c['fraction'] >= .5 for c in components.values())
    accepted = total >= 60 and good >= 3 and fraction >= .65
    return dict(accepted=accepted, reason=None if accepted else 'insufficient_visible_pitch_paint_support',
                samples=total, supported_fraction=fraction, supported_components=good,
                tolerance_px=tolerance, components=components,
                scope='Image consistency screen only; physical accuracy and orientation unverified')


def require_pitch_paint(rgb, calibration):
    support = [[p.pixel.x, p.pixel.y] for p in calibration.landmarks if p.name in calibration.inlier_names]
    evidence = paint_evidence(rgb, calibration.matrix, support, calibration.pitch)
    if not evidence['accepted']:
        raise CalibrationError('Pitch fit rejected: insufficient visible pitch paint support')
    return evidence
