"""Přenosný build v12: jeden EXE pro okno i pro běh bez GUI."""

import sys
import unittest
from pathlib import Path
from unittest import mock

import runtime_paths
from gui_qt import APP_VERSION
from services import cli


ROOT = Path(__file__).resolve().parent


class PortableBuildTests(unittest.TestCase):
    def test_source_application_directory_is_project_directory(self):
        self.assertEqual(runtime_paths.application_directory(), ROOT)

    def test_frozen_application_directory_is_next_to_executable(self):
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(
            sys, "executable", str(ROOT / "portable" / "MailPilot.exe")
        ):
            self.assertEqual(
                runtime_paths.application_directory(), ROOT / "portable"
            )

    def test_no_arguments_start_the_window(self):
        request, rest = cli.parse_cli([])
        self.assertFalse(request.headless)
        self.assertEqual(rest, [])

    def test_one_executable_supports_automatic_mode(self):
        request, _rest = cli.parse_cli(["--automatic"])
        self.assertTrue(request.automatic)
        self.assertTrue(request.headless)
        launcher = (ROOT / "spustit_automaticky_export.bat").read_text(
            encoding="utf-8"
        )
        self.assertIn("MailPilot.exe", launcher)
        self.assertIn("--automatic", launcher)

    def test_one_executable_supports_poctyemailem_alias(self):
        request, _rest = cli.parse_cli(["--poctyemailem"])
        self.assertTrue(request.automatic)
        launcher = (ROOT / "spustit_poctyemailem.bat").read_text(encoding="utf-8")
        self.assertIn("MailPilot.exe", launcher)
        self.assertIn("--poctyemailem", launcher)

    def test_one_executable_supports_monthly_closing_mode(self):
        for flag in ("--uzaverka_072026", "--zaverka_072026"):
            with self.subTest(flag=flag):
                request, _rest = cli.parse_cli([flag])
                self.assertEqual(request.closing_period, (2026, 7))
                self.assertTrue(request.headless)
        current, _rest = cli.parse_cli(["--zaverka_am"])
        self.assertTrue(current.closing_current)
        self.assertIsNone(current.closing_period)
        launcher = (ROOT / "spustit_uzaverku.bat").read_text(encoding="utf-8")
        self.assertIn("MailPilot.exe", launcher)
        self.assertIn("--zaverka_am", launcher)

    def test_one_executable_supports_z17_mode(self):
        request, _rest = cli.parse_cli(["--z17_2026"])
        self.assertEqual(request.z17_year, 2026)
        self.assertTrue(request.headless)
        launcher = (ROOT / "spustit_z17.bat").read_text(encoding="utf-8")
        self.assertIn("MailPilot.exe", launcher)
        self.assertIn("--z17_", launcher)

    def test_config_path_reaches_both_modes(self):
        request, rest = cli.parse_cli(["--config", "jine.json"])
        self.assertEqual(request.config, Path("jine.json"))
        self.assertIn("--config", rest)
        self.assertIn("jine.json", rest)

    def test_conflicting_modes_are_rejected(self):
        request, _rest = cli.parse_cli(["--poctyemailem", "--z17_2026"])
        self.assertEqual(cli.run_headless(request), 2)

    def test_windows_build_creates_onedir_portable_zip(self):
        script = (ROOT / "build_windows.bat").read_text(encoding="utf-8")
        mail_service = (ROOT / "mail_service.py").read_text(encoding="utf-8")
        self.assertIn("AutoReport_qt.py", script)
        self.assertIn("--onedir", script)
        self.assertIn("--windowed", script)
        self.assertIn("--exclude-module nicegui", script)
        self.assertIn("import mailsender_bridge as _mailsender_bridge", mail_service)
        self.assertNotIn('import_module("mailsender_bridge")', mail_service)
        self.assertIn("MailPilot-v12_7-portable.zip", script)
        self.assertIn("spustit_automaticky_export.bat", script)
        self.assertIn("spustit_poctyemailem.bat", script)
        self.assertIn("spustit_uzaverku.bat", script)
        self.assertIn("spustit_z17.bat", script)

    def test_qt_launcher_detaches_windowless_executable(self):
        launcher = (ROOT / "spustit_qt.bat").read_text(encoding="utf-8")
        self.assertIn('start "" "%~dp0MailPilot.exe"', launcher)
        self.assertIn("AutoReport_qt.py", launcher)

    def test_version_is_12(self):
        self.assertEqual(APP_VERSION, "v12.7")


if __name__ == "__main__":
    unittest.main()
