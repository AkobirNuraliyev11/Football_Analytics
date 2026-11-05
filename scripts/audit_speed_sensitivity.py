"""Replay saved experimental geometry with conditional pixel-speed bounds, without media."""
import argparse
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from football_intelligence.config import AppConfig
from football_intelligence.model_assets import sha256
from football_intelligence.position_sensitivity import pixel_square_radius
from football_intelligence.tactical_io import input_frames
from football_intelligence.telemetry import TelemetryEngine


def evaluate(tracks, review):
    paths = [tracks, review/'manifest.json', review/'quality.jsonl']
    hashes = {str(p):sha256(p) for p in paths}
    manifest = json.loads((review/'manifest.json').read_text())
    if (manifest['status'] != 'completed' or manifest['tracks_sha256'] != hashes[str(tracks)]
            or manifest.get('measurement_quality') != 'experimental_estimate'):
        raise ValueError('Need a completed experimental review of these exact tracks')
    config = AppConfig.from_dict(manifest['config'])
    baseline = TelemetryEngine(config, experimental=True, separate_identity_maturity=True)
    candidate = TelemetryEngine(config, experimental=True, separate_identity_maturity=True)
    radius, ambiguous, measured = [], 0, 0
    maximum_speed_change = 0.
    with (review/'quality.jsonl').open() as geometry:
        for frame in input_frames(tracks, review):
            quality = json.loads(next(geometry))
            old = baseline.update(copy.deepcopy(frame))
            for item in frame['detections']:
                evidence = item.get('measurement_evidence', {})
                if quality['matrix'] is not None and evidence.get('anchor_px') is not None:
                    _, value = pixel_square_radius(quality['matrix'], evidence['anchor_px'])
                    evidence['pixel_localization_radius_m'] = value
            new = candidate.update(frame)
            for a, b in zip(old['observations'], new['observations']):
                if a['status'] != b['status'] or a['fragment_id'] != b['fragment_id']:
                    raise ValueError('Sensitivity replay changed eligibility')
                if b['status'] != 'measured': continue
                measured += 1
                maximum_speed_change = max(maximum_speed_change, abs(a['speed_kmh']-b['speed_kmh']))
                value = b['speed_pixel_sensitivity_kmh']
                if value is not None:
                    radius.append(value)
                    low, high = b['speed_pixel_range_kmh']
                    ambiguous += low <= config.analytics.sprint_threshold_kmh < high
    if any(sha256(Path(p)) != digest for p, digest in hashes.items()):
        raise ValueError('Input changed during audit')
    return dict(source_sha256=manifest['source_sha256'], input_sha256=hashes,
        measured_observations=measured, observations_with_pixel_bounds=len(radius),
        median_pixel_speed_radius_kmh=float(np.median(radius)) if radius else None,
        p90_pixel_speed_radius_kmh=float(np.quantile(radius,.9)) if radius else None,
        intervals_straddling_sprint_threshold=ambiguous,
        maximum_nominal_speed_change_kmh=maximum_speed_change,
        scope='Conditional +/-3-pixel-square sensitivity at velocity-window endpoints. '
              'Fixed geometry, unverified contact. Not real-speed accuracy or confidence intervals. '
              'Sprint-threshold overlap is diagnostic and does not create sprint events.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('tracks','review','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args()
    result=evaluate(args.tracks,args.review)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
