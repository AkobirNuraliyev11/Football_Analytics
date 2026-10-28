"""Explicit, cached model downloads from Roboflow's published soccer example."""
import hashlib
import json
from pathlib import Path

SOURCE = "https://github.com/roboflow/sports/blob/main/examples/soccer/setup.sh"
MODELS = {
    "players": ("football-player-detection.pt", "17PXFNlx-jI7VjVo_vQnB1sONjRyvoB-q"),
    "pitch": ("football-pitch-detection.pt", "1Ma5Kt86tgpdjCTKfum79YMgNnSjcoOyf"),
}
EXPECTED_SHA256 = {
    "players": "75b09c377fbf9d0791d23f6cfb689f5aed6eaa43a6818bd1fb884cf7507fffaf",
    "pitch": "28f68f7c4056d6d9b137efd2e7ab5f3c494039380c63831649126ced25628b36",
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_models(directory: Path):
    try:
        import gdown
    except ImportError as exc:
        raise ValueError('Install detection support: pip install -e ".[detection]"') from exc
    directory.mkdir(parents=True, exist_ok=True)
    result = {"source": SOURCE, "license_note": "Ultralytics models/runtime: AGPL-3.0 or applicable commercial license", "models": {}}
    for key, (filename, file_id) in MODELS.items():
        path = directory / filename
        if not path.exists():
            temporary = path.with_suffix(".download")
            downloaded = gdown.download(id=file_id, output=str(temporary), quiet=False, use_cookies=False)
            if downloaded is None or temporary.stat().st_size < 1_000_000:
                raise ValueError(f"Model download failed: {filename}")
            temporary.replace(path)
        digest = sha256(path)
        if digest != EXPECTED_SHA256[key]:
            raise ValueError(f"Unexpected model hash for {filename}; review upstream changes before use")
        result["models"][key] = {"file": filename, "sha256": digest, "bytes": path.stat().st_size}
    (directory / "model-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
