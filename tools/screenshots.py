"""Vývojářský nástroj: nasnímá obrazovky v12 ve všech kombinacích.

Spouští se ručně a slouží ke kontrole rozvržení při různém rozlišení,
zvětšení rozhraní a motivu. Data bere z reálné databáze podle
``config.json``; pokud připojení selže, obrazovky se nasnímají prázdné.

    python tools/screenshots.py --output ../_shots/v12
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "--offscreen" in sys.argv:
    # Offscreen platforma nemá na Windows systémová písma, snímky jsou pak
    # jen kontrola rozvržení.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gui_qt.app import create_application  # noqa: E402
from gui_qt.main_window import (  # noqa: E402
    PAGE_ADMIN,
    PAGE_BULK,
    PAGE_CLOSING,
    PAGE_DAILY,
    PAGE_SPECIAL,
    MainWindow,
)
from gui_qt.pages.admin import (  # noqa: E402
    SECTION_ADVANCED,
    SECTION_APPEARANCE,
    SECTION_DATABASE,
    SECTION_HEADLESS,
    SECTION_MAIL,
    SECTION_PDF,
    SECTION_SCHEDULER,
)
from gui_qt.theme import apply_theme  # noqa: E402
from services.config_io import database_parameters, load_raw_config  # noqa: E402
from services.database import ConnectionInfo, probe_connection, stored_password  # noqa: E402
from services.ui_settings import peek_ui_settings  # noqa: E402

SIZES = ((1920, 1080), (1366, 768))
SCALES = (1.0, 1.25, 1.6)
THEMES = ("light", "dark")
PAGES = (
    (PAGE_DAILY, "denni-stav", None),
    (PAGE_CLOSING, "uzaverka", None),
    (PAGE_SPECIAL, "special-z17", None),
    (PAGE_BULK, "hromadna-zprava", None),
    (PAGE_ADMIN, "admin-databaze", SECTION_DATABASE),
    (PAGE_ADMIN, "admin-emaily", SECTION_MAIL),
    (PAGE_ADMIN, "admin-planovac", SECTION_SCHEDULER),
    (PAGE_ADMIN, "admin-pdf", SECTION_PDF),
    (PAGE_ADMIN, "admin-vzhled", SECTION_APPEARANCE),
    (PAGE_ADMIN, "admin-bez-gui", SECTION_HEADLESS),
    (PAGE_ADMIN, "admin-pokrocile", SECTION_ADVANCED),
)


def _connection(raw: dict) -> ConnectionInfo | None:
    database = database_parameters(raw)
    try:
        return probe_connection(
            database, stored_password(database), remember=False
        )
    except Exception as exc:  # noqa: BLE001 - nástroj jen nahlásí důvod
        print(f"  databáze nedostupná: {exc}")
        return None


def capture(output: Path, config: Path, only: str = "") -> int:
    raw = load_raw_config(config)
    settings = peek_ui_settings(raw)
    application = QApplication.instance() or create_application(["screenshots"])
    info = _connection(raw)
    output.mkdir(parents=True, exist_ok=True)
    written = 0

    for theme in THEMES:
        for scale in SCALES:
            for width, height in SIZES:
                apply_theme(application, theme, scale)
                window = MainWindow(
                    config,
                    settings.with_theme(theme).with_scale(scale),
                )
                window.setMinimumSize(0, 0)
                # Bez skutečného okna se velikost neomezí plochou obrazovky,
                # takže lze nasnímat i 1920×1080 na menším monitoru.
                window.setAttribute(Qt.WA_DontShowOnScreen, True)
                window.resize(width, height)
                window.show()
                QApplication.processEvents()
                window._admin_unlocked = True
                window._refresh_admin_lock_state()
                if info is not None:
                    window._connection_ok(info, silent=True)
                QApplication.processEvents()
                for key, name, section in PAGES:
                    if only and only not in name:
                        continue
                    if key == PAGE_ADMIN:
                        window._activate_page(PAGE_ADMIN)
                        window.sidebar.clearSelection()
                    else:
                        window.sidebar.select(key)
                    if section is not None:
                        window.admin_page.show_section(section)
                    QApplication.processEvents()
                    scale_tag = f"{round(scale * 100)}"
                    target = (
                        output
                        / f"{name}_{theme}_{scale_tag}_{width}x{height}.png"
                    )
                    window.grab().save(str(target))
                    written += 1
                    if section == SECTION_ADVANCED:
                        window.admin_page.advanced_page.set_warning_active(False)
                        QApplication.processEvents()
                        off_target = (
                            output
                            / f"{name}_warning-off_{theme}_{scale_tag}_{width}x{height}.png"
                        )
                        window.grab().save(str(off_target))
                        written += 1
                        window.admin_page.advanced_page.set_warning_active(True)
                        QApplication.processEvents()
                        on_target = (
                            output
                            / f"{name}_warning-on_{theme}_{scale_tag}_{width}x{height}.png"
                        )
                        window.grab().save(str(on_target))
                        written += 1
                window.close()
                window.deleteLater()
                QApplication.processEvents()
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--output", type=Path, default=ROOT.parent / "_shots" / "v12")
    parser.add_argument("--only", default="", help="část názvu obrazovky")
    parser.add_argument(
        "--offscreen",
        action="store_true",
        help="běh bez oken (na Windows bez systémových písem)",
    )
    args = parser.parse_args(argv)
    count = capture(args.output.resolve(), args.config.resolve(), args.only)
    print(f"Uloženo {count} snímků do {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
