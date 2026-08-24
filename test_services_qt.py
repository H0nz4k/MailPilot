"""Testy servisní vrstvy pro desktopové rozhraní (bez Qt)."""

import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from services import (
    config_io,
    daily,
    database,
    environment,
    jidelnasql_warning,
    mail_settings,
    pdf_settings,
    scheduler,
    ui_settings,
    user_overview,
)
from stravovaci_sestava import ConfigError


class UiSettingsTests(unittest.TestCase):
    def test_defaults_for_config_without_ui_block(self):
        settings = ui_settings.peek_ui_settings({})
        self.assertEqual(settings.theme, ui_settings.THEME_LIGHT)
        self.assertEqual(settings.ui_scale, ui_settings.DEFAULT_UI_SCALE)
        self.assertEqual(settings.window_width, ui_settings.DEFAULT_WINDOW_WIDTH)
        self.assertFalse(settings.maximized)
        self.assertIsNone(settings.window_x)

    def test_legacy_nicegui_theme_migrates_to_dark(self):
        settings = ui_settings.peek_ui_settings({"ui_barevne_schema": "tmave"})
        self.assertEqual(settings.theme, ui_settings.THEME_DARK)

    def test_legacy_light_theme_variants_stay_light(self):
        for value in ("svetle", "ocean", "pisek", "nesmysl", None):
            with self.subTest(value=value):
                settings = ui_settings.peek_ui_settings({"ui_barevne_schema": value})
                self.assertEqual(settings.theme, ui_settings.THEME_LIGHT)

    def test_legacy_field_density_maps_to_scale(self):
        self.assertEqual(
            ui_settings.peek_ui_settings({"ui_hustota_poli": "husta"}).ui_scale,
            1.0,
        )
        self.assertGreater(
            ui_settings.peek_ui_settings({"ui_hustota_poli": "volna"}).ui_scale,
            1.0,
        )

    def test_legacy_density_in_ui_block_maps_to_scale(self):
        settings = ui_settings.peek_ui_settings({"ui": {"density": "comfortable"}})
        self.assertGreater(settings.ui_scale, 1.0)

    def test_ui_block_is_read_back(self):
        raw = {
            "ui": {
                "theme": "dark",
                "ui_scale": 1.25,
                "window_width": 1440,
                "window_height": 900,
                "window_x": 120,
                "window_y": 60,
                "maximized": True,
            }
        }
        settings = ui_settings.peek_ui_settings(raw)
        self.assertEqual(settings.theme, "dark")
        self.assertEqual(settings.ui_scale, 1.25)
        self.assertEqual((settings.window_width, settings.window_height), (1440, 900))
        self.assertEqual((settings.window_x, settings.window_y), (120, 60))
        self.assertTrue(settings.maximized)

    def test_scale_is_clamped_to_supported_range(self):
        self.assertEqual(ui_settings.normalize_scale(0.2), ui_settings.MIN_UI_SCALE)
        self.assertEqual(ui_settings.normalize_scale(9.0), ui_settings.MAX_UI_SCALE)
        self.assertEqual(ui_settings.normalize_scale("nesmysl"), 1.0)

    def test_zoom_steps_move_between_offered_sizes(self):
        settings = ui_settings.UiSettings()
        bigger = settings.zoomed(1)
        self.assertGreater(bigger.ui_scale, settings.ui_scale)
        self.assertEqual(bigger.zoomed(-1).ui_scale, settings.ui_scale)
        top = ui_settings.UiSettings(ui_scale=ui_settings.MAX_UI_SCALE)
        self.assertEqual(top.zoomed(1).ui_scale, ui_settings.MAX_UI_SCALE)

    def test_system_theme_is_kept(self):
        settings = ui_settings.peek_ui_settings({"ui": {"theme": "system"}})
        self.assertEqual(settings.theme, ui_settings.THEME_SYSTEM)

    def test_apply_keeps_other_keys_and_drops_missing_position(self):
        raw = {"databaze": {"host": "127.0.0.1"}, "povolene_kategorie": ["1"]}
        settings = ui_settings.UiSettings(theme="dark", ui_scale=1.25)
        updated = ui_settings.apply_ui_settings(raw, settings)
        self.assertEqual(updated["databaze"], {"host": "127.0.0.1"})
        self.assertEqual(updated["povolene_kategorie"], ["1"])
        self.assertEqual(updated["ui"]["theme"], "dark")
        self.assertEqual(updated["ui"]["ui_scale"], 1.25)
        self.assertNotIn("window_x", updated["ui"])

    def test_geometry_is_clamped_to_minimum(self):
        settings = ui_settings.UiSettings().with_geometry(
            width=200, height=100, x=10, y=20, maximized=False
        )
        self.assertEqual(settings.window_width, ui_settings.MIN_WINDOW_WIDTH)
        self.assertEqual(settings.window_height, ui_settings.MIN_WINDOW_HEIGHT)
        self.assertEqual((settings.window_x, settings.window_y), (10, 20))

    def test_round_trip_through_json_is_stable(self):
        raw = ui_settings.apply_ui_settings({}, ui_settings.UiSettings())
        again = ui_settings.peek_ui_settings(json.loads(json.dumps(raw)))
        self.assertEqual(again, ui_settings.peek_ui_settings(raw))


