#!/usr/bin/env python3
"""Vstupní bod MailPilotu v12.7: okno v PySide6 i běh bez GUI.

Bez přepínačů se otevře desktopové rozhraní. S přepínači ``--poctyemailem``,
``--zaverka_MMRRRR``, ``--zaverka_am`` nebo ``--z17_RRRR`` proběhne stejná
úloha bez okna, aby ji mohl volat plánovač úloh Windows i Jídelna.
"""

from __future__ import annotations

import os
import sys


# PyInstaller --windowed nemá konzolové streamy; knihovny je přesto mohou použít.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from runtime_paths import application_directory  # noqa: E402
from services.cli import parse_cli, run_headless  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    os.chdir(application_directory())
    request, rest = parse_cli(argv)
    if request.headless:
        return run_headless(request)
    # Qt se importuje až tady, aby běh bez GUI nepotřeboval PySide6.
    from gui_qt.app import main as gui_main

    return gui_main(rest)


if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()
    raise SystemExit(main())
