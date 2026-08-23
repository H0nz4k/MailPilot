"""Jednotná sada ikon: monolinkové SVG obarvené podle tématu.

Ikony leží v ``assets/ui`` s černou kresbou; barvu dostanou až za běhu,
takže stejný soubor slouží světlému i tmavému tématu.
"""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from gui_qt.theme import Palette
from runtime_paths import bundled_path


NAV_DAILY = "nav_daily"
NAV_CLOSING = "nav_closing"
NAV_SPECIAL = "nav_special"
NAV_BULK = "nav_bulk"
NAV_ADMIN = "nav_admin"
NAV_HELP = "nav_help"
CHEVRON_RIGHT = "chevron_right"
CHEVRON_DOWN = "chevron_down"
TABLE_EMPTY = "table_empty"


@lru_cache(maxsize=64)
def _pixmap(name: str, color: str, size: int, ratio: float) -> QPixmap:
    renderer = QSvgRenderer(str(bundled_path("assets", "ui", f"{name}.svg")))
    pixmap = QPixmap(max(8, int(round(size * ratio))), max(8, int(round(size * ratio))))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    # Painter pracuje v logických pixelech, kreslí se tedy do velikosti ikony.
    logical = QRectF(0, 0, size, size)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter, logical)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(logical, QColor(color))
    painter.end()
    return pixmap


def themed_icon(
    name: str, color: str, size: int = 16, ratio: float = 2.0
) -> QIcon:
    """Ikona v zadané barvě; kreslí se ve dvojnásobku kvůli DPI."""
    return QIcon(_pixmap(name, color, size, ratio))


@lru_cache(maxsize=16)
def stylesheet_icon_path(name: str, color: str, size: int) -> str:
    """QSS umí jen soubor, obarvenou ikonu proto uložíme do dočasné složky."""
    directory = Path(tempfile.gettempdir()) / "autoreport-ui"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{name}_{color.lstrip('#')}_{size}.png"
    if not target.is_file():
        _pixmap(name, color, size, 2.0).save(str(target))
    return target.as_posix()


def nav_icon(name: str, palette: Palette, size: int = 16) -> QIcon:
    """Ikona navigace v barvě běžného textu."""
    return themed_icon(name, palette.text, size)


def muted_icon(name: str, palette: Palette, size: int = 16) -> QIcon:
    """Ikona pro sekundární prvky (chevrony, prázdné stavy)."""
    return themed_icon(name, palette.muted, size)
