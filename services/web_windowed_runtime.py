"""Keep diagnostics available when Windows launches DataShip without a console."""
from __future__ import annotations

import os
from pathlib import Path
import sys


def prepare_windowed_streams(directory: Path) -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        path = Path(directory) / 'logy' / 'dataship_web.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = path.open('a', encoding='utf-8', buffering=1)
    except OSError:
        # A read-only installation must still be able to open its settings.
        stream = open(os.devnull, 'w', encoding='utf-8')
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
