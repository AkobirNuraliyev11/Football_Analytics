"""Screen cached pitch hypotheses without model inference or video rendering."""
import argparse
import ast
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from football_intelligence.config import PitchConfig
from football_intelligence.model_assets import sha256
from football_intelligence.pitch_paint import paint_evidence
from football_intelligence.video import iter_frames


def run(root, baseline, output):
    import cv2
    import numpy as np
    if output.exists():
        raise FileExistsError(output)
    old = json.loads(baseline.read_text())
    source = root/'D_20220220_1_0000_0030.mp4'
    reference = root/'drone_keypoints.json'
    if sha256(source) != old['source_sha256'] or sha256(reference) != old['reference_sha256']:
        raise ValueError('Source/reference fingerprint mismatch')
    records = {r['frame_index']: r for r in old['frames']}
    pairs = json.loads(reference.read_text())
    pixels = np.array(list(pairs.values()), float)
    positions = np.array([ast.literal_eval(k) for k in pairs], float)
    cv2.setRNGSeed(0)
    control, _ = cv2.findHomography(pixels, positions, cv2.RANSAC, .5)
    result = []
    for frame in iter_frames(source):
        if frame.frame_index not in records:
            continue
        c = records[frame.frame_index]['calibration']
        support = [[p['pixel']['x'], p['pixel']['y']] for p in c['landmarks'] if p['name'] in c['inlier_names']]
        result.append(dict(frame_index=frame.frame_index,
            automatic=paint_evidence(frame.rgb, c['matrix'], support, PitchConfig(**c['pitch'])),
            reference_assisted_control=paint_evidence(frame.rgb, control, pixels, PitchConfig())))
        print(frame.frame_index, result[-1]['automatic']['supported_fraction'],
              result[-1]['reference_assisted_control']['supported_fraction'], flush=True)
        if frame.frame_index == max(records):
            break
    if len(result) != len(records):
        raise ValueError('Incomplete frame set')
    report = dict(source_sha256=old['source_sha256'], baseline_sha256=sha256(baseline),
        reference_sha256=old['reference_sha256'], frames=result, can_certify_real_speed=False,
        limits='Same three development frames. Reference-assisted control only checks whether visible '
               'paint can support known geometry; it is not an automatic calibration result. '
               'No reference coordinates enter the automatic paint screen.')
    with output.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'baseline', 'output'):
        parser.add_argument(key, type=Path)
    a = parser.parse_args()
    run(a.root, a.baseline, a.output)
