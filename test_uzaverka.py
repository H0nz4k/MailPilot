import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import uzaverka as closing
from mail_service import MailDispatchResult
from uzaverka_nastaveni import parse_closing_settings


def write_config(path: Path, **uzaverka) -> None:
    block = {
        "sestavy": ["fksp"],
        "prilohy": "zip",
        "vsechny_kategorie": False,
        "odeslat_mail": True,
        "vystup": "vystup/{rok}-{mesic}",
        "mail_prijemci": ["ucetni@example.cz"],
        "mail_text": "Uzávěrka v příloze",
    }
    block.update(uzaverka)
    path.write_text(
        json.dumps(
            {
                "mail_prijemci": ["scio@example.cz"],
                "mail_odesilatel": "podpora@altisima.cz",
                "mail_text": "Denní počty v příloze",
                "datum": "15.07.2026",
                "uzaverka": block,
            }
        ),
        encoding="utf-8",
    )


class MonthlyClosingTests(unittest.TestCase):
    def test_packs_pdf_into_zip_and_sends_it(self):
        fake_config = SimpleNamespace(
            report_date=None,
            categories=("6",),
            database={},
        )
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            write_config(config_path)
            pdf_path = Path(directory) / "FKSP_2026-07.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
            with (
                mock.patch.object(closing, "get_resend_api_key", return_value="re_test"),
                mock.patch.object(closing, "load_config", return_value=fake_config),
                mock.patch.object(closing, "resolve_categories", return_value=fake_config),
                mock.patch.object(closing, "generate_reports", return_value=[pdf_path]),
                mock.patch.object(
                    closing,
                    "send_files_via_mailsender",
                    return_value=MailDispatchResult(("ucetni@example.cz",)),
                ) as send,
            ):
                result = closing.run_monthly_closing(
                    config_path, year=2026, month=7
                )
                attachment = send.call_args.args[3][0]
                self.assertEqual(result["status"], "sent")
                self.assertEqual(attachment.suffix, ".zip")
                self.assertTrue(attachment.is_file())
                self.assertEqual(
                    send.call_args.args[1], "Uzávěrka stravného: červenec 2026"
                )

    def test_sends_separate_pdfs_when_configured(self):
        fake_config = SimpleNamespace(categories=("6",), database={})
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            write_config(config_path, prilohy="samostatne")
            pdf_path = Path(directory) / "FKSP_2026-07.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
            with (
                mock.patch.object(closing, "get_resend_api_key", return_value="re_test"),
                mock.patch.object(closing, "load_config", return_value=fake_config),
                mock.patch.object(closing, "resolve_categories", return_value=fake_config),
                mock.patch.object(closing, "generate_reports", return_value=[pdf_path]),
                mock.patch.object(
                    closing,
                    "send_files_via_mailsender",
                    return_value=MailDispatchResult(("ucetni@example.cz",)),
                ) as send,
            ):
                closing.run_monthly_closing(config_path, year=2026, month=7)

        self.assertEqual(send.call_args.args[3], [pdf_path])

    def test_skips_mail_when_disabled_in_config(self):
        fake_config = SimpleNamespace(categories=("6",), database={})
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            write_config(config_path, odeslat_mail=False)
            pdf_path = Path(directory) / "FKSP_2026-07.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
            with (
                mock.patch.object(closing, "get_resend_api_key") as api_key,
                mock.patch.object(closing, "load_config", return_value=fake_config),
                mock.patch.object(closing, "resolve_categories", return_value=fake_config),
                mock.patch.object(closing, "generate_reports", return_value=[pdf_path]),
                mock.patch.object(closing, "send_files_via_mailsender") as send,
            ):
                result = closing.run_monthly_closing(
                    config_path, year=2026, month=7
                )
                self.assertEqual(result["status"], "exported")
                self.assertTrue(result["attachments"][0].is_file())
                api_key.assert_not_called()
                send.assert_not_called()

    def test_closing_mail_does_not_use_daily_recipients(self):
        fake_config = SimpleNamespace(categories=("6",), database={})
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            write_config(config_path, mail_prijemci=[], mail_text="")
            pdf_path = Path(directory) / "FKSP_2026-07.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
            with (
                mock.patch.object(closing, "get_resend_api_key", return_value="re_test"),
                mock.patch.object(closing, "load_config", return_value=fake_config),
                mock.patch.object(closing, "resolve_categories", return_value=fake_config),
                mock.patch.object(closing, "generate_reports", return_value=[pdf_path]),
                mock.patch.object(closing, "send_files_via_mailsender") as send,
            ):
                with self.assertRaisesRegex(closing.ConfigError, "Uzávěrka"):
                    closing.run_monthly_closing(config_path, year=2026, month=7)
                send.assert_not_called()

    def test_cli_requires_period_in_flag(self):
        args = closing.parse_args(
            ["--uzaverka_072026", "--config", "config.json"]
        )
        self.assertEqual(args.rok, 2026)
        self.assertEqual(args.mesic, 7)
        self.assertEqual(args.uzaverka_flag, "--zaverka_072026")
        with self.assertRaisesRegex(closing.ConfigError, "zaverka_072026"):
            closing.parse_args(["--config", "config.json"])

    def test_cli_accepts_zaverka_alias(self):
        args = closing.parse_args(["--zaverka_072026", "--config", "config.json"])
        self.assertEqual(args.rok, 2026)
        self.assertEqual(args.mesic, 7)

    def test_cli_accepts_current_month_flag(self):
        args = closing.parse_args(["--zaverka_am", "--config", "config.json"])
        self.assertTrue(args.uzaverka_current)
        self.assertIsNone(args.rok)
        self.assertIsNone(args.mesic)
        self.assertEqual(args.uzaverka_flag, "--zaverka_am")
        alias = closing.parse_args(["--uzaverka_am", "--config", "config.json"])
        self.assertTrue(alias.uzaverka_current)

    def test_current_month_closing_reads_period_from_jidelna(self):
        fake_config = SimpleNamespace(categories=("6",), database={})
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            write_config(config_path, odeslat_mail=False)
            pdf_path = Path(directory) / "FKSP_2026-07.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
            with (
                mock.patch.object(
                    closing, "fetch_current_jidelna_period", return_value=(2026, 7)
                ) as fetch,
                mock.patch.object(closing, "load_config", return_value=fake_config),
                mock.patch.object(closing, "resolve_categories", return_value=fake_config),
                mock.patch.object(closing, "generate_reports", return_value=[pdf_path]),
            ):
                result = closing.run_monthly_closing(
                    config_path, current_month=True
                )
            fetch.assert_called_once_with(config_path.resolve())
            self.assertEqual(result["status"], "exported")
            self.assertEqual(result["year"], 2026)
            self.assertEqual(result["month"], 7)

    def test_example_config_is_valid_closing_block(self):
        example = json.loads(
            (Path(__file__).resolve().parent / "config.example.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            settings = parse_closing_settings(
                example,
                year=2026,
                month=7,
                config_directory=Path(directory),
            )
        self.assertEqual(
            settings.reports,
            ("fksp", "stravovaci_arch", "rekapitulace"),
        )
        self.assertEqual(settings.attachment_mode, "zip")
        self.assertFalse(settings.send_mail)

    def test_report_ranges_cover_enabled_reports(self):
        ranges = closing.report_ranges(("fksp", "stravovaci_arch", "rekapitulace"))
        self.assertEqual(ranges["fksp"][0], 6)
        self.assertEqual(ranges["rekapitulace"][1], 90)
        self.assertLess(ranges["fksp"][1], ranges["stravovaci_arch"][0] + 1)
        self.assertLess(ranges["stravovaci_arch"][1], ranges["rekapitulace"][1] + 1)

    def test_closing_emits_progress_messages(self):
        fake_config = SimpleNamespace(categories=("6", "7"), database={})
        seen: list[tuple[int, str]] = []
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            write_config(config_path, odeslat_mail=False)
            pdf_path = Path(directory) / "FKSP_2026-07.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
            with (
                mock.patch.object(closing, "load_config", return_value=fake_config),
                mock.patch.object(closing, "resolve_categories", return_value=fake_config),
                mock.patch.object(closing, "generate_reports", return_value=[pdf_path]),
            ):
                closing.run_monthly_closing(
                    config_path,
                    year=2026,
                    month=7,
                    on_progress=lambda percent, message: seen.append((percent, message)),
                )
        percents = [item[0] for item in seen]
        self.assertEqual(percents[0], 0)
        self.assertEqual(percents[-1], 100)
        self.assertEqual(percents, sorted(percents))
        self.assertTrue(any("nastavení" in message for _, message in seen))
        self.assertTrue(any("ZIP" in message for _, message in seen))


if __name__ == "__main__":
    unittest.main()
