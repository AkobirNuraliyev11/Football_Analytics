"""Score cached pitch-model predictions against separately reviewed image points."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.benchmarks.pitch_landmarks import compare_landmarks
from football_intelligence.model_assets import sha256

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('predictions',type=Path)
    parser.add_argument('references',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    result=compare_landmarks(json.loads(args.predictions.read_text()),json.loads(args.references.read_text()))
    result['input_sha256']={'predictions':sha256(args.predictions),'references':sha256(args.references)}
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps(result['modes'],indent=2))