class DailySettingsTests(unittest.TestCase):
    def test_peek_reads_values_from_config(self):
        raw = {
            "datum": "05.08.2026",
            "povolene_kategorie": ["1", "2"],
            "jazyk_jidelnicku": "anglicky",
            "cislo_jidelnicku": 2,
            "pdf_vystup": "vystup/x_{datum}.pdf",
            "pdf_orientace": "landscape",
            "pdf_velikost_dat": 8.5,
            "pdf_velikost_popisku": 9.0,
            "pdf_tucne": True,
            "kategor_separ": True,
            "dle_kategorii": False,
            "dle_norem": False,
        }
        settings = daily.peek_daily_settings(raw)
        self.assertEqual(settings.report_date, date(2026, 8, 5))
        self.assertEqual(settings.categories, ("1", "2"))
        self.assertEqual(settings.language, "anglicky")
        self.assertEqual(settings.menu_list_number, 2)
        self.assertEqual(settings.pdf_orientation, "na_sirku")
        self.assertEqual(settings.pdf_data_font_size, 8.5)
        self.assertTrue(settings.pdf_bold)
        self.assertTrue(settings.category_separation)
        self.assertFalse(settings.show_by_categories)
        self.assertFalse(settings.show_by_norms)

    def test_peek_prefers_pocty_block(self):
        raw = {
            "povolene_kategorie": ["1"],
            "poctyemailem": {"povolene_kategorie": ["2", "3"]},
        }
        self.assertEqual(daily.peek_daily_settings(raw).categories, ("2", "3"))

    def test_peek_uses_safe_defaults(self):
        settings = daily.peek_daily_settings({"cislo_jidelnicku": "x"})
        self.assertEqual(settings.menu_list_number, 1)
        self.assertEqual(settings.pdf_orientation, "na_vysku")
        self.assertEqual(settings.pdf_output, daily.DEFAULT_PDF_OUTPUT)
        self.assertEqual(settings.pdf_data_font_size, 7.4)

    def test_apply_writes_expected_keys_and_keeps_other_blocks(self):
        raw = {
            "uzaverka": {"sestavy": ["fksp"]},
            "z17": {"rok": 2026},
            "mail_prijemci": ["a@b.cz"],
            "poctyemailem": {"vsechny_kategorie": False},
        }
        settings = daily.DailySettings(
            report_date=date(2026, 8, 22),
            categories=("1", "2"),
            language="česky",
            menu_list_number=1,
            pdf_output="vystup/MailPilot_{datum}.pdf",
            pdf_orientation="na_vysku",
            pdf_data_font_size=8.5,
            pdf_label_font_size=9.0,
        )
        updated = daily.apply_daily_settings(raw, settings)
        self.assertEqual(updated["datum"], "22.08.2026")
        self.assertEqual(updated["povolene_kategorie"], ["1", "2"])
        self.assertEqual(
            updated["poctyemailem"],
            {"vsechny_kategorie": False, "povolene_kategorie": ["1", "2"]},
        )
        self.assertEqual(updated["uzaverka"], {"sestavy": ["fksp"]})
        self.assertEqual(updated["z17"], {"rok": 2026})
        self.assertEqual(updated["mail_prijemci"], ["a@b.cz"])
        self.assertEqual(updated["pdf_velikost_dat"], 8.5)

    def test_apply_removes_password_from_config(self):
        raw = {"databaze": {"host": "x", "password": "tajne"}}
        settings = daily.DailySettings(
            report_date=date(2026, 8, 22), categories=("1",)
        )
        updated = daily.apply_daily_settings(raw, settings)
        self.assertNotIn("password", updated["databaze"])

    def test_validation_rejects_empty_selection(self):
        settings = daily.DailySettings(report_date=date(2026, 8, 22))
        with self.assertRaises(ConfigError):
            daily.validate_daily_settings(settings)

    def test_validation_requires_pdf_extension(self):
        settings = daily.DailySettings(
            report_date=date(2026, 8, 22),
            categories=("1",),
            pdf_output="vystup/sestava.txt",
        )
        with self.assertRaises(ConfigError):
            daily.validate_daily_settings(settings)

    def test_validation_checks_font_size_range(self):
        settings = daily.DailySettings(
            report_date=date(2026, 8, 22),
            categories=("1",),
            pdf_data_font_size=25.0,
        )
        with self.assertRaises(ConfigError):
            daily.validate_daily_settings(settings)

    def test_peek_daily_mail_reads_recipients_and_sender(self):
        raw = {
            "mail_prijemci": ["a@b.cz", "c@d.cz"],
            "mail_text": "Dobrý den",
            "mail_jen_varne_dny": True,
            "mail_odesilatel": "odesilatel@b.cz",
        }
        mail = daily.peek_daily_mail(raw)
        self.assertEqual(mail.recipients, ("a@b.cz", "c@d.cz"))
        self.assertEqual(mail.body, "Dobrý den")
        self.assertTrue(mail.only_cooking_days)
        self.assertEqual(mail.sender, "odesilatel@b.cz")


