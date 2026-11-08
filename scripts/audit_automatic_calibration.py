"""Bounded automatic pitch check; reference landmarks are used only after inference.

This is a same-match diagnostic, not a physical-accuracy certification. No media
is generated and no reference geometry is supplied to the model or fitter.
"""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from football_intelligence.calibration import CalibrationError
from football_intelligence.detection import FootballDetector
from football_intelligence.model_assets import sha256
from football_intelligence.models import PixelPoint
from football_intelligence.video import iter_frames


def geometry_discrepancy(predicted, expected, length=105., width=68.):
    """Diagnostic symmetries never modify predictions or certify orientation."""
    import numpy as np
    if not predicted:
        return dict(symmetry_median_discrepancy_m={}, median_pair_distance_discrepancy_m=None)
    p, q = np.asarray(predicted), np.asarray(expected)
    variants = dict(identity=p, reverse_length=np.column_stack([length-p[:, 0], p[:, 1]]),
                    reverse_width=np.column_stack([p[:, 0], width-p[:, 1]]),
                    rotate_180=np.array([length, width])-p)
    medians = {k: float(np.median(np.linalg.norm(v-q, axis=1))) for k, v in variants.items()}
    a, b = np.triu_indices(len(p), 1)
    distances = np.abs(np.linalg.norm(p[a]-p[b], axis=1)-np.linalg.norm(q[a]-q[b], axis=1))
    return dict(symmetry_median_discrepancy_m=medians,
                median_pair_distance_discrepancy_m=float(np.median(distances)) if len(distances) else None)


def run(root, output, frames=(360, 390, 420)):
    import numpy as np
    import torch
    torch.set_num_threads(4)
    if output.exists():
        raise FileExistsError(output)
    spec = json.loads((Path(__file__).resolve().parents[1] /
                       'evaluations/soccertrack-sample.json').read_text())
    pinned = {Path(r['file']).name: r['sha256'] for r in spec['files']}
    source = root / 'D_20220220_1_0000_0030.mp4'
    reference = root / 'drone_keypoints.json'
    for path in (source, reference):
        if sha256(path) != pinned[path.name]:
            raise ValueError('Input differs from pinned source')
    detector = FootballDetector(Path('data/models'))
    predictions = []
    started = time.monotonic()
    # Complete predictions before reading any reference coordinates.
    for frame in iter_frames(source):
        if frame.frame_index not in frames:
            continue
        scope = dict(match_id='soccertrack-calibration-audit', shot_id=0,
                     frame_index=frame.frame_index)
        try:
            calibration = detector.calibrate(frame.rgb, **scope)
            reason = None
        except CalibrationError as exc:
            calibration, reason = None, str(exc)
        predictions.append((frame.frame_index, frame.timestamp_s, calibration, reason))
        print(f'Calibration {len(predictions)}/{len(frames)}: {reason or "fit"}', flush=True)
        if frame.frame_index == max(frames):
            break
    if len(predictions) != len(frames):
        raise ValueError('Incomplete frame set')
    pairs = [(ast.literal_eval(k), v) for k, v in json.loads(reference.read_text()).items()]
    results = []
    for index, timestamp, calibration, reason in predictions:
        errors, rejected = [], Counter()
        predicted_points, expected_points = [], []
        for expected, pixel in pairs:
            if calibration is None:
                rejected['calibration_unavailable'] += 1
                continue
            try:
                point = calibration.project(PixelPoint(*pixel), match_id=calibration.match_id,
                    shot_id=0, frame_index=index, width=calibration.width, height=calibration.height)
                errors.append(float(np.linalg.norm(np.array([point.x_m, point.y_m]) - expected)))
                predicted_points.append([point.x_m, point.y_m])
                expected_points.append(expected)
            except CalibrationError as exc:
                rejected[str(exc)] += 1
        results.append(dict(frame_index=index, timestamp_s=timestamp, reason=reason,
            calibration=calibration.to_dict() if calibration else None,
            reference_points=len(pairs), projected_points=len(errors), rejections=dict(rejected),
            **geometry_discrepancy(predicted_points, expected_points),
            median_landmark_discrepancy_m=float(np.median(errors)) if errors else None,
            p90_landmark_discrepancy_m=float(np.percentile(errors, 90)) if errors else None))
    report = dict(schema_version=1, status='completed', requested_frames=list(frames),
        source_sha256=pinned[source.name], reference_sha256=pinned[reference.name],
        models=detector.fingerprints, elapsed_seconds=time.monotonic()-started,
        frames_with_fit=sum(c is not None for _, _, c, _ in predictions),
        can_certify_real_speed=False, reference_supplied_to_predictions=False,
        limits='Same-match aerial diagnostic, not an independent match. Static publisher landmarks; '
               'camera motion and physical accuracy unverified. Canonical orientation is not aligned '
               'using reference data. No player tracking or speed evaluation.', frames=results)
    with output.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    run(args.root, args.output)
