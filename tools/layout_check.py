"""Vývojářský nástroj: kontrola nejmenší použitelné velikosti obrazovek.

Ověřuje, že se okno dá zmenšit na 1366×768 i při zvětšení rozhraní 160 %
a že obsah zůstane dostupný posuvníkem, ne oříznutý.

    python tools/layout_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

from gui_qt.app import create_application  # noqa: E402
from gui_qt.main_window import (  # noqa: E402
    PAGE_ADMIN,
    PAGE_BULK,
    PAGE_CLOSING,
    PAGE_DAILY,
    PAGE_SPECIAL,
    MainWindow,
)
from gui_qt.pages.admin import SECTIONS  # noqa: E402
from gui_qt.theme import apply_theme  # noqa: E402
from services.config_io import load_raw_config  # noqa: E402
from services.ui_settings import UI_SCALES, peek_ui_settings  # noqa: E402

TARGET = (1366, 768)
PAGES = (
    (PAGE_DAILY, "Denní stav"),
    (PAGE_CLOSING, "Uzávěrka"),
    (PAGE_SPECIAL, "Speciál"),
    (PAGE_BULK, "Hromadná zpráva"),
)


def _clipped(page) -> bool:  # noqa: ANN001 - Qt widget
    """Obsah bez posuvníku, který se nevejde, je oříznutý."""
    if page.findChildren(QScrollArea):
        return False
    hint = page.minimumSizeHint()
    return hint.height() > page.height() or hint.width() > page.width()


def main() -> int:
    config = ROOT / "config.json"
    raw = load_raw_config(config)
    settings = peek_ui_settings(raw)
    application = QApplication.instance() or create_application(["layout-check"])
    problems: list[str] = []

    for scale in UI_SCALES:
        percent = round(scale * 100)
        apply_theme(application, "light", scale)
        window = MainWindow(config, settings.with_scale(scale))
        window.setMinimumSize(0, 0)
        window.setAttribute(Qt.WA_DontShowOnScreen, True)
        window.show()
        window.resize(*TARGET)
        QApplication.processEvents()
        size = window.size()
        print(f"{percent:>3} %: okno {size.width()}×{size.height()}")
        if size.width() > TARGET[0] or size.height() > TARGET[1]:
            problems.append(
                f"okno se při {percent} % nezmenší na {TARGET[0]}×{TARGET[1]}"
                f" (zůstalo {size.width()}×{size.height()})"
            )

        for key, label in PAGES:
            window.sidebar.select(key)
            QApplication.processEvents()
            page = window.stack.currentWidget()
            if _clipped(page):
                problems.append(
                    f"{label} při {percent} % nemá posuvník a nevejde se "
                    f"({page.minimumSizeHint().height()} px do {page.height()} px)"
                )

        window.sidebar.select(PAGE_ADMIN)
        for key, label in SECTIONS:
            window.admin_page.show_section(key)
            QApplication.processEvents()
            page = window.admin_page.stack.currentWidget()
            if _clipped(page):
                problems.append(
                    f"Administrace → {label} při {percent} % nemá posuvník "
                    f"a nevejde se ({page.minimumSizeHint().height()} px "
                    f"do {page.height()} px)"
                )

        window.close()
        window.deleteLater()
        QApplication.processEvents()

    if problems:
        print("\nNalezené problémy:")
        for item in problems:
            print(f" - {item}")
        return 1
    print(f"\nVšechny obrazovky se ve všech zvětšeních vejdou do {TARGET[0]}×{TARGET[1]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