class SelectionTests(unittest.TestCase):
    def test_summary_text(self):
        self.assertEqual(daily.selection_summary(18, 21), "18 z 21 vybráno")
        self.assertEqual(daily.selection_summary(0, 0), "0 vybráno")

    def test_moment_is_described_relative_to_today(self):
        now = datetime(2026, 8, 22, 9, 30)
        self.assertEqual(
            daily.describe_moment(datetime(2026, 8, 22, 8, 12), now=now),
            "dnes 08:12",
        )
        self.assertEqual(
            daily.describe_moment(datetime(2026, 8, 21, 17, 5), now=now),
            "včera 17:05",
        )
        self.assertEqual(
            daily.describe_moment(datetime(2026, 8, 5, 7, 0), now=now),
            "05.08.2026 07:00",
        )

    def test_recipients_phrase_uses_czech_declension(self):
        self.assertEqual(daily.recipients_phrase(1), "1 příjemci")
        self.assertEqual(daily.recipients_phrase(3), "3 příjemcům")

    def test_preview_shortens_long_selection(self):
        codes = [str(index) for index in range(1, 21)]
        preview = daily.selection_preview(codes, limit=5)
        self.assertTrue(preview.startswith("1, 2, 3, 4, 5"))
        self.assertIn("+ 15 dalších", preview)

    def test_preview_of_empty_selection(self):
        self.assertEqual(daily.selection_preview([]), "žádná kategorie")

    def test_restrict_categories_splits_missing_codes(self):
        kept, dropped = daily.restrict_categories(
            ["1", "2", "STARA"], ["1", "2", "3"]
        )
        self.assertEqual(kept, ("1", "2"))
        self.assertEqual(dropped, ("STARA",))

    def test_reconcile_keeps_valid_part_of_selection(self):
        result = daily.reconcile_categories(["1", "STARA"], ["1", "2", "3"])
        self.assertEqual(result.selected, ("1",))
        self.assertEqual(result.dropped, ("STARA",))
        self.assertFalse(result.selected_all)
        self.assertEqual(
            result.status_note(3),
            "z výběru vypadla 1 kategorie, která už v databázi není",
        )

    def test_reconcile_selects_all_when_nothing_matches(self):
        result = daily.reconcile_categories(["1DOB", "1HOL"], ["4", "5", "10"])
        self.assertEqual(result.selected, ("4", "5", "10"))
        self.assertEqual(result.dropped, ("1DOB", "1HOL"))
        self.assertTrue(result.selected_all)
        note = result.status_note(3)
        self.assertIn("vypadly 2 kategorie", note)
        self.assertIn("vybrány všechny 3 dostupné kategorie", note)

    def test_reconcile_selects_all_for_empty_selection(self):
        result = daily.reconcile_categories([], [str(index) for index in range(21)])
        self.assertEqual(len(result.selected), 21)
        self.assertEqual(result.dropped, ())
        self.assertTrue(result.selected_all)
        self.assertEqual(
            result.status_note(21), "vybráno všech 21 dostupných kategorií"
        )

    def test_reconcile_without_database_categories_keeps_empty(self):
        result = daily.reconcile_categories(["1"], [])
        self.assertEqual(result.selected, ())
        self.assertEqual(result.dropped, ("1",))
        self.assertFalse(result.selected_all)


