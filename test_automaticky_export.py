import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import automaticky_export as scheduled
from mail_service import CookingStatus, MailDispatchResult


def write_config(path: Path, *, only_cooking_days: bool = True) -> None:
    path.write_text(
        json.dumps(
            {
                "povolene_kategorie": ["1STD", "ZAM"],
                "mail_prijemci": ["a@example.cz", "B@example.cz"],
                "mail_odesilatel": "podpora@altisima.cz",
                "mail_text": "Dobrý den",
                "mail_jen_varne_dny": only_cooking_days,
            }
        ),
        encoding="utf-8",
    )


class ScheduledExportTests(unittest.TestCase):
    def test_uses_current_run_date_and_sends_pdf(self):
        run_date = date(2026, 8, 6)
        fake_config = SimpleNamespace(report_date=run_date)
        fake_pdf = Path("sestava.pdf")
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            write_config(config_path, only_cooking_days=False)
            with (
                mock.patch.object(scheduled, "get_resend_api_key", return_value="re_test"),
                mock.patch.object(scheduled, "load_config", return_value=fake_config) as load,
                mock.patch.object(scheduled, "fetch_report", return_value="report"),
                mock.patch.object(scheduled, "create_pdf", return_value=fake_pdf),
                mock.patch.object(
                    scheduled,
                    "send_pdf_via_mailsender",
                    return_value=MailDispatchResult(("a@example.cz", "B@example.cz")),
                ) as send,
            ):
                result = scheduled.run_scheduled_export(config_path, run_date)

        load.assert_called_once_with(config_path.resolve(), date_override="06.08.2026")
        self.assertEqual(send.call_args.args[1], "Seznam strávníků: 06.08.2026")
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["categories"], ("1STD", "ZAM"))

    def test_non_cooking_day_creates_nothing_and_sends_nothing(self):
        run_date = date(2026, 8, 8)
        fake_config = SimpleNamespace(report_date=run_date)
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            write_config(config_path, only_cooking_days=True)
            with (
                mock.patch.object(scheduled, "get_resend_api_key", return_value="re_test"),
                mock.patch.object(scheduled, "load_config", return_value=fake_config),
                mock.patch.object(
                    scheduled,
                    "fetch_cooking_status",
                    return_value=(CookingStatus("Oběd", False),),
                ),
                mock.patch.object(scheduled, "fetch_report") as fetch_report,
                mock.patch.object(scheduled, "create_pdf") as create_pdf,
                mock.patch.object(scheduled, "send_pdf_via_mailsender") as send,
            ):
                result = scheduled.run_scheduled_export(config_path, run_date)

        self.assertEqual(result["status"], "skipped")
        fetch_report.assert_not_called()
        create_pdf.assert_not_called()
        send.assert_not_called()

    def test_requires_saved_resend_key(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            write_config(config_path, only_cooking_days=False)
            fake_config = SimpleNamespace(report_date=date(2026, 8, 6))
            with (
                mock.patch.object(scheduled, "load_config", return_value=fake_config),
                mock.patch.object(scheduled, "get_resend_api_key", return_value=None),
            ):
                with self.assertRaisesRegex(scheduled.ConfigError, "Resend API klíč"):
                    scheduled.run_scheduled_export(config_path, date(2026, 8, 6))

    def test_log_rotates_at_size_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.log"
            path.write_bytes(b"x" * scheduled.LOG_MAX_BYTES)
            scheduled.write_log(path, "OK", "hotovo")
            self.assertTrue(path.with_suffix(".log.1").is_file())
            self.assertIn("hotovo", path.read_text(encoding="utf-8"))

    def test_main_shows_dashboard_warning_on_error(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            write_config(config_path, only_cooking_days=False)
            log_path = Path(directory) / "auto.log"
            with (
                mock.patch.object(
                    scheduled,
                    "run_scheduled_export_with_retry",
                    side_effect=scheduled.ConfigError("boom"),
                ),
                mock.patch.object(
                    scheduled,
                    "show_jidelnasql_mail_warning",
                    return_value=None,
                ) as warn,
            ):
                code = scheduled.main(
                    ["--config", str(config_path), "--log", str(log_path)]
                )
        self.assertEqual(code, 2)
        warn.assert_called_once()

    def test_main_clears_dashboard_warning_after_success(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            write_config(config_path, only_cooking_days=False)
            log_path = Path(directory) / "auto.log"
            sent = {
                "status": "sent",
                "path": Path("x.pdf"),
                "recipients": ("a@example.cz",),
                "detail": "",
                "categories": ("1",),
            }
            with (
                mock.patch.object(
                    scheduled,
                    "run_scheduled_export_with_retry",
                    return_value=sent,
                ),
                mock.patch.object(
                    scheduled, "clear_jidelnasql_mail_warning", return_value=None
                ) as clear,
            ):
                code = scheduled.main(
                    ["--config", str(config_path), "--log", str(log_path)]
                )
        self.assertEqual(code, 0)
        clear.assert_called_once()

    def test_retry_continues_when_internet_check_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            log_path = Path(directory) / "auto.log"
            config_path.write_text("{}", encoding="utf-8")
            with (
                mock.patch.object(
                    scheduled,
                    "_has_internet",
                    side_effect=[False, True],
                ),
                mock.patch.object(
                    scheduled,
                    "run_scheduled_export",
                    side_effect=[
                        RuntimeError("network timeout"),
                        {"status": "sent"},
                    ],
                ) as run,
                mock.patch.object(scheduled.time, "sleep") as sleep_mock,
            ):
                result = scheduled.run_scheduled_export_with_retry(
                    config_path, date(2026, 8, 6), log_path
                )
        self.assertEqual(result["status"], "sent")
        self.assertEqual(run.call_count, 2)
        sleep_mock.assert_called_once_with(scheduled.RETRY_DELAYS_SECONDS[0])

    def test_retry_stops_for_permanent_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            log_path = Path(directory) / "auto.log"
            config_path.write_text("{}", encoding="utf-8")
            with (
                mock.patch.object(scheduled, "_has_internet", return_value=True),
                mock.patch.object(
                    scheduled,
                    "run_scheduled_export",
                    side_effect=scheduled.ConfigError("invalid api key"),
                ) as run,
                mock.patch.object(scheduled.time, "sleep") as sleep_mock,
            ):
                with self.assertRaises(scheduled.ConfigError):
                    scheduled.run_scheduled_export_with_retry(
                        config_path, date(2026, 8, 6), log_path
                    )
        self.assertEqual(run.call_count, 1)
        sleep_mock.assert_not_called()

    def test_retry_uses_retry_after_for_http_429(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            log_path = Path(directory) / "auto.log"
            config_path.write_text("{}", encoding="utf-8")
            with (
                mock.patch.object(scheduled, "_has_internet", return_value=True),
                mock.patch.object(
                    scheduled,
                    "run_scheduled_export",
                    side_effect=[
                        RuntimeError("HTTP 429 Too Many Requests Retry-After: 120"),
                        {"status": "sent"},
                    ],
                ),
                mock.patch.object(scheduled.time, "sleep") as sleep_mock,
            ):
                scheduled.run_scheduled_export_with_retry(
                    config_path, date(2026, 8, 6), log_path
                )
        sleep_mock.assert_called_once_with(120)


if __name__ == "__main__":
    unittest.main()
