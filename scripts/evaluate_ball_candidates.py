"""Score reviewed retained ball candidates, not whole-frame detection recall."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from football_intelligence.model_assets import sha256


def evaluate(tracks, review):
    if sha256(tracks) != review['tracks_sha256']:
        raise ValueError('Reviewed tracks fingerprint mismatch')
    rows = {r['frame_index']:r for r in map(json.loads, tracks.read_text().splitlines())}
    samples = []
    keys = set()
    for label in review['candidates']:
        key = (label['frame_index'], label['track_id'])
        if key in keys or label['label'] not in ('ball','not_ball'):
            raise ValueError('Duplicate or invalid candidate label')
        keys.add(key)
        matches = [d for d in rows[key[0]]['detections'] if d['track_id']==key[1] and d['kind']=='ball']
        if len(matches)!=1:
            raise ValueError('Reviewed candidate missing or ambiguous')
        samples.append((matches[0]['confidence'], label['label']))
    reports = []
    for threshold in (0, .4, .5):
        reports.append(dict(confidence_threshold=threshold,
            retained_true_candidates=sum(c>=threshold and l=='ball' for c,l in samples),
            retained_false_candidates=sum(c>=threshold and l=='not_ball' for c,l in samples),
            rejected_true_candidates=sum(c<threshold and l=='ball' for c,l in samples)))
    return dict(reviewed_candidates=len(samples), thresholds=reports,
        scope='Assistant-reviewed development subset of retained candidates. '
              'Not independent labels, full-frame precision/recall or model accuracy. '
              'Missing detector outputs are not represented. No threshold is selected by this report.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('tracks','review','output'):p.add_argument(name,type=Path)
    a=p.parse_args()
    result=evaluate(a.tracks,json.loads(a.review.read_text()))
    result['review_sha256']=sha256(a.review)
    result['tracks_sha256']=sha256(a.tracks)
    with a.output.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