class ActionStateTests(unittest.TestCase):
    def test_without_connection_nothing_runs(self):
        state = daily.action_state(
            connected=False, selected_categories=5, recipients=1, has_last_pdf=False
        )
        self.assertFalse(state.can_create)
        self.assertFalse(state.can_send)
        self.assertIn("připojení", state.reason)

    def test_without_categories_create_is_blocked(self):
        state = daily.action_state(
            connected=True, selected_categories=0, recipients=2, has_last_pdf=True
        )
        self.assertFalse(state.can_create)
        self.assertTrue(state.can_open_last)
        self.assertIn("kategorii", state.reason)

    def test_without_recipients_only_send_is_blocked(self):
        state = daily.action_state(
            connected=True, selected_categories=3, recipients=0, has_last_pdf=False
        )
        self.assertTrue(state.can_create)
        self.assertFalse(state.can_send)
        self.assertIn("příjemce", state.reason)

    def test_ready_state_enables_everything(self):
        state = daily.action_state(
            connected=True, selected_categories=3, recipients=2, has_last_pdf=True
        )
        self.assertTrue(state.can_create)
        self.assertTrue(state.can_send)
        self.assertTrue(state.can_open_last)
        self.assertEqual(state.reason, "")

    def test_busy_blocks_actions(self):
        state = daily.action_state(
            connected=True,
            selected_categories=3,
            recipients=2,
            has_last_pdf=True,
            busy=True,
        )
        self.assertFalse(state.can_create)
        self.assertFalse(state.can_send)


class OverviewTests(unittest.TestCase):
    def test_overview_maps_report_to_rows(self):
        report = SimpleNamespace(
            menus=(
                SimpleNamespace(
                    meal_type="Obed ", menu=1, portions=253, meal_name="Hrachová kaše"
                ),
                SimpleNamespace(meal_type="Obed", menu=2, portions=42, meal_name=None),
            ),
            diners=tuple(range(295)),
            categories=(),
            active_categories=("1", "2", "3"),
        )
        overview = daily.overview_from_report(report, date(2026, 8, 5))
        self.assertEqual(overview.report_date, date(2026, 8, 5))
        self.assertEqual(overview.rows[0].meal_type, "Obed")
        self.assertEqual(overview.rows[1].meal_name, "")
        self.assertEqual(overview.total_portions, 295)
        self.assertEqual(overview.diners, 295)
        self.assertEqual(overview.categories, 3)

    def test_empty_overview_has_no_portions(self):
        self.assertEqual(daily.DailyOverview().total_portions, 0)


class DatabaseServiceTests(unittest.TestCase):
    def _fake_psycopg(self):
        cursor = mock.MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [("vyvoj",), ("ZŠ Kozinova",)]
        cursor.fetchall.side_effect = [
            [("1", "Žáci"), ("HOST", "")],
            [("tentomesic", "7"), ("tentorok", "2026")],
        ]
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        return SimpleNamespace(connect=mock.Mock(return_value=connection)), cursor

    def test_probe_connection_reads_identity_and_categories(self):
        fake, cursor = self._fake_psycopg()
        parameters = {
            "host": "127.0.0.1",
            "port": 5433,
            "dbname": "vyvoj",
            "user": "postgres",
        }
        with mock.patch.dict(sys.modules, {"psycopg": fake}), mock.patch(
            "services.database.set_password"
        ) as remember:
            info = database.probe_connection(parameters, "tajne")

        self.assertEqual(info.categories, (("1", "Žáci"), ("HOST", "")))
        self.assertEqual(info.database_name, "vyvoj")
        self.assertEqual(info.subject_name, "ZŠ Kozinova")
        self.assertEqual(info.period, (2026, 7))
        self.assertEqual(info.period_label, "07/2026")
        self.assertEqual(info.name, "ZŠ Kozinova")
        self.assertIn("127.0.0.1:5433", info.details)
        remember.assert_called_once()
        executed = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn("public.kategor", executed[1])

    def test_probe_connection_can_skip_saving_password(self):
        fake, _cursor = self._fake_psycopg()
        with mock.patch.dict(sys.modules, {"psycopg": fake}), mock.patch(
            "services.database.set_password"
        ) as remember:
            database.probe_connection(
                {"host": "h", "port": 1, "dbname": "d", "user": "u"},
                "tajne",
                remember=False,
            )
        remember.assert_not_called()

    def test_stored_password_returns_empty_text_when_missing(self):
        with mock.patch("services.database.get_password", return_value=None):
            self.assertEqual(database.stored_password({"host": "h"}), "")


