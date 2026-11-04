"""Restore the exact public development videos; verify before publishing files."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from football_intelligence.model_assets import sha256

SOURCE = "https://github.com/roboflow/sports/blob/main/examples/soccer/setup.sh"
SAMPLES = {
    "first": {"upstream_name": "0bfacc_0.mp4", "drive_id": "12TqauVZ9tLAv8kWxTTBFWtgt2hNQ4_ZF",
        "path": "data/demo-step-04/source.mp4",
        "sha256": "43d342c78fbb40e522f48ab378fbee83b5b880d35c056836e0d493ec2b15ee51"},
    "second": {"upstream_name": "2e57b9_0.mp4", "drive_id": "19PGw55V8aA6GZu5-Aac5_9mCy3fNxmEf",
        "path": "data/tracking-review/second-source.mp4",
        "sha256": "7788719b32b944e42d8f1024fb4802f681bc2053d6301218a5bff6705b549f96"},
}


def restore(root, downloader=None):
    if downloader is None:
        import gdown
        downloader = gdown.download
    result = {"source": SOURCE, "samples": {}}
    for name, sample in SAMPLES.items():
        target = root / sample["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if sha256(target) != sample["sha256"]:
                raise ValueError(f"Existing {name} sample differs; refusing to overwrite")
        else:
            partial = target.with_suffix(".partial.mp4")
            if downloader(id=sample["drive_id"], output=str(partial), quiet=True, use_cookies=False) is None:
                raise ValueError(f"Download failed for {name}")
            if sha256(partial) != sample["sha256"]:
                raise ValueError(f"Unexpected {name} sample hash; partial file retained for inspection")
            partial.replace(target)
        result["samples"][name] = sample | {"bytes": target.stat().st_size, "verified": True}
        print(f"Verified {name}: {target}", flush=True)
    (root/"data/sample-sources.json").write_text(json.dumps(result, indent=2)+"\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    restore(args.root)
