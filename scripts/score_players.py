"""Evaluate labeled player frames; never infer labels from predicted identities."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from football_intelligence.benchmarks.player_metrics import score_players
from football_intelligence.model_assets import sha256

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evaluation',type=Path)
    parser.add_argument('output',type=Path)
    a=parser.parse_args()
    data=json.loads(a.evaluation.read_text())
    result=score_players(data['frames'])
    result['evaluation_sha256']=sha256(a.evaluation)
    result['evaluation_notes']=data.get('notes','No provenance notes supplied')
    result['target']=.86
    result['acceptance_status']='not_certified_by_this_scorer'
    with a.output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))
