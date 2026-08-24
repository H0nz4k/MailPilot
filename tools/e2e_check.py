"""Průchod celou aplikací nad skutečnou databází.

Skript otevře hlavní okno, připojí se k databázi, načte přehled, vytvoří
denní PDF, spustí uzávěrku i podklad Z 17-01, načte příjemce hromadné zprávy
a vyzkouší změnu motivu a zvětšení včetně uložení do configu.

E-maily se záměrně neodesílají; ověřuje se jen připravenost odeslání.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import gui_qt.main_window as main_window_module  # noqa: E402
from gui_qt.app import create_application  # noqa: E402
from gui_qt.main_window import (  # noqa: E402
    PAGE_ADMIN,
    PAGE_BULK,
    PAGE_CLOSING,
    PAGE_DAILY,
    PAGE_SPECIAL,
    MainWindow,
)
from gui_qt.theme import apply_theme  # noqa: E402
from services.config_io import load_raw_config  # noqa: E402
from services.ui_settings import peek_ui_settings  # noqa: E402

TIMEOUT = 180.0


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[bool, str, str]] = []

    def add(self, ok: bool, name: str, detail: str = "") -> None:
        self.rows.append((ok, name, detail))
        mark = "OK  " if ok else "CHYBA"
        print(f"{mark} {name}{f' — {detail}' if detail else ''}", flush=True)

    @property
    def failed(self) -> int:
        return sum(1 for ok, _name, _detail in self.rows if not ok)


def _answer_dialogs(report: Report) -> None:
    """Bez obsluhy by potvrzovací dialogy průchod zastavily."""

    def question(_parent, title, text, *_args, **_kwargs):
        report.add(True, f"Potvrzení: {title}", text.splitlines()[0])
        return QMessageBox.Yes

    def note(_parent, title, text, *_args, **_kwargs):
        report.add(False, f"Hláška: {title}", text.splitlines()[0])
        return QMessageBox.Ok

    QMessageBox.question = staticmethod(question)
    QMessageBox.warning = staticmethod(note)
    QMessageBox.critical = staticmethod(note)
    QMessageBox.information = staticmethod(note)


def _wait(predicate, timeout: float = TIMEOUT) -> bool:
    """Točí smyčku událostí, dokud podmínka neplatí nebo nevyprší čas."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    QApplication.processEvents()
    return predicate()


def _status(window: MainWindow) -> str:
    return window.statusBar().currentMessage()


def run(config_path: Path) -> int:
    raw = load_raw_config(config_path)
    settings = peek_ui_settings(raw)
    application = QApplication.instance() or create_application(["e2e"])
    apply_theme(application, settings.theme, settings.ui_scale)

    report = Report()
    _answer_dialogs(report)
    # Kontrolní běh nemá otevírat prohlížeč PDF u každé sestavy.
    main_window_module.open_document = lambda path: None
    window = MainWindow(config_path, settings)
    window.setAttribute(Qt.WA_DontShowOnScreen, True)
    window.show()
    QApplication.processEvents()
    window._admin_unlocked = True
    window._refresh_admin_lock_state()

    connected = _wait(lambda: window.connection() is not None, 60.0)
    report.add(connected, "Připojení k databázi", _status(window))
    if not connected:
        return 1

    info = window.connection()
    report.add(
        bool(info.subject_name and info.database_name and info.period),
        "Hlavička s provozovnou a obdobím",
        f"{info.name} · {info.details}",
    )
    report.add(
        len(window.daily_page.category_options()) > 0,
        "Kategorie z databáze",
        f"{len(window.daily_page.category_options())} kategorií",
    )

    window.sidebar.select(PAGE_DAILY)
    window.daily_page.overview_requested.emit()
    loaded = _wait(lambda: window.daily_page.overview_rows() > 0 or "nen" in _status(window))
    report.add(loaded, "Přehled porcí", f"{window.daily_page.overview_rows()} řádků")

    window.daily_page.create_requested.emit()
    made = _wait(lambda: window.last_pdf() is not None)
    report.add(
        made and window.last_pdf().is_file(),
        "Denní PDF",
        str(window.last_pdf()) if made else _status(window),
    )

    window.sidebar.select(PAGE_CLOSING)
    window.closing_page.run_requested.emit()
    closed = _wait(lambda: window.last_closing() is not None)
    report.add(
        closed and window.last_closing().exists(),
        "Uzávěrka",
        str(window.last_closing()) if closed else _status(window),
    )

    window.sidebar.select(PAGE_SPECIAL)
    window.special_page.run_requested.emit()
    special = _wait(lambda: window.last_special() is not None)
    report.add(
        special and window.last_special().is_file(),
        "Podklad Z 17-01",
        str(window.last_special()) if special else _status(window),
    )

    window.sidebar.select(PAGE_BULK)
    window.bulk_page.reload_requested.emit()
    people = _wait(lambda: bool(window.bulk_data().diners))
    data = window.bulk_data()
    report.add(
        people,
        "Příjemci hromadné zprávy",
        f"{len(data.diners)} strávníků · {len(data.classes)} tříd · "
        f"{len(data.categories)} kategorií"
        if people
        else _status(window),
    )

    window._activate_page(PAGE_ADMIN)
    window.sidebar.clearSelection()
    for section in window.admin_page.sections():
        window.admin_page.show_section(section)
        QApplication.processEvents()
        page = window.admin_page.current_widget()
        report.add(
            page is not None and page.isVisible(),
            f"Administrace -> {section}",
        )

    window._change_scale(1.6)
    window._change_theme("dark")
    QApplication.processEvents()
    window.close()
    QApplication.processEvents()

    stored = json.loads(config_path.read_text(encoding="utf-8")).get("ui", {})
    report.add(
        abs(float(stored.get("ui_scale", 0)) - 1.6) < 0.001
        and stored.get("theme") == "dark",
        "Uložení motivu a zvětšení",
        json.dumps(stored, ensure_ascii=False),
    )

    restored = MainWindow(config_path, peek_ui_settings(load_raw_config(config_path)))
    restored.setAttribute(Qt.WA_DontShowOnScreen, True)
    restored.show()
    QApplication.processEvents()
    report.add(
        abs(restored.ui_settings().ui_scale - 1.6) < 0.001
        and restored.ui_settings().theme == "dark",
        "Obnovení nastavení po restartu",
    )

    restored._change_scale(settings.ui_scale)
    restored._change_theme(settings.theme)
    restored.close()
    QApplication.processEvents()

    print()
    print(f"Hotovo: {len(report.rows)} kontrol, chyb {report.failed}")
    return 1 if report.failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    arguments = parser.parse_args(argv)
    return run(arguments.config)


if __name__ == "__main__":
    raise SystemExit(main())