class ConfigIoTests(unittest.TestCase):
    def test_normalize_database_requires_mandatory_fields(self):
        with self.assertRaises(ConfigError):
            config_io.normalize_database({"host": "", "port": 5432, "dbname": "d", "user": "u"})

    def test_normalize_database_validates_port(self):
        with self.assertRaises(ConfigError):
            config_io.normalize_database(
                {"host": "h", "port": 0, "dbname": "d", "user": "u"}
            )
        with self.assertRaises(ConfigError):
            config_io.normalize_database(
                {"host": "h", "port": "abc", "dbname": "d", "user": "u"}
            )

    def test_normalize_database_trims_values(self):
        values = config_io.normalize_database(
            {"host": " 127.0.0.1 ", "port": "5433", "dbname": " vyvoj ", "user": " pg "}
        )
        self.assertEqual(values["host"], "127.0.0.1")
        self.assertEqual(values["port"], 5433)
        self.assertEqual(values["dbname"], "vyvoj")
        self.assertEqual(values["user"], "pg")
        self.assertEqual(values["sslmode"], "prefer")

    def test_save_raw_config_writes_without_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config_io.save_raw_config(
                path, {"databaze": {"host": "h", "password": "tajne"}}
            )
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("password", saved["databaze"])


class JidelnaWarningTests(unittest.TestCase):
    def test_show_and_clear_warning_block(self):
        template = """
<div id="info-system">
  <div class="info-content">
    <p><span class="popis">Export:</span><span id="synchronizace-export">včera</span></p>
  </div>
</div>
""".strip()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.template.html"
            path.write_text(template, encoding="utf-8")
            settings = jidelnasql_warning.JidelnaWarningSettings(
                enabled=True, template_path=path
            )
            note = jidelnasql_warning.show_jidelnasql_mail_warning(
                settings, when=datetime(2026, 8, 23, 15, 20)
            )
            self.assertIsNone(note)
            content = path.read_text(encoding="utf-8")
            self.assertIn(jidelnasql_warning.BEGIN, content)
            self.assertIn("23.08.2026 15:20", content)
            self.assertTrue(
                path.with_name(path.name + ".mailpilot-backup").is_file()
            )
            self.assertIsNone(jidelnasql_warning.clear_jidelnasql_mail_warning(settings))
            self.assertNotIn(
                jidelnasql_warning.BEGIN, path.read_text(encoding="utf-8")
            )

    def test_detects_and_replaces_legacy_warning_marker(self):
        template = """
<div id="info-system">
  <div class="info-content">
    <p><span class="popis">Export:</span><span id="synchronizace-export">včera</span></p>
    <!-- AUTOREPORT_AUTOMAIL_BEGIN -->
    <div>legacy warning</div>
    <!-- AUTOREPORT_AUTOMAIL_END -->
  </div>
</div>
""".strip()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.template.html"
            path.write_text(template, encoding="utf-8")
            settings = jidelnasql_warning.JidelnaWarningSettings(
                enabled=True, template_path=path
            )
            self.assertTrue(jidelnasql_warning.is_jidelnasql_mail_warning_active(settings))
            self.assertIsNone(jidelnasql_warning.show_jidelnasql_mail_warning(settings))
            content = path.read_text(encoding="utf-8")
            self.assertIn(jidelnasql_warning.MAILPILOT_BEGIN, content)
            self.assertNotIn(jidelnasql_warning.LEGACY_BEGIN, content)
            self.assertEqual(content.count(jidelnasql_warning.MAILPILOT_BEGIN), 1)
            self.assertIsNone(jidelnasql_warning.clear_jidelnasql_mail_warning(settings))
            self.assertFalse(
                jidelnasql_warning.is_jidelnasql_mail_warning_active(settings)
            )

    def test_warning_message_is_html_escaped(self):
        template = """
<div id="info-system">
  <div class="info-content">
    <p><span class="popis">Export:</span><span id="synchronizace-export">včera</span></p>
  </div>
</div>
""".strip()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.template.html"
            path.write_text(template, encoding="utf-8")
            settings = jidelnasql_warning.JidelnaWarningSettings(
                enabled=True, template_path=path
            )
            self.assertIsNone(
                jidelnasql_warning.show_jidelnasql_mail_warning(
                    settings, message="<smtp timeout>"
                )
            )
            content = path.read_text(encoding="utf-8")
            self.assertIn("&lt;smtp timeout&gt;", content)
            self.assertNotIn("<smtp timeout>", content)

    def test_warning_fails_safely_without_anchor(self):
        template = "<html><body><p>Bez anchoru</p></body></html>"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.template.html"
            path.write_text(template, encoding="utf-8")
            settings = jidelnasql_warning.JidelnaWarningSettings(
                enabled=True, template_path=path
            )
            note = jidelnasql_warning.show_jidelnasql_mail_warning(settings)
            self.assertIsNotNone(note)
            self.assertIn("anchor Export", str(note))
            self.assertEqual(path.read_text(encoding="utf-8"), template)

    def test_warning_write_is_atomic_without_leftover_temp_file(self):
        template = """
<div id="info-system">
  <div class="info-content">
    <p><span class="popis">Export:</span><span id="synchronizace-export">včera</span></p>
  </div>
</div>
""".strip()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.template.html"
            path.write_text(template, encoding="utf-8")
            settings = jidelnasql_warning.JidelnaWarningSettings(
                enabled=True, template_path=path
            )
            self.assertIsNone(jidelnasql_warning.show_jidelnasql_mail_warning(settings))
            tmp_path = path.with_name(f".{path.name}.tmp")
            self.assertFalse(tmp_path.exists())

    def test_warning_config_roundtrip(self):
        raw = {}
        settings = jidelnasql_warning.JidelnaWarningSettings(
            enabled=False, template_path=Path(r"C:\Gastro\Programy\Templates\dashboard.template.html")
        )
        saved = jidelnasql_warning.apply_warning_settings(raw, settings)
        loaded = jidelnasql_warning.peek_warning_settings(saved)
        self.assertFalse(loaded.enabled)
        self.assertEqual(loaded.template_path, settings.template_path)


