import tempfile
import unittest
from pathlib import Path

from stravovaci_sestava import ConfigError
from uzaverka_nastaveni import (
    CLOSING_FLAG_HELP,
    CURRENT_CLOSING_PERIOD,
    DEFAULT_CLOSING_OUTPUT,
    apply_closing_ui,
    closing_flag,
    consume_closing_flag,
    parse_closing_flag,
    parse_closing_settings,
    parse_period,
    peek_closing_ui,
    require_closing_flag,
)


def write_raw(**overrides):
    raw = {
        "uzaverka": {
            "sestavy": ["fksp"],
            "stravovaci_arch": "StravovaciArch",
            "stravovaci_arch_hromadne": True,
            "rekapitulace": "R",
            "prilohy": "zip",
            "vsechny_kategorie": True,
            "vystup": "vystup/uzaverka/{rok}-{mesic}",
        }
    }
    raw["uzaverka"].update(overrides)
    return raw


class ClosingSettingsTests(unittest.TestCase):
    def test_parses_supported_variants_and_zip_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = parse_closing_settings(
                write_raw(
                    stravovaci_arch="StravArch2",
                    rekapitulace="ST",
                    prilohy="samostatne",
                ),
                year=2026,
                month=7,
                config_directory=Path(directory),
            )
        self.assertEqual(settings.arch_variant, "StravArch2")
        self.assertEqual(settings.recap_variant, "ST")
        self.assertEqual(settings.attachment_mode, "samostatne")
        self.assertFalse(settings.send_mail)
        self.assertEqual(settings.period_label, "červenec 2026")
        self.assertTrue(str(settings.output_directory).endswith("2026-07"))

    def test_accepts_all_supported_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = parse_closing_settings(
                write_raw(sestavy=["fksp", "stravovaci_arch", "rekapitulace"]),
                year=2026,
                month=7,
                config_directory=Path(directory),
            )
        self.assertEqual(
            settings.reports,
            ("fksp", "stravovaci_arch", "rekapitulace"),
        )

    def test_parses_send_mail_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = parse_closing_settings(
                write_raw(odeslat_mail=True),
                year=2026,
                month=7,
                config_directory=Path(directory),
            )
        self.assertTrue(settings.send_mail)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "odeslat_mail"):
                parse_closing_settings(
                    write_raw(odeslat_mail="ano"),
                    year=2026,
                    month=7,
                    config_directory=Path(directory),
                )

    def test_rejects_unknown_arch_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "stravovaci_arch"):
                parse_closing_settings(
                    write_raw(stravovaci_arch="Neznamy"),
                    year=2026,
                    month=7,
                    config_directory=Path(directory),
                )

    def test_period_validation(self):
        self.assertEqual(parse_period(2026, 7), (2026, 7))
        with self.assertRaises(ConfigError):
            parse_period(2026, 13)

    def test_parses_uzaverka_mmrrrr_flag(self):
        self.assertEqual(parse_closing_flag("--uzaverka_072026"), (2026, 7))
        self.assertEqual(parse_closing_flag("--zaverka_072026"), (2026, 7))
        self.assertEqual(closing_flag(2026, 7), "--zaverka_072026")
        remaining, period = consume_closing_flag(
            ["--config", "x.json", "--uzaverka_072026"]
        )
        self.assertEqual(remaining, ["--config", "x.json"])
        self.assertEqual(period, (2026, 7))
        remaining, period = consume_closing_flag(["--zaverka_052026"])
        self.assertEqual(period, (2026, 5))

    def test_parses_current_month_flag(self):
        remaining, period = consume_closing_flag(
            ["--config", "x.json", "--zaverka_am"]
        )
        self.assertEqual(remaining, ["--config", "x.json"])
        self.assertEqual(period, CURRENT_CLOSING_PERIOD)
        remaining, period = consume_closing_flag(["--uzaverka_am"])
        self.assertEqual(period, CURRENT_CLOSING_PERIOD)
        remaining, period = require_closing_flag(["--zaverka_am"])
        self.assertEqual(period, CURRENT_CLOSING_PERIOD)

    def test_rejects_mixing_current_and_explicit_period(self):
        with self.assertRaisesRegex(ConfigError, "jen jednou"):
            consume_closing_flag(["--zaverka_am", "--zaverka_072026"])

    def test_rejects_bare_uzaverka_without_period(self):
        with self.assertRaisesRegex(ConfigError, "zaverka_072026"):
            consume_closing_flag(["--uzaverka"])
        with self.assertRaisesRegex(ConfigError, "zaverka_072026"):
            consume_closing_flag(["--zaverka"])
        with self.assertRaisesRegex(ConfigError, "zaverka_072026"):
            require_closing_flag(["--config", "x.json"])
        self.assertIn("--zaverka_072026", CLOSING_FLAG_HELP)

    def test_rejects_old_year_month_switches(self):
        with self.assertRaisesRegex(ConfigError, "--zaverka_072026"):
            consume_closing_flag(["--rok", "2026", "--mesic", "7"])

    def test_peek_closing_ui_defaults_and_zip_switch(self):
        defaults = peek_closing_ui({})
        self.assertEqual(
            defaults["sestavy"],
            ["fksp", "stravovaci_arch", "rekapitulace"],
        )
        self.assertEqual(defaults["vystup"], DEFAULT_CLOSING_OUTPUT)
        self.assertTrue(defaults["zip"])
        self.assertFalse(defaults["odeslat_mail"])
        peeked = peek_closing_ui(
            {
                "uzaverka": {
                    "sestavy": ["fksp"],
                    "prilohy": "samostatne",
                    "odeslat_mail": True,
                    "vystup": "D:/uzaverky/{rok}-{mesic}",
                }
            }
        )
        self.assertEqual(peeked["sestavy"], ["fksp"])
        self.assertFalse(peeked["zip"])
        self.assertTrue(peeked["odeslat_mail"])
        self.assertEqual(peeked["vystup"], "D:/uzaverky/{rok}-{mesic}")

    def test_apply_closing_ui_writes_zip_mail_and_keeps_other_keys(self):
        updated = apply_closing_ui(
            {"stravovaci_arch": "StravArch2", "mail_prijemci": ["a@b.cz"]},
            reports=["rekapitulace", "fksp"],
            output="vystup/uzaverka/{rok}-{mesic}",
            pack_zip=True,
            send_mail=True,
        )
        self.assertEqual(updated["sestavy"], ["fksp", "rekapitulace"])
        self.assertEqual(updated["prilohy"], "zip")
        self.assertTrue(updated["odeslat_mail"])
        self.assertEqual(updated["stravovaci_arch"], "StravArch2")
        self.assertEqual(updated["mail_prijemci"], ["a@b.cz"])
        loose = apply_closing_ui(
            {},
            reports=["stravovaci_arch"],
            output="C:/tisky",
            pack_zip=False,
            send_mail=False,
        )
        self.assertEqual(loose["prilohy"], "samostatne")
        self.assertFalse(loose["odeslat_mail"])

    def test_apply_closing_ui_requires_report_and_path(self):
        with self.assertRaisesRegex(ConfigError, "alespoň jednu"):
            apply_closing_ui({}, reports=[], output="vystup", pack_zip=True, send_mail=False)
        with self.assertRaisesRegex(ConfigError, "složku"):
            apply_closing_ui(
                {},
                reports=["fksp"],
                output="   ",
                pack_zip=True,
                send_mail=False,
            )


if __name__ == "__main__":
    unittest.main()
