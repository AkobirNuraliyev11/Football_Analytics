"""Run the built dashboard, local API and one worker until Ctrl-C. No cloud service."""
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    if not (ROOT/'frontend/dist/index.html').is_file():
        raise SystemExit('Build the dashboard first: cd frontend && npm ci && npm run build')
    import uvicorn
    from football_intelligence.api import create_app
    os.chdir(ROOT)
    token = os.environ.get('FOOTBALL_API_TOKEN') or secrets.token_urlsafe(32)
    print('\nDashboard: http://127.0.0.1:8000/dashboard/', flush=True)
    if 'FOOTBALL_API_TOKEN' not in os.environ:
        print('Temporary local API token (paste into Connection):\n'+token+'\n', flush=True)
    else:
        print('Use your FOOTBALL_API_TOKEN in Connection.\n', flush=True)
    worker = subprocess.Popen([sys.executable, '-m', 'football_intelligence', 'worker',
                               '--data-dir', 'data/backend'], cwd=ROOT)
    try:
        uvicorn.run(create_app(ROOT/'data/backend', token=token), host='127.0.0.1', port=8000)
    finally:
        if worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()


if __name__ == '__main__':
    main()