class UserOverviewTests(unittest.TestCase):
    def test_overview_reports_next_run_and_last_success(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text("{}", encoding="utf-8")
            log_dir = Path(directory) / "logy"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "automaticky_export.log").write_text(
                "\n".join(
                    [
                        "2026-08-23 08:00:00 +0200 [WARN] test warning",
                        "2026-08-23 08:02:00 +0200 [OK] test ok",
                    ]
                ),
                encoding="utf-8",
            )
            job = scheduler.build_job(
                name="Denní stav",
                action=scheduler.ACTION_POCTY,
                schedule_type="daily",
                launcher=str(Path(directory) / "spustit_poctyemailem.bat"),
                enabled=True,
                time="09:30",
                config_directory=Path(directory),
            )
            scheduler.write_jobs(scheduler.scheduler_path(config), [job])
            with (
                mock.patch.object(
                    user_overview,
                    "peek_service_config",
                    return_value=SimpleNamespace(service_name="MailPilot_denniprehled"),
                ),
                mock.patch.object(
                    user_overview,
                    "read_runtime_snapshot",
                    return_value=SimpleNamespace(
                        running=True,
                        runtime_type="nssm",
                        service_name="MailPilot_denniprehled",
                        service_installed=True,
                        service_running=True,
                        service_account="DOMAIN\\user",
                        runtime_identity="DOMAIN\\user",
                        credential_ok=True,
                        credential_detail="OK",
                        last_heartbeat="2026-08-23 07:59:50",
                        last_run="2026-08-23 08:00:00",
                        last_result="OK",
                        next_run="2026-08-24 09:30:00",
                        last_error="—",
                    ),
                ),
            ):
                overview = user_overview.load_automail_overview(config)
        self.assertTrue(overview.configured)
        self.assertTrue(overview.enabled)
        self.assertEqual(overview.job_names, ("Denní stav",))
        self.assertEqual(overview.next_send_from, "Denní stav")
        self.assertIn("23.08.2026 08:02", overview.last_success)
        self.assertTrue(overview.next_send)
        self.assertEqual(len(overview.errors), 1)
        self.assertTrue(overview.runtime_running)
        self.assertEqual(overview.runtime_type, "nssm")
        self.assertTrue(overview.credential_ok)

    def test_retry_reports_success(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text("{}", encoding="utf-8")
            with (
                mock.patch.object(
                    user_overview,
                    "run_scheduled_export_with_retry",
                    return_value={
                        "status": "sent",
                        "path": Path("x.pdf"),
                        "recipients": ("a@b.cz",),
                        "detail": "",
                    },
                ),
                mock.patch.object(
                    user_overview,
                    "read_saved_settings",
                    return_value={},
                ),
            ):
                result = user_overview.retry_daily_mail(config)
        self.assertTrue(result.success)
        self.assertIn("Odesláno", result.message)

    def test_overview_does_not_show_active_next_run_when_runtime_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text("{}", encoding="utf-8")
            job = scheduler.build_job(
                name="Denní stav",
                action=scheduler.ACTION_POCTY,
                schedule_type="daily",
                launcher=str(Path(directory) / "spustit_poctyemailem.bat"),
                enabled=True,
                time="09:30",
                config_directory=Path(directory),
            )
            scheduler.write_jobs(scheduler.scheduler_path(config), [job])
            with (
                mock.patch.object(
                    user_overview,
                    "peek_service_config",
                    return_value=SimpleNamespace(service_name="MailPilot_denniprehled"),
                ),
                mock.patch.object(
                    user_overview,
                    "read_runtime_snapshot",
                    return_value=SimpleNamespace(
                        running=False,
                        runtime_type="not running",
                        service_name="MailPilot_denniprehled",
                        service_installed=False,
                        service_running=False,
                        service_account="—",
                        runtime_identity="DOMAIN\\user",
                        credential_ok=True,
                        credential_detail="OK",
                        last_heartbeat="—",
                        last_run="—",
                        last_result="—",
                        next_run="—",
                        last_error="—",
                    ),
                ),
            ):
                overview = user_overview.load_automail_overview(config)
        self.assertIn("runtime neběží", overview.next_send)


class MailSettingsTests(unittest.TestCase):
    def _raw(self):
        return {
            "mail_odesilatel": "podpora@altisima.cz",
            "mail_prijemci": ["reditel@skola.cz"],
            "mail_text": "Denní stav v příloze.",
            "mail_jen_varne_dny": True,
            "uzaverka": {"mail_prijemci": ["ucetni@skola.cz"], "mail_text": "Uzávěrka."},
            "z17": {"mail_prijemci": [], "mail_text": ""},
        }

    def test_each_function_keeps_its_own_recipients(self):
        settings = mail_settings.peek_mail_settings(self._raw())
        self.assertEqual(settings.sender, "podpora@altisima.cz")
        self.assertEqual(
            settings.function(mail_settings.FUNCTION_DAILY).recipients,
            ("reditel@skola.cz",),
        )
        self.assertTrue(
            settings.function(mail_settings.FUNCTION_DAILY).only_cooking_days
        )
        self.assertEqual(
            settings.function(mail_settings.FUNCTION_CLOSING).recipients,
            ("ucetni@skola.cz",),
        )
        self.assertEqual(
            settings.function(mail_settings.FUNCTION_SPECIAL).recipients, ()
        )

    def test_apply_writes_functions_to_their_config_blocks(self):
        settings = mail_settings.peek_mail_settings(self._raw())
        updated = settings.with_function(
            mail_settings.FUNCTION_SPECIAL,
            mail_settings.FunctionMail(recipients=("kraj@skola.cz",), body="Z 17-01."),
        )
        raw = mail_settings.apply_mail_settings(self._raw(), updated)
        self.assertEqual(raw["z17"]["mail_prijemci"], ["kraj@skola.cz"])
        self.assertEqual(raw["z17"]["mail_text"], "Z 17-01.")
        self.assertEqual(raw["mail_prijemci"], ["reditel@skola.cz"])
        self.assertEqual(raw["uzaverka"]["mail_prijemci"], ["ucetni@skola.cz"])

    def test_apply_never_stores_database_password(self):
        raw = dict(self._raw(), databaze={"host": "h", "password": "tajne"})
        saved = mail_settings.apply_mail_settings(
            raw, mail_settings.peek_mail_settings(raw)
        )
        self.assertNotIn("password", saved["databaze"])

    def test_add_recipient_validates_and_blocks_duplicates(self):
        added = mail_settings.add_recipient(("a@skola.cz",), " b@skola.cz ")
        self.assertEqual(added, ("a@skola.cz", "b@skola.cz"))
        with self.assertRaises(ConfigError):
            mail_settings.add_recipient(("a@skola.cz",), "A@Skola.cz")
        with self.assertRaises(ConfigError):
            mail_settings.add_recipient((), "bez zavinace")

    def test_empty_sender_falls_back_to_default(self):
        raw = mail_settings.apply_mail_settings({}, mail_settings.MailSettings())
        self.assertEqual(raw["mail_odesilatel"], mail_settings.DEFAULT_SENDER)


class SchedulerServiceTests(unittest.TestCase):
    def _job(self, **kwargs):
        values = {
            "name": "Denní stav",
            "action": scheduler.ACTION_POCTY,
            "schedule_type": "daily",
            "launcher": r"C:\AutoReport\AutoReport.exe",
            "enabled": True,
            "time": "6:5",
        }
        values.update(kwargs)
        return scheduler.build_job(**values)

    def test_build_job_normalizes_time(self):
        self.assertEqual(self._job().time, "06:05")

    def test_build_job_rejects_invalid_schedule(self):
        with self.assertRaises(ConfigError):
            self._job(time="25:00")
        with self.assertRaises(ConfigError):
            self._job(name="  ")

    def test_next_run_is_described_in_czech(self):
        reference = datetime(2026, 8, 22, 5, 0)
        job = self._job(time="06:30")
        self.assertEqual(scheduler.describe_next_run(job, reference=reference), "dnes 06:30")
        later = self._job(time="04:30")
        self.assertEqual(
            scheduler.describe_next_run(later, reference=reference), "zítra 04:30"
        )
        self.assertEqual(
            scheduler.describe_next_run(self._job(enabled=False), reference=reference),
            "—",
        )

    def test_command_matches_selected_function(self):
        closing = self._job(name="Uzávěrka", action=scheduler.ACTION_CLOSING)
        self.assertIn("--zaverka_", scheduler.describe_command(closing))

    def test_duplicate_names_are_refused(self):
        job = self._job()
        with self.assertRaises(ConfigError):
            scheduler.ensure_unique([job], self._job(name="denní stav"))

    def test_jobs_survive_save_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "planovac.json"
            scheduler.write_jobs(path, [self._job()])
            loaded = scheduler.read_jobs(path)
            self.assertEqual([job.name for job in loaded], ["Denní stav"])

    def test_scheduler_file_sits_next_to_config(self):
        path = scheduler.scheduler_path(Path("C:/app/config.json"))
        self.assertEqual(path.name, "planovac.json")
        self.assertEqual(path.parent.name, "app")


class PdfSettingsTests(unittest.TestCase):
    def _raw(self):
        return {
            "datum": "05.08.2026",
            "povolene_kategorie": ["1", "2"],
            "jazyk_jidelnicku": "česky",
            "pdf_orientace": "na_sirku",
            "pdf_velikost_dat": 8.5,
        }

    def test_peek_reads_pdf_part_of_daily_settings(self):
        settings = pdf_settings.peek_pdf_settings(self._raw())
        self.assertEqual(settings.orientation, "na_sirku")
        self.assertEqual(settings.data_font_size, 8.5)

    def test_apply_keeps_date_and_categories(self):
        raw = pdf_settings.apply_pdf_settings(
            self._raw(),
            pdf_settings.PdfSettings(orientation="na_vysku", menu_list_number=3),
        )
        self.assertEqual(raw["datum"], "05.08.2026")
        self.assertEqual(raw["povolene_kategorie"], ["1", "2"])
        self.assertEqual(raw["pdf_orientace"], "na_vysku")
        self.assertEqual(raw["cislo_jidelnicku"], 3)

    def test_invalid_output_is_refused(self):
        with self.assertRaises(ConfigError):
            pdf_settings.apply_pdf_settings(
                self._raw(), pdf_settings.PdfSettings(output="vystup/report.txt")
            )


class EnvironmentTests(unittest.TestCase):
    def test_cli_commands_use_current_period(self):
        commands = environment.cli_commands(reference=datetime(2026, 8, 22))
        joined = " ".join(item.command for item in commands)
        self.assertIn("--poctyemailem", joined)
        self.assertIn("--zaverka_072026", joined)
        self.assertIn("--z17_2026", joined)
        self.assertTrue(all(item.log for item in commands))

    def test_application_files_are_relative_to_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text("{}", encoding="utf-8")
            entries = {item.label: item for item in environment.application_files(config_path)}
            self.assertTrue(entries["Nastavení"].exists)
            self.assertEqual(entries["Plánovač"].path.name, "planovac.json")
            self.assertEqual(entries["Resend API klíč"].path.name, ".env")
            self.assertFalse(entries["Logy"].exists)

    def test_secret_locations_never_mention_config_file(self):
        lines = environment.secret_locations(
            {"host": "h", "port": 5432, "dbname": "d", "user": "u"}
        )
        self.assertTrue(any("Správce přihlašovacích údajů" in line for line in lines))
        self.assertFalse(any("config.json" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
