import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from stravovaci_sestava import (
    AppConfig,
    CATEGORY_SUMMARY_QUERY,
    CategorySummary,
    ConfigError,
    DINER_LIST_QUERY,
    DinerOrder,
    existing_categories,
    MenuSummary,
    NORM_MENU_QUERY,
    NormMenuSummary,
    ReportData,
    SUBJECT_NAME_QUERY,
    SUMMARY_QUERY,
    create_pdf,
    load_config,
    parse_jidelna_period,
    peek_jidelna_period,
    render_table,
)


VALID_CONFIG = {
    "databaze": {
        "host": "127.0.0.1",
        "port": 5432,
        "dbname": "jidelna",
        "user": "tester",
    },
    "povolene_kategorie": ["Z1", "Z2", "Z1"],
    "datum": "05.08.2026",
}


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.password_patch = patch(
            "stravovaci_sestava.get_password", return_value="secret"
        )
        self.password_patch.start()
        self.addCleanup(self.password_patch.stop)

    def write_config(self, content):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "config.json"
        path.write_text(json.dumps(content), encoding="utf-8")
        return path

    def test_loads_and_normalizes_config(self):
        path = self.write_config(VALID_CONFIG)
        config = load_config(path)
        self.assertEqual(config.report_date, date(2026, 8, 5))
        self.assertEqual(config.categories, ("Z1", "Z2"))
        self.assertEqual(config.language, "česky")
        self.assertEqual(config.menu_list_number, 1)
        self.assertFalse(config.category_separation)
        self.assertTrue(config.show_by_categories)
        self.assertTrue(config.show_by_norms)
        self.assertEqual(config.pdf_orientation, "na_sirku")
        self.assertEqual(config.pdf_data_font_size, 7.4)
        self.assertEqual(config.pdf_label_font_size, 7.4)
        self.assertFalse(config.pdf_bold)
        self.assertEqual(
            config.pdf_output,
            path.parent / "vystup" / "AutoReport_2026-08-05.pdf",
        )

    def test_poctyemailem_categories_override_root_list(self):
        content = dict(VALID_CONFIG)
        content["poctyemailem"] = {"povolene_kategorie": ["ZAM"]}
        config = load_config(self.write_config(content))
        self.assertEqual(config.categories, ("ZAM",))

    def test_loads_category_separation(self):
        content = dict(VALID_CONFIG)
        content["kategor_separ"] = True
        config = load_config(self.write_config(content))
        self.assertTrue(config.category_separation)

    def test_existing_categories_trims_database_padding_and_ignores_missing(self):
        self.assertEqual(
            existing_categories(("MŠ T", "Z1", "NEEXISTUJE"), ("MŠ T ", "Z1")),
            ("MŠ T", "Z1"),
        )

    def test_rejects_non_boolean_category_separation(self):
        content = dict(VALID_CONFIG)
        content["kategor_separ"] = "true"
        with self.assertRaises(ConfigError):
            load_config(self.write_config(content))

    def test_loads_summary_visibility_options(self):
        content = dict(VALID_CONFIG)
        content.update({"dle_kategorii": False, "dle_norem": False})
        config = load_config(self.write_config(content))
        self.assertFalse(config.show_by_categories)
        self.assertFalse(config.show_by_norms)

    def test_rejects_non_boolean_summary_visibility_options(self):
        for key in ("dle_kategorii", "dle_norem"):
            with self.subTest(key=key):
                content = dict(VALID_CONFIG)
                content[key] = "false"
                with self.assertRaises(ConfigError):
                    load_config(self.write_config(content))

    def test_loads_pdf_appearance_options(self):
        content = dict(VALID_CONFIG)
        content.update(
            {
                "pdf_orientace": "na_vysku",
                "pdf_velikost_dat": 9.5,
                "pdf_velikost_popisku": 11,
                "pdf_tucne": True,
            }
        )
        config = load_config(self.write_config(content))
        self.assertEqual(config.pdf_orientation, "na_vysku")
        self.assertEqual(config.pdf_data_font_size, 9.5)
        self.assertEqual(config.pdf_label_font_size, 11)
        self.assertTrue(config.pdf_bold)

    def test_accepts_human_readable_pdf_orientation_aliases(self):
        content = dict(VALID_CONFIG)
        content["pdf_orientace"] = "na výšku"
        self.assertEqual(
            load_config(self.write_config(content)).pdf_orientation,
            "na_vysku",
        )

    def test_rejects_invalid_pdf_appearance_options(self):
        for key, value in (
            ("pdf_orientace", "čtverec"),
            ("pdf_velikost_dat", 4.9),
            ("pdf_velikost_popisku", 18.1),
            ("pdf_tucne", "ano"),
        ):
            with self.subTest(key=key):
                content = dict(VALID_CONFIG)
                content[key] = value
                with self.assertRaises(ConfigError):
                    load_config(self.write_config(content))

    def test_cli_date_overrides_config(self):
        config = load_config(self.write_config(VALID_CONFIG), "06.08.2026")
        self.assertEqual(config.report_date, date(2026, 8, 6))

    def test_rejects_invalid_date(self):
        content = dict(VALID_CONFIG)
        content["datum"] = "2026-08-05"
        with self.assertRaises(ConfigError):
            load_config(self.write_config(content))

    def test_pdf_output_supports_date_placeholder_and_cli_override(self):
        content = dict(VALID_CONFIG)
        content["pdf_vystup"] = "sestavy/seznam_{datum_cz}.pdf"
        path = self.write_config(content)
        config = load_config(path)
        self.assertEqual(
            config.pdf_output,
            path.parent / "sestavy" / "seznam_05.08.2026.pdf",
        )

        override = path.parent / "vlastni.pdf"
        overridden = load_config(path, pdf_override=override)
        self.assertEqual(overridden.pdf_output, override)

    def test_rejects_non_pdf_output(self):
        content = dict(VALID_CONFIG)
        content["pdf_vystup"] = "vystup/sestava.txt"
        with self.assertRaises(ConfigError):
            load_config(self.write_config(content))

    def test_rejects_password_stored_in_json(self):
        content = json.loads(json.dumps(VALID_CONFIG))
        content["databaze"]["password"] = "nesmi-byt-v-json"
        with self.assertRaisesRegex(ConfigError, "Heslo nesmí být"):
            load_config(self.write_config(content))


