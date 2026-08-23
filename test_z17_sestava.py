import tempfile
import unittest
from pathlib import Path

from stravovaci_sestava import ConfigError
from uzaverka_pdf import SubjectHeader
from z17_nastaveni import (
    Z17_FLAG_HELP,
    apply_z17_ui,
    consume_z17_flag,
    parse_z17_flag,
    parse_z17_settings,
    peek_z17_ui,
    period_keys,
    school_year_periods,
    z17_flag,
)
from z17_sestava import (
    MEAL_LUNCH,
    MEAL_MORNING,
    build_z17_report,
    classify_meal,
    columns_for_kinds,
    format_thousands,
    guess_z17_row,
)


class Z17SettingsTests(unittest.TestCase):
    def test_school_year_is_september_to_august_before_october(self):
        periods = school_year_periods(2026)
        self.assertEqual(periods[0], (2025, 9))
        self.assertEqual(periods[-1], (2026, 8))
        self.assertNotIn((2026, 10), periods)
        self.assertIn(202510, period_keys(periods))

    def test_parses_year_flag(self):
        self.assertEqual(parse_z17_flag("--z17_2026"), 2026)
        self.assertEqual(z17_flag(2026), "--z17_2026")
        remaining, year = consume_z17_flag(["--config", "x.json", "--z17_2026"])
        self.assertEqual(remaining, ["--config", "x.json"])
        self.assertEqual(year, 2026)

    def test_rejects_bare_flag(self):
        with self.assertRaisesRegex(ConfigError, "z17_2026"):
            consume_z17_flag(["--z17"])
        self.assertIn("--z17_2026", Z17_FLAG_HELP)

    def test_parses_mapping_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = parse_z17_settings(
                {
                    "z17": {
                        "mapovani_kategorii": {"0108": ["10"], "0114a": ["6"]},
                        "vystup": "out/{rok}",
                    }
                },
                year=2026,
                config_directory=Path(directory),
            )
        self.assertEqual(settings.category_rows["0108"], ("10",))
        self.assertEqual(settings.school_year_label, "2025/2026")
        self.assertTrue(str(settings.output_directory).endswith("2026"))

    def test_selected_categories_are_independent_of_daily(self):
        peeked = peek_z17_ui(
            {
                "povolene_kategorie": ["DENNI"],
                "z17": {
                    "vsechny_kategorie": False,
                    "povolene_kategorie": ["10", "6"],
                    "vystup": "out/{rok}",
                },
            }
        )
        self.assertFalse(peeked["vsechny_kategorie"])
        self.assertEqual(peeked["povolene_kategorie"], ["10", "6"])
        applied = apply_z17_ui(
            {},
            output="out/{rok}",
            use_all_categories=False,
            categories=["10"],
            year=2026,
        )
        self.assertEqual(applied["povolene_kategorie"], ["10"])
        self.assertFalse(applied["vsechny_kategorie"])
        self.assertEqual(applied["rok"], 2026)

    def test_rejects_selected_mode_without_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "povolene_kategorie"):
                parse_z17_settings(
                    {
                        "z17": {
                            "vsechny_kategorie": False,
                            "povolene_kategorie": [],
                        }
                    },
                    year=2026,
                    config_directory=Path(directory),
                )


class Z17ClassifyTests(unittest.TestCase):
    def test_meal_types(self):
        self.assertEqual(classify_meal("Oběd"), MEAL_LUNCH)
        self.assertEqual(classify_meal("Přesnídávka"), MEAL_MORNING)
        self.assertEqual(classify_meal("Večeře"), "vecere")
        self.assertEqual(classify_meal("Druhá večeře"), "druha_vecere")

    def test_guesses_common_category_names(self):
        self.assertEqual(guess_z17_row("6", "Učitelé"), "0114")
        self.assertEqual(guess_z17_row("10", "Gymnázium 2. stupeň"), "0108")
        self.assertEqual(guess_z17_row("2", "1. stupeň"), "0104")
        self.assertEqual(guess_z17_row("C", "Cizí strávníci"), "0113")

    def test_lunch_plus_out_of_scope_snack_stays_lunch_only(self):
        cols = columns_for_kinds(
            (MEAL_LUNCH, MEAL_MORNING), supplements_in_scope=False
        )
        self.assertEqual(cols.lunch_only, 1)
        self.assertEqual(cols.lunch_and_supplement, 0)

    def test_kindergarten_lunch_and_snack_uses_column_4(self):
        cols = columns_for_kinds(
            (MEAL_LUNCH, MEAL_MORNING), supplements_in_scope=True
        )
        self.assertEqual(cols.lunch_and_supplement, 1)
        self.assertEqual(cols.total, 1)

    def test_thousands_use_czech_decimal(self):
        self.assertEqual(format_thousands(12345), "12,3")
        self.assertEqual(format_thousands(19603), "19,6")


