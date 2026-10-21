import json
import inspect
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import stravovaci_nicegui as gui
import ui_widgets as w


class NiceGuiHelperTests(unittest.TestCase):
    def test_emphasized_ui_has_readable_typography_and_active_tab(self):
        self.assertIn("--app-text", gui.UI_CSS)
        self.assertIn("font-size: var(--app-text)", gui.UI_CSS)
        self.assertIn(".q-tab--active", gui.UI_CSS)
        self.assertIn("blocks-emphasized", gui.UI_CSS)
        self.assertIn("border-left: 3px solid var(--app-primary)", gui.UI_CSS)
        self.assertIn("min-height: var(--app-control-min)", gui.UI_CSS)

    def test_admin_can_choose_ui_text_size(self):
        self.assertEqual(gui.peek_ui_text_size({}), "stredni")
        self.assertEqual(gui.peek_ui_text_size({"ui_velikost_textu": "velka"}), "velka")
        self.assertEqual(gui.peek_ui_text_size({"ui_velikost_textu": "obri"}), "stredni")
        self.assertEqual(gui.UI_TEXT_SIZE_PX["text"]["mala"], 14)
        self.assertEqual(gui.UI_TEXT_SIZE_PX["nadpis"]["extra"], 22)
        self.assertEqual(gui.UI_TEXT_SIZE_PX["popis"]["stredni"], 13)
        appearance = gui.peek_ui_appearance(
            {
                "ui_velikost_textu": "mala",
                "ui_velikost_nadpisu": "velka",
                "ui_velikost_popisu": "extra",
                "ui_barevne_schema": "svestkova",
                "ui_zvyrazneni_bloku": True,
            }
        )
        self.assertEqual(appearance["text"], "mala")
        self.assertEqual(appearance["nadpis"], "velka")
        self.assertEqual(appearance["popis"], "extra")
        self.assertEqual(appearance["schema"], "svestkova")
        self.assertTrue(appearance["zvyrazneni"])
        self.assertEqual(gui.peek_ui_theme({"ui_barevne_schema": "neon"}), "horcicova")
        # Dříve uložená schémata se bezpečně převedou na výchozí.
        self.assertEqual(gui.peek_ui_theme({"ui_barevne_schema": "tmave"}), "horcicova")
        self.assertEqual(gui.peek_ui_theme({"ui_barevne_schema": "svetle"}), "horcicova")
        self.assertEqual(set(gui.UI_THEMES), {"horcicova", "svestkova", "kremova"})
        self.assertFalse(gui.peek_ui_blocks({}))
        self.assertTrue(gui.peek_ui_blocks({"ui_zvyrazneni_bloku": "ano"}))
        self.assertEqual(gui.peek_ui_zoom({}), 100)
        self.assertEqual(gui.peek_ui_zoom({"ui_zoom": 125}), 125)
        self.assertEqual(gui.peek_ui_zoom({"ui_zoom": 200}), 150)
        self.assertEqual(gui.peek_ui_zoom({"ui_zoom": "abc"}), 100)
        self.assertEqual(gui.peek_ui_appearance({"ui_zoom": 125})["zoom"], 125)
        self.assertEqual(appearance["zoom"], 100)
        self.assertEqual(appearance["sablona"], "bezna")
        self.assertEqual(appearance["rozestupy"], "stredni")
        self.assertEqual(gui.peek_ui_template({}), "bezna")
        self.assertEqual(gui.peek_ui_template({"ui_sablona": "kompaktni"}), "kompaktni")
        self.assertEqual(gui.peek_ui_spacing({"ui_sablona": "kompaktni"}), "tesne")
        self.assertEqual(gui.peek_ui_spacing({"ui_rozestupy": "volne"}), "volne")
        self.assertEqual(gui.peek_ui_line({"ui_sablona": "pohodlna"}), "volne")
        self.assertEqual(gui.peek_ui_density({"ui_hustota_poli": "husta"}), "husta")
        self.assertEqual(gui.appearance_config(appearance)["ui_zoom"], 100)
        self.assertEqual(gui.appearance_config(appearance)["ui_sablona"], "bezna")
        self.assertIn("horcicova", gui.UI_THEMES)
        self.assertTrue(gui.UI_THEMES["horcicova"]["dark"])
        self.assertFalse(gui.UI_THEMES["kremova"]["dark"])
        self.assertIn("blocks-emphasized", gui.UI_CSS)
        self.assertIn("--app-gap", gui.UI_CSS)
        self.assertIn("--app-panel-pad", gui.UI_CSS)
        self.assertIn("padding: var(--app-panel-pad)", gui.UI_CSS)
        self.assertIn(".app-text {", gui.UI_CSS)
        self.assertIn("font-size: var(--app-heading)", gui.UI_CSS)
        self.assertIn("font-size: var(--app-help)", gui.UI_CSS)
        self.assertIn("zoom: var(--app-zoom)", gui.UI_CSS)
        self.assertIn("zoom:", inspect.getsource(gui.apply_ui_appearance))
        self.assertIn("--app-gap", inspect.getsource(gui.appearance_css_vars))
        collect_source = inspect.getsource(gui.NiceGuiApp._collect_config)
        self.assertIn("appearance_config", collect_source)
        self.assertIn("ui_barevne_schema", inspect.getsource(gui.appearance_config))
        self.assertIn("ui_zoom", inspect.getsource(gui.appearance_config))
        self.assertIn("ui_sablona", inspect.getsource(gui.appearance_config))
        self.assertIn("apply_ui_appearance", inspect.getsource(gui.NiceGuiApp.build))

    def test_admin_can_choose_one_of_three_ui_layout_templates(self):
        self.assertEqual(
            set(gui.UI_LAYOUT_LABELS), {"compact", "dashboard", "minimal"}
        )
        self.assertEqual(gui.DEFAULT_UI_LAYOUT, "compact")
        self.assertEqual(gui.peek_ui_layout({}), "compact")
        self.assertEqual(gui.peek_ui_layout({"ui_layout": "dashboard"}), "dashboard")
        self.assertEqual(gui.peek_ui_layout({"ui_layout": "nesmysl"}), "compact")
        self.assertEqual(gui.UI_LAYOUTS["dashboard"]["navigace"], "side")
        self.assertEqual(gui.UI_LAYOUTS["compact"]["navigace"], "top")
        self.assertEqual(gui.UI_LAYOUTS["minimal"]["karty"], "zadne")
        # Bez uloženého výběru předvolí hustotu zvolená šablona.
        self.assertEqual(gui.peek_ui_template({"ui_layout": "minimal"}), "kompaktni")
        self.assertEqual(gui.peek_ui_spacing({"ui_layout": "minimal"}), "tesne")
        self.assertEqual(gui.peek_ui_density({"ui_layout": "minimal"}), "husta")
        # Výběr se ukládá do configu a přežije restart.
        saved = gui.appearance_config(
            gui.peek_ui_appearance({"ui_layout": "dashboard"})
        )
        self.assertEqual(saved["ui_layout"], "dashboard")
        self.assertEqual(gui.peek_ui_layout(saved), "dashboard")
        classes = gui.appearance_html_classes({"ui_layout": "dashboard"})
        self.assertIn("layout-dashboard", classes)
        self.assertIn("nav-side", classes)
        self.assertIn("cards-vyrazne", classes)
        self.assertIn("layout-minimal", gui.appearance_html_classes({"ui_layout": "minimal"}))
        variables = gui.appearance_css_vars({"ui_layout": "dashboard"})
        self.assertEqual(variables["--app-nav-width"], "216px")
        self.assertIn("--app-radius", variables)
        self.assertIn("--app-field-min", variables)
        # Rozvržení navigace řídí CSS, aby přepnutí šablony neztratilo stav.
        self.assertIn("html.nav-side .workspace", gui.UI_CSS)
        self.assertIn("html.cards-zadne .app-card", gui.UI_CSS)
        # Přehledové dlaždice se staví vždy, zobrazuje je jen šablona s přehledem.
        self.assertIn("overview-on", gui.appearance_html_classes({"ui_layout": "dashboard"}))
        self.assertNotIn("overview-on", gui.appearance_html_classes({"ui_layout": "compact"}))
        self.assertIn("html.overview-on .overview-row", gui.UI_CSS)
        overview_source = inspect.getsource(gui.NiceGuiApp._build_daily_overview)
        self.assertIn("overview-row", overview_source)
        daily_source = inspect.getsource(gui.NiceGuiApp._build_daily_panel)
        self.assertIn("_build_daily_overview", daily_source)
        appearance_source = inspect.getsource(gui.NiceGuiApp._build_appearance_panel)
        self.assertIn("UI_LAYOUT_LABELS", appearance_source)
        self.assertIn("template-card", appearance_source)
        self.assertIn("LAYOUT_PREVIEWS", appearance_source)
        self.assertIn("Rozestupy prvků", appearance_source)
        self.assertIn("Řádkování textu", appearance_source)
        self.assertIn("Hustota polí", appearance_source)
        self.assertIn("Zvýraznit rámování", appearance_source)
        self.assertIn("Barevné schéma", appearance_source)
        self.assertIn("Přiblížení", appearance_source)
        self.assertIn("Nadpisy", appearance_source)
        self.assertIn("Popisy", appearance_source)
        self.assertIn("Běžný text", appearance_source)
        self.assertIn("_apply_style_template", appearance_source)
        self.assertIn("save_ui_appearance", appearance_source)
        self.assertIn("ui_layout", inspect.getsource(gui.NiceGuiApp.save_ui_appearance))

    def test_ui_defaults_to_browser_window(self):
        args = gui.parse_args([])
        self.assertFalse(args.browser)
        self.assertFalse(args.native)
        native_opts = gui.configure_ui_window(
            browser=False, native_window=True, port=12345
        )
        browser_opts = gui.configure_ui_window(
            browser=True, native_window=False, port=12345
        )
        self.assertTrue(browser_opts["show"])
        self.assertFalse(browser_opts["native"])
        if gui.native_ui_available():
            self.assertTrue(native_opts["native"])
            self.assertFalse(native_opts["show"])
            self.assertEqual(native_opts["window_size"], gui.NATIVE_WINDOW_SIZE)
        else:
            self.assertFalse(native_opts["native"])
            self.assertTrue(native_opts["show"])

    def test_connection_identity_panel_is_persistent_and_tabs_remain_available(self):
        init_source = inspect.getsource(gui.NiceGuiApp.__init__)
        build_source = inspect.getsource(gui.NiceGuiApp.build)
        invalidate_source = inspect.getsource(gui.NiceGuiApp.invalidate_connection)
        self.assertIn("BEZ SPOJENÍ", init_source)
        self.assertIn("open_database_settings", inspect.getsource(gui.NiceGuiApp))
        admin_source = inspect.getsource(gui.NiceGuiApp._build_admin_dialog)
        self.assertIn("keydown.enter", admin_source)
        self.assertIn("_submit_admin_dialog", admin_source)
        self.assertNotIn("connection_strip.set_visibility", build_source)
        self.assertNotIn("Nejprve otestujte připojení k databázi", build_source)
        self.assertNotIn("category_tab.disable", build_source)
        self.assertNotIn("category_tab.disable", invalidate_source)
        self.assertNotIn("pdf_tab.disable", invalidate_source)

    def test_connection_display_explicitly_updates_nicegui_elements(self):
        source = inspect.getsource(gui.NiceGuiApp.set_connection_display)
        self.assertIn("DB OK", source)
        self.assertIn("BEZ SPOJENÍ", source)
        self.assertIn("element.update()", source)

    def test_scheduler_help_points_to_jidelna_flags(self):
        self.assertIn("poctyemailem", gui.SCHEDULER_HELP_TEXT)
        self.assertIn("spustit_automaticky_export.bat", gui.SCHEDULER_HELP_TEXT)

    def test_admin_documents_cli_commands_without_gui(self):
        settings_source = inspect.getsource(gui.NiceGuiApp._build_admin_panel)
        cli_source = inspect.getsource(gui.NiceGuiApp._build_cli_help_panel)
        self.assertIn("_build_cli_help_panel", settings_source)
        self.assertIn("Spuštění bez GUI", cli_source)
        commands = " ".join(item["command"] for item in gui.CLI_COMMANDS)
        self.assertIn("--poctyemailem", commands)
        self.assertIn("--zaverka_072026", commands)
        self.assertIn("--zaverka_am", commands)
        self.assertIn("--z17_2026", commands)
        self.assertIn("GUI neotevřou", gui.CLI_HELP_INTRO)
        details = " ".join(item["detail"] for item in gui.CLI_COMMANDS)
        self.assertIn("varných", details)
        self.assertIn("FKSP", details)
        self.assertIn("Z 17-01", details)

    def test_output_path_picker_keeps_placeholders_and_filename(self):
        closing = gui.join_picked_directory(
            "vystup/uzaverka/{rok}-{mesic}",
            r"D:\Sestavy",
        )
        self.assertEqual(Path(closing), Path(r"D:\Sestavy") / "{rok}-{mesic}")
        special = gui.join_picked_directory("vystup/z17/{rok}", r"E:\Z17")
        self.assertEqual(Path(special), Path(r"E:\Z17") / "{rok}")
        pdf = gui.join_picked_directory(
            "vystup/AutoReport_{datum}.pdf",
            r"D:\PDF",
            filename="AutoReport_{datum}.pdf",
        )
        self.assertEqual(Path(pdf), Path(r"D:\PDF") / "AutoReport_{datum}.pdf")
        picker_source = inspect.getsource(gui.NiceGuiApp._output_path_field)
        widget_source = inspect.getsource(w.path_field)
        self.assertIn("path_field", picker_source)
        self.assertIn("Procházet", widget_source)
        self.assertIn("folder_open", widget_source)
        self.assertIn("pick_local_directory", inspect.getsource(gui.NiceGuiApp._browse_output_path))
        self.assertIn("_output_path_field", inspect.getsource(gui.NiceGuiApp._build_closing_panel))
        self.assertIn("_output_path_field", inspect.getsource(gui.NiceGuiApp._build_special_panel))
        special_source = inspect.getsource(gui.NiceGuiApp._build_special_panel)
        self.assertIn("Vytvořit podklad Z 17-01", special_source)
        self.assertIn("Jen zvolené", special_source)
        self.assertIn("Změnit výběr", special_source)
        self.assertIn("_open_item_picker_dialog", inspect.getsource(gui.NiceGuiApp.open_z17_category_dialog))
        self.assertIn("z17_selected_categories", inspect.getsource(gui.NiceGuiApp.__init__))
        self.assertIn("generate_z17", inspect.getsource(gui.NiceGuiApp))
        self.assertIn("_z17_category_caption", inspect.getsource(gui.NiceGuiApp))
        self.assertNotIn(
            "self.selected_categories",
            inspect.getsource(gui.NiceGuiApp._selected_z17_category_order),
        )
        self.assertIn("_output_path_field", inspect.getsource(gui.NiceGuiApp._build_pdf_settings_section))

    def test_existing_directory_for_dialog_walks_up_to_real_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            found = gui.existing_directory_for_dialog(
                str(root / "chybejici" / "{rok}-{mesic}"),
                config_directory=root,
            )
            self.assertEqual(Path(found), root)

    def test_user_tabs_are_unlocked_and_admin_is_password_gated(self):
        shell_source = "\n".join(
            inspect.getsource(method)
            for method in (
                gui.NiceGuiApp.build,
                gui.NiceGuiApp._build_topbar,
                gui.NiceGuiApp._build_workspace,
                gui.NiceGuiApp._build_navigation,
                gui.NiceGuiApp._build_panels,
            )
        ).replace("'", '"')
        init_source = inspect.getsource(gui.NiceGuiApp.__init__)
        admin_source = inspect.getsource(gui.NiceGuiApp._build_admin_panel)
        self.assertIn("Administrace", shell_source)
        self.assertIn('value="daily"', shell_source)
        self.assertIn("admin_unlocked", init_source)
        self.assertIn("_build_scheduler_panel", admin_source)
        self.assertIn("_build_appearance_panel", admin_source)
        self.assertIn("_build_mail_panel", admin_source)
        self.assertIn("_build_db_panel", admin_source)
        self.assertIn("admin-nav", admin_source)
        self.assertIn('label="Denní stav"', shell_source)
        self.assertIn('label="Uzávěrka"', shell_source)
        self.assertIn('label="Speciál"', shell_source)
        self.assertIn('label="Hromadná zpráva"', shell_source)
        self.assertIn("_build_daily_panel", shell_source)
        self.assertIn("_build_special_panel", shell_source)
        self.assertIn("_build_bulk_panel", shell_source)
        admin_tabs = shell_source[
            shell_source.find("self.admin_tab_elements") : shell_source.find(
                "self._apply_admin_visibility"
            )
        ]
        self.assertNotIn("daily_tab", admin_tabs)
        self.assertNotIn("closing_tab", admin_tabs)
        self.assertNotIn("special_tab", admin_tabs)
        self.assertNotIn("bulk_tab", admin_tabs)
        bulk_source = inspect.getsource(gui.NiceGuiApp._build_bulk_panel)
        self.assertIn("FILTER_LABELS", bulk_source)
        self.assertIn("FILTER_CLASS", bulk_source)
        self.assertIn("campaign", bulk_source)
        self.assertIn("Změnit výběr", bulk_source)
        self.assertIn("bulk_preview_summary", inspect.getsource(gui.NiceGuiApp._render_bulk_preview))
        self.assertIn("_open_item_picker_dialog", inspect.getsource(gui.NiceGuiApp))
        self.assertIn("picker-row", inspect.getsource(w.open_picker_dialog))
        self.assertIn("Vybrat vše", inspect.getsource(w.open_picker_dialog))
        self.assertIn("Zrušit vše", inspect.getsource(w.open_picker_dialog))
        self.assertIn("Hledat", inspect.getsource(w.open_picker_dialog))
        self.assertIn("pointer-events: none", gui.UI_CSS)
        self.assertIn("_bind_dialog_enter", inspect.getsource(gui.NiceGuiApp))
        daily_source = inspect.getsource(gui.NiceGuiApp._build_category_panel)
        admin_categories = inspect.getsource(gui.NiceGuiApp._build_category_settings_panel)
        self.assertIn("Změnit výběr", daily_source)
        self.assertIn("count-badge", daily_source)
        self.assertIn("Změnit výběr", admin_categories)
        self.assertIn("Jen vybrané kategorie", admin_categories)
        self.assertIn("_build_category_settings_panel", inspect.getsource(gui.NiceGuiApp._build_admin_panel))
        self.assertIn("Seznam strávníků", inspect.getsource(gui.NiceGuiApp._build_pdf_settings_section))
        self.assertIn("meal_type_select", inspect.getsource(gui.NiceGuiApp._build_daily_panel))
        self.assertIn("allowed_categories", inspect.getsource(gui.NiceGuiApp.open_daily_category_dialog))
        self.assertIn("admin_unlocked", inspect.getsource(gui.NiceGuiApp.open_allowed_category_dialog))
        self.assertIn("_manual_daily_categories", inspect.getsource(gui.NiceGuiApp.generate_pdf))
        self.assertIn("_manual_daily_categories", inspect.getsource(gui.NiceGuiApp.send_mail))
        self.assertIn("go_home", inspect.getsource(gui.NiceGuiApp._build_topbar))
        self.assertIn('self.tabs.value = "daily"', inspect.getsource(gui.NiceGuiApp.go_home))
        self.assertIn("width: 246px", gui.UI_CSS)

        self.assertIn("open_daily_category_dialog", daily_source)
        special_picker = inspect.getsource(gui.NiceGuiApp._build_special_panel)
        self.assertIn("open_z17_category_dialog", special_picker)
        closing_source = inspect.getsource(gui.NiceGuiApp._build_closing_panel)
        self.assertIn("ZIP", closing_source)
        self.assertIn("Odeslat e-mailem", closing_source)
        self.assertIn("save_closing_settings", closing_source)
        daily_panel = inspect.getsource(gui.NiceGuiApp._build_daily_panel)
        self.assertNotIn("my-6", daily_panel)
        self.assertIn("Pokročilé nastavení PDF", daily_panel)
        self.assertIn("_build_pdf_settings_section", daily_panel)
        self.assertIn("_build_pdf_panel", daily_panel)
        self.assertIn("_build_date_field", daily_panel)
        pdf_settings = inspect.getsource(gui.NiceGuiApp._build_pdf_settings_section)
        self.assertIn("form_grid(4)", pdf_settings)
        self.assertIn("tooltip", inspect.getsource(w.setting_switch))
        pdf_actions = inspect.getsource(gui.NiceGuiApp._build_pdf_panel)
        self.assertIn("Vytvořit PDF", pdf_actions)
        self.assertIn("Vytvořit a odeslat", pdf_actions)
        self.assertIn("action_bar", pdf_actions)
        self.assertIn("grow=True", special_picker)
        self.assertIn("padding: var(--app-panel-pad)", gui.UI_CSS)
        mail_source = inspect.getsource(gui.NiceGuiApp._build_mail_panel)
        self.assertIn("FUNCTION_LABELS", mail_source)
        self.assertIn("E-maily funkcí", mail_source)

    def test_sticky_actions_and_compact_status_keep_viewport_short(self):
        self.assertIn(".action-bar", gui.UI_CSS)
        self.assertIn("position: sticky", gui.UI_CSS)
        self.assertIn(".status-pill", gui.UI_CSS)
        self.assertIn(".stat-card", gui.UI_CSS)
        self.assertIn(".chip-row", gui.UI_CSS)
        self.assertIn("form-grid-4", gui.UI_CSS)
        self.assertIn("@media (max-width: 1180px)", gui.UI_CSS)
        topbar = inspect.getsource(gui.NiceGuiApp._build_topbar)
        self.assertIn("app-topbar", topbar)
        self.assertIn("connection_tooltip", topbar)
        self.assertIn("open_database_settings", topbar)
        self.assertIn("Administrace", topbar)

    def test_secrets_have_no_visibility_toggle_and_manual_save_is_removed(self):
        db_source = inspect.getsource(gui.NiceGuiApp._build_db_panel)
        mail_source = inspect.getsource(gui.NiceGuiApp._build_mail_panel)
        build_source = inspect.getsource(gui.NiceGuiApp.build)
        self.assertIn("password=True", db_source)
        self.assertIn("password=True", mail_source)
        self.assertIn("**kwargs", inspect.getsource(w.setting_input))
        self.assertNotIn("password_toggle_button", db_source)
        self.assertNotIn("password_toggle_button", mail_source)
        self.assertNotIn("Uložit nastavení", build_source)
        self.assertIn("BRAND_FOOTER", build_source)
        self.assertEqual(gui.BRAND_FOOTER, "DataShip by HanzG")

    def test_both_pdf_actions_automatically_persist_settings(self):
        generate_source = inspect.getsource(gui.NiceGuiApp.generate_pdf)
        send_source = inspect.getsource(gui.NiceGuiApp.send_mail)
        persist_source = inspect.getsource(gui.NiceGuiApp._persist_settings)
        self.assertIn("await self._persist_settings()", generate_source)
        self.assertIn(
            "await self._persist_settings(require_api_key=True)", send_source
        )
        self.assertIn("set_password", persist_source)
        self.assertIn("set_resend_api_key", persist_source)
        self.assertIn("write_config", persist_source)

    def test_last_browser_client_shutdowns_server(self):
        current = SimpleNamespace(is_deleted=False)
        other = SimpleNamespace(is_deleted=False)
        with mock.patch.object(gui.app, "clients", return_value=iter([current])), mock.patch.object(
            gui.app, "shutdown"
        ) as shutdown:
            gui.shutdown_when_last_client_closes(current)
            shutdown.assert_called_once_with()
        with mock.patch.object(
            gui.app, "clients", return_value=iter([current, other])
        ), mock.patch.object(gui.app, "shutdown") as shutdown:
            gui.shutdown_when_last_client_closes(current)
            shutdown.assert_not_called()

    def test_configured_date_uses_czech_config_format(self):
        self.assertEqual(gui.configured_date({"datum": "05.08.2026"}), date(2026, 8, 5))

    def test_configured_date_falls_back_to_today(self):
        self.assertEqual(gui.configured_date({"datum": "nesmysl"}), date.today())

    def test_parse_czech_date_accepts_required_format(self):
        self.assertEqual(gui.parse_czech_date("05.08.2026"), date(2026, 8, 5))

    def test_parse_czech_date_rejects_iso_format(self):
        with self.assertRaisesRegex(gui.ConfigError, "DD.MM.RRRR"):
            gui.parse_czech_date("2026-08-05")

    def test_parse_czech_date_rejects_non_padded_format(self):
        with self.assertRaisesRegex(gui.ConfigError, "DD.MM.RRRR"):
            gui.parse_czech_date("5.8.2026")

    def test_parse_czech_date_rejects_impossible_date(self):
        with self.assertRaisesRegex(gui.ConfigError, "DD.MM.RRRR"):
            gui.parse_czech_date("31.02.2026")

    def test_load_ui_config_uses_safe_example(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "config.json"
            raw = gui.load_ui_config(missing)
        self.assertNotIn("password", raw["databaze"])
        self.assertNotIn("resend_api_key", raw)

    def test_legacy_secrets_are_removed_from_written_config(self):
        raw = json.loads((Path(gui.__file__).with_name("config.example.json")).read_text(encoding="utf-8"))
        raw["databaze"]["password"] = "tajne-heslo"
        raw["resend_api_key"] = "re_test"
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps(raw), encoding="utf-8")
            with mock.patch.object(gui, "set_password"), mock.patch.object(gui, "set_resend_api_key"):
                gui.NiceGuiApp(config)
            stored = json.loads(config.read_text(encoding="utf-8"))
        self.assertNotIn("password", stored["databaze"])
        self.assertNotIn("resend_api_key", stored)

    def test_database_parameters_are_normalized(self):
        values = gui.database_parameters(
            {"databaze": {"host": " db.local ", "port": 5433, "dbname": " jid ", "user": " tech "}}
        )
        self.assertEqual(values["host"], "db.local")
        self.assertEqual(values["dbname"], "jid")
        self.assertEqual(values["user"], "tech")
        self.assertEqual(values["port"], 5433)

    def test_connection_identity_contains_subject_database_and_server(self):
        subject, details = gui.connection_identity(
            "  Školní jídelna U Parku  ",
            "vyvoj",
            {"host": "127.0.0.1", "port": 5433},
        )
        self.assertEqual(subject, "Školní jídelna U Parku")
        self.assertEqual(details, "Databáze: vyvoj · Server: 127.0.0.1:5433")
        with_period, period_details = gui.connection_identity(
            "Školní jídelna U Parku",
            "vyvoj",
            {"host": "127.0.0.1", "port": 5433},
            (2026, 7),
        )
        self.assertEqual(with_period, "Školní jídelna U Parku")
        self.assertIn("Aktuální měsíc: červenec 2026 (072026)", period_details)

    def test_database_test_reads_same_subject_name_as_pdf(self):
        cursor = mock.MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [
            ("vyvoj",),
            ("Školní jídelna U Parku",),
            ("0",),
            ("0",),
        ]
        cursor.fetchall.side_effect = [
            [("MŠ T", "Mateřská škola")],
            [("tentomesic", "7"), ("tentorok", "2026")],
        ]
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        fake_psycopg = SimpleNamespace(connect=mock.Mock(return_value=connection))
        database = {
            "host": "127.0.0.1",
            "port": 5433,
            "dbname": "vyvoj",
            "user": "postgres",
        }

        with mock.patch.dict(sys.modules, {"psycopg": fake_psycopg}), mock.patch(
            "services.database.set_password"
        ):
            categories, database_name, subject_name, jidelna_period = (
                gui.NiceGuiApp._test_database(database, "tajne")
            )

        self.assertEqual(categories, [("MŠ T", "Mateřská škola")])
        self.assertEqual(database_name, "vyvoj")
        self.assertEqual(subject_name, "Školní jídelna U Parku")
        self.assertEqual(jidelna_period, (2026, 7))
        executed = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn(gui.SUBJECT_NAME_QUERY, executed)
        self.assertTrue(
            any("pouzivatcenik" in query.lower() for query in executed),
            msg="TEST DB má načítat i cenový režim.",
        )
        self.assertTrue(any("TentoMesic" in query for query in executed))
        self.assertTrue(any("TentoRok" in query for query in executed))


if __name__ == "__main__":
    unittest.main()