class OutputTests(unittest.TestCase):
    def test_renders_rows_and_total(self):
        config = AppConfig(
            database={},
            report_date=date(2026, 8, 5),
            categories=("Z1", "Z2"),
            language="Česky",
            menu_list_number=1,
        )
        output = render_table(
            config,
            [
                MenuSummary("Oběd", 1, 12, "Polévka, Kuře s rýží"),
                MenuSummary("Oběd", 2, 3, None),
            ],
        )
        self.assertIn("Oběd", output)
        self.assertIn("Polévka, Kuře s rýží", output)
        self.assertIn("Celkem porcí: 15", output)

    def test_renders_category_names_counts_and_norm_menu_matrix(self):
        config = AppConfig(
            database={},
            report_date=date(2026, 8, 5),
            categories=("Z1", "Z2", "Z3"),
            language="česky",
            menu_list_number=1,
        )
        output = render_table(
            config,
            [
                MenuSummary("Oběd", 1, 12, "Hrachová kaše"),
                MenuSummary("Oběd", 2, 3, "Bulgur"),
            ],
            [
                CategorySummary("Z1", "Žáci 7–10", "A", 10),
                CategorySummary("Z2", "Žáci 11–14", "B", 5),
                CategorySummary("Z3", "Zaměstnanci", "D", 0),
            ],
            [
                NormMenuSummary("Oběd", "A", 1, 9),
                NormMenuSummary("Oběd", "A", 2, 1),
                NormMenuSummary("Oběd", "B", 1, 3),
                NormMenuSummary("Oběd", "B", 2, 2),
            ],
        )
        self.assertIn("Přihlášky podle kategorií", output)
        self.assertIn("Žáci 7–10", output)
        self.assertIn("Zaměstnanci", output)
        self.assertIn("Celkem přihlášek: 15", output)
        self.assertIn("Objednaná menu podle norem", output)
        self.assertIn("Norma | Menu 1 | Menu 2 | Celkem", output)
        self.assertIn("A     | 9      | 1      | 10", output)
        self.assertIn("D     | 0      | 0      | 0", output)

    def test_renders_diner_list_sorted_by_name(self):
        config = AppConfig(
            database={},
            report_date=date(2026, 8, 5),
            categories=("Z1", "Z2"),
            language="česky",
            menu_list_number=1,
        )
        output = render_table(
            config,
            [],
            diner_rows=[
                DinerOrder("Žák Zdeněk", "Z2", "Žáci 11–14", "Oběd", 2, "B", "Bulgur"),
                DinerOrder("Adam Alena", "Z1", "Žáci 7–10", "Oběd", 1, "A", "Hrachová kaše"),
            ],
        )
        self.assertIn("Jmenný seznam strávníků", output)
        self.assertIn("Jméno", output)
        self.assertIn("Objednané jídlo", output)
        self.assertIn("Menu 1", output)
        self.assertLess(output.index("Adam Alena"), output.index("Žák Zdeněk"))

    def test_can_hide_category_and_norm_tables_in_console_output(self):
        config = AppConfig(
            database={},
            report_date=date(2026, 8, 5),
            categories=("Z1",),
            language="česky",
            menu_list_number=1,
            show_by_categories=False,
            show_by_norms=False,
        )
        output = render_table(
            config,
            [MenuSummary("Oběd", 1, 1, "Kaše")],
            [CategorySummary("Z1", "Žáci", "A", 1)],
            [NormMenuSummary("Oběd", "A", 1, 1)],
        )
        self.assertNotIn("Přihlášky podle kategorií", output)
        self.assertNotIn("Objednaná menu podle norem", output)
        self.assertIn("Objednaná menu", output)

    def test_diner_list_uses_category_code_as_name_fallback(self):
        config = AppConfig({}, date(2026, 8, 5), ("Z1",), "česky", 1)
        output = render_table(
            config,
            [],
            diner_rows=[
                DinerOrder("Novák Jan", "Z1", None, "Oběd", 1, None, None),
            ],
        )
        self.assertIn("Z1", output)
        self.assertIn("[bez normy]", output)
        self.assertIn("[název v jídelníčku nenalezen]", output)

    def test_diner_list_can_be_separated_by_category(self):
        config = AppConfig(
            database={},
            report_date=date(2026, 8, 5),
            categories=("Z2", "Z1", "Z3"),
            language="česky",
            menu_list_number=1,
            category_separation=True,
        )
        output = render_table(
            config,
            [],
            diner_rows=[
                DinerOrder("Žák Zdeněk", "Z1", "Žáci 7–10", "Oběd", 1, "A", "Kaše"),
                DinerOrder("Bartoš Boris", "Z2", "Žáci 11–14", "Oběd", 2, "B", "Bulgur"),
                DinerOrder("Adam Alena", "Z1", "Žáci 7–10", "Oběd", 1, "A", "Kaše"),
            ],
        )
        self.assertIn("Jmenný seznam strávníků podle kategorií", output)
        self.assertIn("Žáci 11–14\n----------", output)
        self.assertIn("Žáci 7–10\n---------", output)
        self.assertNotIn("Z3\n--", output)
        self.assertLess(output.index("Žáci 11–14"), output.index("Žáci 7–10"))
        self.assertLess(output.index("Adam Alena"), output.index("Žák Zdeněk"))

    def test_false_category_separation_keeps_single_list(self):
        config = AppConfig(
            {}, date(2026, 8, 5), ("Z1",), "česky", 1, False
        )
        output = render_table(
            config,
            [],
            diner_rows=[
                DinerOrder("Novák Jan", "Z1", "Žáci", "Oběd", 1, "A", "Kaše"),
            ],
        )
        self.assertIn("Jmenný seznam strávníků\nJméno", output)
        self.assertNotIn("Jmenný seznam strávníků podle kategorií", output)

    def test_renders_subject_name_at_top_of_header(self):
        config = AppConfig({}, date(2026, 8, 5), ("Z1",), "česky", 1)
        output = render_table(
            config,
            [],
            subject_name="Základní škola a mateřská škola",
        )
        self.assertTrue(output.startswith("Základní škola a mateřská škola\n"))
        self.assertIn("Objednaná strava pro 05.08.2026", output)

    def test_creates_multipage_landscape_pdf_with_czech_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "sestavy" / "seznam.pdf"
            config = AppConfig(
                database={},
                report_date=date(2026, 8, 5),
                categories=("Z1", "Z2"),
                language="česky",
                menu_list_number=1,
                category_separation=True,
                pdf_output=output,
            )
            diners = tuple(
                DinerOrder(
                    f"Žák {index:03d}",
                    "Z1" if index < 55 else "Z2",
                    "Žáci první kategorie" if index < 55 else "Zaměstnanci",
                    "Oběd",
                    1 if index % 3 else 2,
                    "A" if index < 55 else "C",
                    (
                        "Kuřecí plátek s bramborovou kaší a zeleninovou "
                        "oblohou"
                    ),
                )
                for index in range(95)
            )
            report = ReportData(
                menus=(
                    MenuSummary("Oběd", 1, 63, "Hrachová kaše"),
                    MenuSummary("Oběd", 2, 32, "Bulgur se zeleninou"),
                ),
                categories=(
                    CategorySummary("Z1", "Žáci první kategorie", "A", 55),
                    CategorySummary("Z2", "Zaměstnanci", "C", 40),
                ),
                norms=(
                    NormMenuSummary("Oběd", "A", 1, 36),
                    NormMenuSummary("Oběd", "A", 2, 19),
                    NormMenuSummary("Oběd", "C", 1, 27),
                    NormMenuSummary("Oběd", "C", 2, 13),
                ),
                diners=diners,
                subject_name="ZŠ Kozinova",
            )

            created = create_pdf(config, report)
            self.assertEqual(created, output.resolve())
            self.assertTrue(created.is_file())

            from pypdf import PdfReader

            reader = PdfReader(str(created))
            self.assertGreaterEqual(len(reader.pages), 2)
            self.assertGreater(
                float(reader.pages[0].mediabox.width),
                float(reader.pages[0].mediabox.height),
            )
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("ZŠ Kozinova", text)
            self.assertIn("Jmenný seznam strávníků", text)
            self.assertIn("Žáci první kategorie", text)
            self.assertIn("Strana 2", text)

    def test_creates_portrait_pdf_with_larger_bold_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "portrait.pdf"
            config = AppConfig(
                database={},
                report_date=date(2026, 8, 5),
                categories=("Z1",),
                language="česky",
                menu_list_number=1,
                pdf_output=output,
                pdf_orientation="na_vysku",
                pdf_data_font_size=9.5,
                pdf_label_font_size=10.5,
                pdf_bold=True,
            )
            diners = tuple(
                DinerOrder(
                    f"Žák {index:03d}",
                    "Z1",
                    "Žáci",
                    "Oběd",
                    1,
                    "A",
                    "Kuřecí plátek s bramborovou kaší a zeleninovou oblohou",
                )
                for index in range(60)
            )
            report = ReportData(
                menus=(MenuSummary("Oběd", 1, 60, "Kuřecí plátek"),),
                categories=(CategorySummary("Z1", "Žáci", "A", 60),),
                norms=(NormMenuSummary("Oběd", "A", 1, 60),),
                diners=diners,
                subject_name="ZŠ Kozinova",
            )

            created = create_pdf(config, report)

            from pypdf import PdfReader

            reader = PdfReader(str(created))
            self.assertGreater(len(reader.pages), 1)
            self.assertLess(
                float(reader.pages[0].mediabox.width),
                float(reader.pages[0].mediabox.height),
            )
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("ZŠ Kozinova", text)
            self.assertIn("Žák 059", text)

    def test_pdf_summary_tables_follow_both_visibility_switches(self):
        from pypdf import PdfReader

        report = ReportData(
            menus=(MenuSummary("Oběd", 1, 1, "Kaše"),),
            categories=(CategorySummary("Z1", "Žáci", "A", 1),),
            norms=(NormMenuSummary("Oběd", "A", 1, 1),),
            diners=(
                DinerOrder("Novák Jan", "Z1", "Žáci", "Oběd", 1, "A", "Kaše"),
            ),
            subject_name="ZŠ Testovací",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            for show_categories in (False, True):
                for show_norms in (False, True):
                    with self.subTest(
                        dle_kategorii=show_categories,
                        dle_norem=show_norms,
                    ):
                        output = Path(temp_dir) / (
                            f"sestava_{int(show_categories)}_{int(show_norms)}.pdf"
                        )
                        config = AppConfig(
                            database={},
                            report_date=date(2026, 8, 5),
                            categories=("Z1",),
                            language="česky",
                            menu_list_number=1,
                            show_by_categories=show_categories,
                            show_by_norms=show_norms,
                            pdf_output=output,
                            pdf_orientation="na_vysku",
                        )
                        create_pdf(config, report)
                        text = "\n".join(
                            page.extract_text() or ""
                            for page in PdfReader(str(output)).pages
                        )
                        self.assertEqual(
                            "Přihlášky podle kategorií" in text,
                            show_categories,
                        )
                        self.assertEqual(
                            "Objednaná menu podle norem" in text,
                            show_norms,
                        )
                        self.assertIn("Jídelníček a počty porcí", text)
                        self.assertIn("Jmenný seznam strávníků", text)


class QueryRegressionTests(unittest.TestCase):
    def test_uses_menu_designation_instead_of_internal_type_id(self):
        self.assertIn("JOIN public.typstrj AS t", SUMMARY_QUERY)
        self.assertIn("t.oznaceni::integer AS menu", SUMMARY_QUERY)
        self.assertNotIn("m.idtypstrj::integer AS menu", SUMMARY_QUERY)

    def test_starts_from_real_orders_and_does_not_add_zero_rows(self):
        self.assertIn("FROM objednavky AS o", SUMMARY_QUERY)
        self.assertIn("LEFT JOIN jidla AS j", SUMMARY_QUERY)
        self.assertNotIn("FULL OUTER JOIN", SUMMARY_QUERY)

    def test_category_summary_uses_category_name_norm_and_real_orders(self):
        self.assertIn("k.nazev", CATEGORY_SUMMARY_QUERY)
        self.assertIn("k.norma", CATEGORY_SUMMARY_QUERY)
        self.assertIn("COUNT(p.id)::integer", CATEGORY_SUMMARY_QUERY)
        self.assertIn("p.{day_column} ~ '^[1-9]$'", CATEGORY_SUMMARY_QUERY)
        self.assertIn("BTRIM(k.oznaceni) = v.oznaceni", CATEGORY_SUMMARY_QUERY)

    def test_norm_menu_summary_groups_by_meal_norm_and_menu(self):
        self.assertIn("JOIN public.kategor AS k", NORM_MENU_QUERY)
        self.assertIn("p.typsluzby AS typ_stravy", NORM_MENU_QUERY)
        self.assertIn("k.norma", NORM_MENU_QUERY)
        self.assertIn("p.{day_column}::integer AS menu", NORM_MENU_QUERY)
        self.assertIn("BTRIM(s.kategorie) = ANY", NORM_MENU_QUERY)

    def test_diner_list_joins_real_orders_to_menu_names(self):
        self.assertIn("NULLIF(BTRIM(s.jmeno), '') AS jmeno", DINER_LIST_QUERY)
        self.assertIn("JOIN public.kategor AS k", DINER_LIST_QUERY)
        self.assertIn("LEFT JOIN jidla AS j", DINER_LIST_QUERY)
        self.assertIn("p.{day_column} ~ '^[1-9]$'", DINER_LIST_QUERY)
        self.assertIn("ORDER BY", DINER_LIST_QUERY)
        self.assertIn("LOWER(BTRIM(s.jmeno)) NULLS LAST", DINER_LIST_QUERY)
        self.assertIn("BTRIM(k.oznaceni) AS kategorie_oznaceni", DINER_LIST_QUERY)

    def test_subject_name_is_loaded_from_parameters(self):
        self.assertIn("FROM public.parametry", SUBJECT_NAME_QUERY)
        self.assertIn("LOWER(BTRIM(sekce))", SUBJECT_NAME_QUERY)
        self.assertIn("BACKUP", SUBJECT_NAME_QUERY)
        self.assertIn("LOWER(BTRIM(parametr))", SUBJECT_NAME_QUERY)
        self.assertIn("NameSubject", SUBJECT_NAME_QUERY)

    def test_jidelna_period_parses_tento_mesic_and_rok(self):
        self.assertEqual(
            parse_jidelna_period(
                [("tentomesic", "7"), ("tentorok", "2026")]
            ),
            (2026, 7),
        )
        with self.assertRaisesRegex(ConfigError, "TentoMesic"):
            parse_jidelna_period([("tentorok", "2026")])
        cursor = Mock()
        cursor.fetchall.return_value = []
        self.assertIsNone(peek_jidelna_period(cursor))


if __name__ == "__main__":
    unittest.main()
