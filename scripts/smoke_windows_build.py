"""Run real frozen EXEs with isolated settings and no configured recipients/tasks."""
from pathlib import Path
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.web_branding import WEB_VERSION


def stop(process):
    if process.poll() is not None:
        return
    if sys.platform == 'win32':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, check=False)
    else:
        process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()


def smoke_service(app: Path, tmp: Path) -> None:
    from services.web_mail_nssm import _run_nssm, require_service_rights
    require_service_rights('install')
    service_dir = tmp / 'service'
    service_dir.mkdir()
    config = service_dir / 'config.json'
    shutil.copy2(ROOT / 'config.example.json', config)
    (service_dir / 'web_mail_tasks.json').write_text('{"version":1,"tasks":[]}', encoding='utf-8')
    name = f'DataShipBuildSmoke_{os.getpid()}'
    base = [str(app / 'nssm/win64/nssm.exe')]
    installed = False
    try:
        _run_nssm(base + ['install', name, str(app / 'DataShip-Worker.exe'), '--config', str(config), '--interval', '10'])
        installed = True
        _run_nssm(base + ['set', name, 'AppDirectory', str(service_dir)])
        _run_nssm(base + ['set', name, 'Start', 'SERVICE_DEMAND_START'])
        _run_nssm(base + ['start', name])
        deadline = time.monotonic() + 90
        logfile = service_dir / 'logy/web_mail_worker.log'
        while not logfile.exists() or 'scheduler started' not in logfile.read_text(encoding='utf-8'):
            if time.monotonic() > deadline:
                raise RuntimeError('NSSM service worker did not start in 90 seconds.')
            time.sleep(0.5)
        time.sleep(1)
        if 'ERROR' in logfile.read_text(encoding='utf-8'):
            raise RuntimeError('Worker reported an error under NSSM.')
        assert _run_nssm(base + ['status', name]).strip() == 'SERVICE_RUNNING'
    finally:
        if installed:
            try:
                _run_nssm(base + ['stop', name])
            finally:
                _run_nssm(base + ['remove', name, 'confirm'])
    print('Actual isolated NSSM install/start/status/stop/remove verified with no email tasks.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, default=ROOT / 'dist-web/DataShip')
    parser.add_argument('--service', action='store_true', help='Also install/start/remove an isolated temporary service; administrator required.')
    args = parser.parse_args()
    app = args.app.resolve()
    for executable in ['DataShip.exe', 'DataShip-Worker.exe']:
        version = subprocess.check_output([str(app / executable), '--version'], text=True, timeout=120)
        if WEB_VERSION not in version:
            raise RuntimeError(f'Incorrect version: {version}')
    with tempfile.TemporaryDirectory(prefix='dataship-smoke-') as tmp:
        tmp = Path(tmp)
        config = tmp / 'config.json'
        shutil.copy2(ROOT / 'config.example.json', config)
        (tmp / 'web_mail_tasks.json').write_text('{"version":1,"tasks":[]}', encoding='utf-8')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        log = ROOT / 'build/test-results/frozen-smoke.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open('w', encoding='utf-8') as output:
            gui = subprocess.Popen([str(app / 'DataShip.exe'), '--browser', '--port', str(port), '--config', str(config)],
                                   stdout=output, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 120
                while True:
                    if gui.poll() is not None:
                        raise RuntimeError('Frozen GUI exited; see frozen-smoke.log')
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=3) as r:
                            if r.status == 200 and b'DataShip' in r.read():
                                break
                    except (OSError, TimeoutError):
                        pass
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Frozen GUI did not serve the application within 120s.')
                    time.sleep(0.5)
            finally:
                stop(gui)
            worker = subprocess.Popen([str(app / 'DataShip-Worker.exe'), '--config', str(config), '--interval', '10'],
                                      stdout=output, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 90
                worker_log = tmp / 'logy/web_mail_worker.log'
                while not worker_log.exists() or 'scheduler started' not in worker_log.read_text(encoding='utf-8'):
                    if worker.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Frozen worker did not start; see frozen-smoke.log')
                    time.sleep(0.5)
                # Observe one scheduler tick with the empty, isolated task list.
                time.sleep(1)
                text = worker_log.read_text(encoding='utf-8')
                if 'ERROR' in text or worker.poll() is not None:
                    raise RuntimeError(text)
            finally:
                stop(worker)
        if args.service:
            smoke_service(app, tmp)
    print('Frozen GUI HTTP, worker startup and both version checks passed. No mail/tasks used.')


if __name__ == '__main__':
    main()
