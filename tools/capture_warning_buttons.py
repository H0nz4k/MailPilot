"""Capture warning button state screenshots (OFF/ON)."""

from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui_qt.pages.advanced import AdvancedPage
from gui_qt.theme import apply_theme, metrics_for


OUTPUT = ROOT / "artifacts" / "screenshots_v12_8"


def main() -> int:
    app = QApplication.instance() or QApplication(["warning-capture"])
    apply_theme(app, "light", 1.0)
    page = AdvancedPage(metrics_for(1.0))
    page.setAttribute(Qt.WA_DontShowOnScreen, True)
    page.resize(1150, 720)
    page.show()
    app.processEvents()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    page.set_warning_active(False)
    app.processEvents()
    buttons = page._show_warning_btn.parentWidget() if page._show_warning_btn else page
    buttons.grab().save(str(OUTPUT / "warning_buttons_off.png"))

    page.set_warning_active(True)
    app.processEvents()
    buttons = page._show_warning_btn.parentWidget() if page._show_warning_btn else page
    buttons.grab().save(str(OUTPUT / "warning_buttons_on.png"))

    page.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
