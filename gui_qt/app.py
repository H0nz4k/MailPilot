"""Start desktopového rozhraní MailPilotu (PySide6)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QLibraryInfo, QLocale, Qt, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from gui_qt import APP_TITLE, APP_VERSION
from gui_qt.main_window import MainWindow
from gui_qt.theme import apply_theme
from runtime_paths import application_directory, bundled_path
from services.config_io import load_raw_config
from services.ui_settings import peek_ui_settings
from stravovaci_sestava import ConfigError


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="MailPilot",
        description="Desktopové rozhraní MailPilotu (PySide6 / Qt Widgets).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=application_directory() / "config.json",
        help="cesta ke konfiguraci (výchozí: config.json vedle aplikace)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_TITLE} {APP_VERSION}",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def _install_translations(application: QApplication) -> None:
    """Načte české texty standardních Qt dialogů, pokud jsou dostupné."""
    path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    for name in ("qtbase", "qt"):
        translator = QTranslator(application)
        if translator.load(QLocale("cs_CZ"), name, "_", path):
            application.installTranslator(translator)


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """Připraví QApplication s DPI politikou a systémovým fontem."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    application = QApplication(list(argv) if argv is not None else sys.argv[:1])
    application.setApplicationName(APP_TITLE)
    application.setApplicationVersion(APP_VERSION.lstrip("v"))
    application.setOrganizationName("HanzG")
    application.setStyle("Fusion")
    icon_path = bundled_path("assets", "app_icon.svg")
    if icon_path.exists():
        application.setWindowIcon(QIcon(str(icon_path)))
    _install_translations(application)
    return application


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    os.chdir(application_directory())
    application = create_application([sys.argv[0] if sys.argv else "MailPilot"])
    config_path = Path(args.config)
    try:
        raw = load_raw_config(config_path)
    except ConfigError as exc:
        QMessageBox.critical(None, f"{APP_TITLE} {APP_VERSION}", str(exc))
        return 2
    settings = peek_ui_settings(raw)
    apply_theme(
        application,
        settings.theme,
        settings.ui_scale,
        font_bold_mode=settings.font_bold_mode,
        custom_palette_enabled=settings.custom_palette_enabled,
        custom_palette=settings.custom_palette,
    )
    window = MainWindow(config_path, settings)
    window.show()
    return application.exec()


if __name__ == "__main__":  # pragma: no cover - přímé spuštění
    raise SystemExit(main())
