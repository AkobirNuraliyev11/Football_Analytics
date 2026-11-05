"""Conditional pixel-localization sensitivity with geometry held fixed.

These bounds exclude calibration, camera, scale, identity and ground-contact errors.
They are deterministic perturbation bounds, not statistical confidence intervals.
"""
from .calibration import CalibrationError, transform
from .validation import finite


def pixel_square_radius(matrix, pixel, radius_px=3.):
    """Bound displacement over a pixel square under a finite projective mapping."""
    import numpy as np
    finite('radius_px', radius_px, minimum=0)
    matrix = np.asarray(matrix, dtype=float)
    pixel = np.asarray(pixel, dtype=float)
    if matrix.shape != (3, 3) or pixel.shape != (2,) or not np.isfinite(matrix).all() or not np.isfinite(pixel).all():
        raise ValueError('Need finite 3x3 mapping and two-dimensional pixel')
    corners = pixel + radius_px * np.array([[-1, -1], [-1, 1], [1, -1], [1, 1]])
    denominator = np.column_stack([corners, np.ones(4)]) @ matrix[2]
    if not ((denominator > 1e-10).all() or (denominator < -1e-10).all()):
        raise CalibrationError('Pixel uncertainty crosses the projection horizon')
    center = transform(matrix, [pixel])[0]
    # A same-sign projective map sends this square to a convex quadrilateral.
    radius = float(np.linalg.norm(transform(matrix, corners)-center, axis=1).max())
    return center, radius


def interval_sensitivity(matrix_a, pixel_a, matrix_b, pixel_b, duration_s, radius_px=3.):
    import numpy as np
    finite('duration_s', duration_s, minimum=0)
    if duration_s == 0:
        raise ValueError('Interval duration must be positive')
    a, ra = pixel_square_radius(matrix_a, pixel_a, radius_px)
    b, rb = pixel_square_radius(matrix_b, pixel_b, radius_px)
    distance = float(np.linalg.norm(b-a))
    sensitivity = (ra+rb)/duration_s*3.6
    speed = distance/duration_s*3.6
    return dict(duration_s=duration_s, nominal_net_speed_kmh=speed,
                pixel_only_speed_radius_kmh=sensitivity,
                pixel_only_speed_range_kmh=[max(0., speed-sensitivity), speed+sensitivity],
                endpoint_radii_m=[ra, rb], radius_px=radius_px,
                scope='Net endpoint displacement per time. Geometry held fixed. '
                      'Excludes calibration, camera, scale, identity and ground contact. '
                      'Not a confidence interval or instantaneous-speed validation.')
