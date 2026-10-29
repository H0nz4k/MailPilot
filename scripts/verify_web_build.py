"""Check windowed GUI and console worker identities before deploying a build."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.web_branding import WEB_BUILD


def verify(app: Path) -> None:
    app = app.resolve()
    with tempfile.TemporaryDirectory(prefix='.version-', dir=app.parent) as temporary:
        identity = Path(temporary) / 'gui-version.txt'
        subprocess.run([str(app / 'DataShip.exe'), '--version-file', str(identity)],
                       check=True, timeout=60, capture_output=True)
        versions = {
            'DataShip.exe': identity.read_text(encoding='utf-8').strip(),
            'DataShip-Worker.exe': subprocess.run(
                [str(app / 'DataShip-Worker.exe'), '--version'], check=True,
                timeout=60, capture_output=True, text=True, encoding='utf-8',
            ).stdout.strip(),
        }
    for name, version in versions.items():
        if not version.endswith(f' build {WEB_BUILD}'):
            raise ValueError(f'{name} nema ocekavane sestaveni {WEB_BUILD}: {version}')
        print(f'OVERENO: {name}: {version}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    args = parser.parse_args()
    try:
        verify(args.app)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'CHYBA: overeni EXE selhalo: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
