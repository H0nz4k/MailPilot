"""Unit tests for NSSM glue. Does not touch installed Windows services."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import web_mail_nssm as nssm


class WorkerPathTests(unittest.TestCase):
    def test_running_from_sources_uses_absolute_entry_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            with patch.object(nssm.sys, "frozen", False, create=True):
                executable, params, workdir = nssm._worker_launch(config)
            self.assertEqual(executable, Path(sys.executable).resolve())
            self.assertEqual(params[1:], ["--config", str(config)])
            entry = Path(params[0])
            self.assertTrue(entry.is_absolute())
            self.assertEqual(entry.name, "web_mail_worker_main.py")
            self.assertTrue(entry.is_file())
            self.assertEqual(workdir, entry.parent)

    def test_bundled_worker_is_next_to_gui_exe(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fake_gui = folder / "DataShip.exe"
            fake_worker = folder / "DataShip-Worker.exe"
            fake_gui.touch()
            fake_worker.touch()
            with (
                patch.object(nssm.sys, "frozen", True, create=True),
                patch.object(nssm.sys, "executable", str(fake_gui)),
            ):
                exe, params, workdir = nssm._worker_launch(folder / "config.json")
            self.assertEqual(exe, fake_worker)
            self.assertEqual(params, ["--config", str(folder / "config.json")])
            self.assertEqual(workdir, folder)

    def test_bundle_without_worker_fails_with_clear_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_gui = Path(tmp) / "DataShip.exe"
            fake_gui.touch()
            with (
                patch.object(nssm.sys, "frozen", True, create=True),
                patch.object(nssm.sys, "executable", str(fake_gui)),
            ):
                with self.assertRaisesRegex(ValueError, "DataShip-Worker.exe"):
                    nssm._worker_launch(Path(tmp) / "config.json")


class ServiceCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.config = self.folder / "config.json"
        self.config.write_text("{}", encoding="utf-8")
        self.nssmexe = self.folder / "nssm.exe"
        self.nssmexe.touch()
        self.settings = {
            "service_name": "DataShipScheduler",
            "nssm_path": str(self.nssmexe),
        }

    def test_install_sets_directory_and_logs(self):
        commands = []

        def fake_run(command, **_):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "OK", "")

        worker = self.folder / "DataShip-Worker.exe"
        worker.touch()
        with (
            patch.object(nssm, "load_settings", return_value=self.settings),
            patch.object(nssm, "_is_windows_admin", return_value=True),
            patch.object(nssm, "_worker_launch", return_value=(worker, ["--config", str(self.config)], self.folder)),
            patch.object(nssm.subprocess, "run", side_effect=fake_run),
        ):
            output = nssm.service_command(self.folder, "install")

        self.assertIn("nainstalovaná", output)
        self.assertEqual(commands[0][1:3], ["install", "DataShipScheduler"])
        self.assertEqual(commands[0][3:], [str(worker), "--config", str(self.config)])
        self.assertIn(["set", "DataShipScheduler", "AppDirectory", str(self.folder)], [c[1:] for c in commands])
        self.assertTrue((self.folder / "logy").is_dir())
        self.assertTrue(any(c[3] == "AppStderr" for c in commands if len(c) > 3))

    def test_status_needs_no_elevation(self):
        with (
            patch.object(nssm, "load_settings", return_value=self.settings),
            patch.object(nssm, "_is_windows_admin", return_value=False),
            patch.object(nssm.subprocess, "run", return_value=subprocess.CompletedProcess(
                [str(self.nssmexe), "status", "DataShipScheduler"], 0, "SERVICE_RUNNING", ""
            )),
        ):
            self.assertIn("SERVICE_RUNNING", nssm.service_command(self.folder, "status"))

    def test_install_needs_elevation(self):
        with (
            patch.object(nssm, "load_settings", return_value=self.settings),
            patch.object(nssm, "_is_windows_admin", return_value=False),
        ):
            with self.assertRaisesRegex(PermissionError, "správce"):
                nssm.service_command(self.folder, "install")

    def test_invalid_action_does_not_run_anything(self):
        with self.assertRaises(ValueError):
            nssm.service_command(self.folder, "delete")

    def test_nssm_error_contains_context(self):
        with patch.object(nssm.subprocess, "run", return_value=subprocess.CompletedProcess([], 5, "", "Access is denied")):
            with self.assertRaisesRegex(RuntimeError, "Access is denied"):
                nssm._invoke([str(self.nssmexe), "start", "DataShipScheduler"])


if __name__ == "__main__":
    unittest.main()