class Z17AggregationTests(unittest.TestCase):
    def test_splits_school_year_and_october_and_maps_rows(self):
        header = SubjectHeader(
            subject_name="ZS",
            address=None,
            zip_code=None,
            city=None,
            company_id=None,
            vat_id=None,
        )
        with tempfile.TemporaryDirectory() as directory:
            settings = parse_z17_settings(
                {
                    "z17": {
                        "mapovani_kategorii": {
                            "0104": ["2"],
                            "0108": ["10"],
                            "0114": ["6"],
                            "0114a": ["6"],
                        }
                    }
                },
                year=2026,
                config_directory=Path(directory),
            )
        report = build_z17_report(
            header=header,
            settings=settings,
            records=[
                (2025, 9, 1, "10", "Gymnázium", "Oběd", 20, False, False),
                (2026, 8, 1, "10", "Gymnázium", "Oběd", 15, False, False),
                (2025, 10, 1, "10", "Gymnázium", "Oběd", 17, False, False),
                (2026, 10, 1, "10", "Gymnázium", "Oběd", 18, False, False),
                (2026, 10, 2, "6", "Učitelé", "Oběd", 19, False, False),
                (2026, 10, 3, "2", "1. stupeň", "Oběd", 16, False, False),
                (2026, 10, 3, "2", "1. stupeň", "Svačina", 16, False, False),
                (2026, 10, 9, "2", "1. stupeň", "Oběd", 10, True, False),
            ],
        )
        by_code = {row.code: row for row in report.section_i}
        self.assertEqual(by_code["0108"].columns.total, 1)
        self.assertEqual(by_code["0108"].columns.lunch_only, 1)
        self.assertEqual(by_code["0104"].columns.lunch_only, 1)
        self.assertEqual(by_code["0104"].columns.lunch_and_supplement, 0)
        self.assertEqual(by_code["0113"].columns.supplement_only, 1)
        self.assertEqual(by_code["0113"].columns.total, 2)
        self.assertEqual(by_code["0114"].columns.total, 1)
        self.assertEqual(by_code["0114a"].columns.total, 1)
        self.assertEqual(by_code["0101"].columns.total, 2)
        self.assertEqual(by_code["0115"].columns.total, 4)
        lunches = {row.code: row for row in report.section_iii}["0301"]
        self.assertEqual(lunches.school_year, 52)
        self.assertEqual(lunches.october, 63)
        self.assertEqual(lunches.school_year_school, 52)
        snacks = {row.code: row for row in report.section_iii}["0305"]
        self.assertEqual(snacks.october, 16)
        self.assertEqual(snacks.school_year_school, 0)

    def test_selected_categories_ignore_other_codes(self):
        header = SubjectHeader(
            subject_name="ZS",
            address=None,
            zip_code=None,
            city=None,
            company_id=None,
            vat_id=None,
        )
        with tempfile.TemporaryDirectory() as directory:
            settings = parse_z17_settings(
                {
                    "z17": {
                        "mapovani_kategorii": {
                            "0104": ["2"],
                            "0108": ["10"],
                        },
                        "vsechny_kategorie": False,
                        "povolene_kategorie": ["10"],
                    }
                },
                year=2026,
                config_directory=Path(directory),
            )
        report = build_z17_report(
            header=header,
            settings=settings,
            records=[
                (2026, 10, 1, "10", "Gymnázium", "Oběd", 18, False, False),
                (2026, 10, 3, "2", "1. stupeň", "Oběd", 16, False, False),
            ],
        )
        by_code = {row.code: row for row in report.section_i}
        self.assertEqual(by_code["0108"].columns.total, 1)
        self.assertEqual(by_code["0104"].columns.total, 0)


if __name__ == "__main__":
    unittest.main()
