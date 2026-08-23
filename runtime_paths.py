"""Cesty použitelné ze zdrojů i z přenosného PyInstaller buildu."""

from __future__ import annotations

import sys
from pathlib import Path


def application_directory() -> Path:
    """Adresář s EXE; při běhu ze zdrojů adresář tohoto modulu."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_path(*parts: str) -> Path:
    """Soubor přibalený PyInstallerem, případně soubor ve zdrojové složce."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    root = Path(bundle_root) if bundle_root else Path(__file__).resolve().parent
    return root.joinpath(*parts)
