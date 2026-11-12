"""Run the local dashboard and supervised worker; Ctrl-C stops both."""
import argparse
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def reserve_socket(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', port))
        sock.listen(128)
    except OSError as exc:
        sock.close()
        raise SystemExit(f'Cannot start dashboard on port {port}: {exc}. '
                         'Check the existing server or choose --port with another local port.') from exc
    return sock


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--data-dir',type=Path,default=ROOT/'data/backend')
    args=parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    if not (ROOT/'frontend/dist/index.html').is_file():
        raise SystemExit('Build the dashboard first: cd frontend && npm ci && npm run build')
    import uvicorn
    from football_intelligence.api import create_app
    data_dir=args.data_dir.resolve()
    os.chdir(ROOT)
    token = os.environ.get('FOOTBALL_API_TOKEN') or secrets.token_urlsafe(32)
    app=create_app(data_dir, token=token)
    # Bind before launching a worker. A busy port must not leave an orphan worker.
    with reserve_socket(args.port) as sock:
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=args.port))
        worker=subprocess.Popen([sys.executable,'-m','football_intelligence','worker',
                                 '--data-dir',str(data_dir)],cwd=ROOT)
        stopping=threading.Event()
        failed=threading.Event()
        def supervise():
            code=worker.wait()
            if not stopping.is_set():
                failed.set()
                print(f'Analysis worker stopped (exit {code}); stopping dashboard. '
                      'Check the worker error above before restarting.',file=sys.stderr,flush=True)
                server.should_exit=True
        threading.Thread(target=supervise,daemon=True).start()
        try:
            print(f'\nDashboard: http://127.0.0.1:{args.port}/dashboard/',flush=True)
            if 'FOOTBALL_API_TOKEN' not in os.environ:
                print('Temporary local API token (paste into Connection):\n'+token+'\n',flush=True)
            else:
                print('Use your FOOTBALL_API_TOKEN in Connection.\n',flush=True)
            server.run(sockets=[sock])
        finally:
            stopping.set()
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait()

        if failed.is_set():
            raise SystemExit(1)


if __name__ == '__main__':
    main()
