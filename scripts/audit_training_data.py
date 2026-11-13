"""Audit the existing pinned annotations without downloading or training a model."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.benchmarks.training_data import audit_soccertrack_csv
from football_intelligence.model_assets import sha256

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('annotations',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args()
    spec=json.loads((Path(__file__).resolve().parents[1]/'evaluations/soccertrack-sample.json').read_text())
    pins={Path(r['file']).name:r['sha256'] for r in spec['files']}
    digest=sha256(a.annotations)
    if digest!=pins.get(a.annotations.name):raise ValueError('Unrecognized annotation fingerprint')
    result=audit_soccertrack_csv(a.annotations)|{'annotation_sha256':digest}
    with a.output.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
