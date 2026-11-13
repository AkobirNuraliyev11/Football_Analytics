"""Image-region context from current paint-checked overhead geometry only."""
from ..calibration import CalibrationError, transform


def ball_region(bbox, calibration, *, frame_index, width, height):
    # Do not trust a generic semantic fit, stale mapping or absent paint support.
    if (not calibration or calibration.get('method')!='overhead_boundaries_paint_checked'
            or not (calibration.get('image_evidence') or {}).get('accepted')
            or (calibration.get('frame_index'),calibration.get('width'),calibration.get('height'))
            != (frame_index,width,height)):
        return 'unknown'
    try:
        x,y=transform(calibration['matrix'],[[(bbox['x_min']+bbox['x_max'])/2,
                                             (bbox['y_min']+bbox['y_max'])/2]])[0]
        pitch=calibration['pitch']
        # Padding allows touchline play and modest elevation/parallax. This is
        # region screening, never a ground position or ball-depth estimate.
        return 'near_pitch' if -3<=x<=pitch['length_m']+3 and -3<=y<=pitch['width_m']+3 else 'outside_supported_pitch'
    except (CalibrationError, KeyError, TypeError, ValueError):
        return 'unknown'
