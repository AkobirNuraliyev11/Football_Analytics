"""Score visually reviewed fixed crops, keeping unknown/missing predictions as errors."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.benchmarks.classification_reference import score_classification_review
from football_intelligence.model_assets import sha256

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('references','predictions','source_video','output'):parser.add_argument(name,type=Path)
    a=parser.parse_args()
    refs=json.loads(a.references.read_text())
    with a.predictions.open() as stream:
        result=score_classification_review(refs,map(json.loads,stream),source_sha256=sha256(a.source_video))
    result.update(references_sha256=sha256(a.references),predictions_sha256=sha256(a.predictions))
    with a.output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))
