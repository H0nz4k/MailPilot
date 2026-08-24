"""Testy desktopového rozhraní: widgety, presenter logika, konfigurace.

Testy se přeskočí, pokud v prostředí není PySide6; business logika ani
konzolové režimy na nich nezávisí.
"""

import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

PYSIDE_AVAILABLE = importlib.util.find_spec("PySide6") is not None

if PYSIDE_AVAILABLE:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QDate, Qt
    from PySide6.QtWidgets import QApplication, QScrollArea

    from gui_qt import APP_VERSION
    from gui_qt.dialogs.categories import CategoryDialog
    from gui_qt.main_window import (
        PAGE_ADMIN,
        PAGE_BULK,
        PAGE_CLOSING,
        PAGE_DAILY,
        PAGE_SPECIAL,
        PAGE_USER,
        MainWindow,
    )
    from gui_qt.models import OverviewModel, RecipientModel
    from gui_qt.pages.admin import SECTION_APPEARANCE, SECTION_DATABASE
    from gui_qt.pages.bulk import BulkPage
    from gui_qt.pages.closing import ClosingPage
    from gui_qt.pages.daily import DailyPage
    from gui_qt.pages.special import SpecialPage
    from gui_qt.theme import build_stylesheet, metrics_for, palette_for, resolve_theme
    from gui_qt.widgets.common import SegmentedNav
    from gui_qt.widgets.header import STATE_ERROR, STATE_OK, HeaderBar
    from gui_qt.widgets.sidebar import SEPARATOR, NavItem, NavigationSidebar

from services.bulk import BulkForm
from services.closing import ClosingForm
from services.daily import ActionState, DailyOverview, DailySettings, OverviewRow
from services.database import ConnectionInfo
from services.special import SpecialForm
from services.ui_settings import (
    MAX_UI_SCALE,
    THEME_SYSTEM,
    UI_SCALES,
    UiSettings,
    peek_ui_settings,
)

ROOT = Path(__file__).resolve().parent


def _application():
    return QApplication.instance() or QApplication([])


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class ThemeTests(unittest.TestCase):
    def test_every_dimension_grows_with_scale(self):
        small = metrics_for(0.9)
        base = metrics_for(1.0)
        large = metrics_for(1.6)
        for name in (
            "control_height",
            "nav_item_height",
            "header_height",
            "row_height",
            "sidebar_width",
            "icon_size",
            "label_column",
            "margin",
            "section_gap",
        ):
            with self.subTest(name=name):
                self.assertLess(getattr(small, name), getattr(base, name))
                self.assertLess(getattr(base, name), getattr(large, name))
        self.assertLess(base.font_pt, large.font_pt)
        self.assertLess(base.heading_pt, large.heading_pt)

    def test_px_helper_follows_scale(self):
        self.assertEqual(metrics_for(1.0).px(100), 100)
        self.assertEqual(metrics_for(1.6).px(100), 160)
        self.assertGreaterEqual(metrics_for(0.9).px(1), 1)

    def test_unknown_values_fall_back_to_defaults(self):
        self.assertEqual(metrics_for("nesmysl"), metrics_for(1.0))
        self.assertEqual(palette_for("nesmysl"), palette_for("light"))

    def test_system_theme_resolves_to_light_or_dark(self):
        self.assertIn(resolve_theme(THEME_SYSTEM), ("light", "dark"))

    def test_stylesheet_uses_palette_and_metrics(self):
        for scale in (1.0, 1.6):
            for theme in ("light", "dark"):
                with self.subTest(theme=theme, scale=scale):
                    palette = palette_for(theme)
                    metrics = metrics_for(scale)
                    style = build_stylesheet(palette, metrics)
                    self.assertIn(palette.accent, style)
                    self.assertIn(f"{metrics.nav_item_height}px", style)
                    self.assertIn("QListWidget#NavSidebar", style)
                    self.assertNotIn("!important", style)

    def test_stylesheet_font_size_follows_scale(self):
        base = build_stylesheet(palette_for("light"), metrics_for(1.0))
        large = build_stylesheet(palette_for("light"), metrics_for(1.6))
        self.assertNotEqual(base, large)
        self.assertIn(f"{metrics_for(1.6).font_pt}pt", large)


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class ModelTests(unittest.TestCase):
    def test_overview_model_exposes_rows_and_headers(self):
        _application()
        model = OverviewModel()
        self.assertEqual(model.rowCount(), 0)
        model.set_rows(
            (
                OverviewRow("Obed", 1, "Hrachová kaše", 253),
                OverviewRow("Obed", 2, "Bulgur", 42),
            )
        )
        self.assertEqual(model.rowCount(), 2)
        self.assertEqual(model.columnCount(), 4)
        self.assertEqual(model.index(0, 2).data(), "Hrachová kaše")
        self.assertEqual(model.index(1, 3).data(), "42")
        self.assertEqual(model.headerData(3, Qt.Horizontal), "Porcí")

    def test_recipient_model_marks_missing_mail(self):
        _application()
        model = RecipientModel()
        model.set_rows(
            (
                ("Novák Jan", "3.A", "1", "jan@example.com"),
                ("Malá Eva", "3.A", "1", RecipientModel.MISSING),
            )
        )
        self.assertEqual(model.rowCount(), 2)
        self.assertEqual(model.index(0, 3).data(), "jan@example.com")
        tooltip = model.index(1, 3).data(Qt.ToolTipRole)
        self.assertIn("nemá", tooltip)


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class CategoryDialogTests(unittest.TestCase):
    def setUp(self):
        _application()
        self.options = [
            ("1", "Žáci"),
            ("1DOB", "Žáci doběh"),
            ("2", "Žáci 2"),
            ("HOST", "Hosté"),
        ]

    def test_preselected_codes_are_checked(self):
        dialog = CategoryDialog(self.options, ["1", "HOST"], metrics_for(1.0))
        self.assertEqual(dialog.selected_codes(), ("1", "HOST"))

    def test_select_all_and_clear_all(self):
        dialog = CategoryDialog(self.options, [], metrics_for(1.0))
        dialog._set_visible_checked(True)
        self.assertEqual(len(dialog.selected_codes()), 4)
        dialog._set_visible_checked(False)
        self.assertEqual(dialog.selected_codes(), ())

    def test_search_filters_and_bulk_action_touches_visible_only(self):
        dialog = CategoryDialog(self.options, [], metrics_for(1.0))
        dialog._apply_filter("host")
        dialog._set_visible_checked(True)
        self.assertEqual(dialog.selected_codes(), ("HOST",))
        dialog._apply_filter("")
        self.assertEqual(dialog.selected_codes(), ("HOST",))

    def test_summary_shows_selected_and_total(self):
        dialog = CategoryDialog(self.options, ["1"], metrics_for(1.0))
        self.assertEqual(dialog._summary.text(), "Vybráno: 1 / 4")

    def test_dialog_grows_with_ui_scale(self):
        small = CategoryDialog(self.options, [], metrics_for(1.0))
        large = CategoryDialog(self.options, [], metrics_for(1.6))
        self.assertGreater(large.width(), small.width())


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class SegmentedNavTests(unittest.TestCase):
    def test_selection_emits_key_and_marks_active(self):
        _application()
        nav = SegmentedNav(
            (("db", "Databáze"), ("mail", "E-maily")), metrics_for(1.0)
        )
        seen = []
        nav.section_selected.connect(seen.append)
        nav.select("mail")
        self.assertEqual(seen, ["mail"])
        self.assertEqual(nav.current_key(), "mail")
        self.assertEqual(nav._buttons["mail"].property("active"), "true")
        self.assertEqual(nav._buttons["db"].property("active"), "false")

    def test_silent_selection_does_not_emit(self):
        _application()
        nav = SegmentedNav((("db", "Databáze"), ("mail", "E-maily")), metrics_for(1.0))
        seen = []
        nav.section_selected.connect(seen.append)
        nav.select("db", notify=False)
        self.assertEqual(seen, [])
        self.assertEqual(nav.current_key(), "db")


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class DailyPageTests(unittest.TestCase):
    def setUp(self):
        _application()
        self.page = DailyPage(metrics_for(1.0), palette=palette_for("light"))

    def test_settings_round_trip(self):
        settings = DailySettings(
            report_date=date(2026, 8, 22),
            categories=("1", "2"),
            language="anglicky",
            menu_list_number=3,
            pdf_output="vystup/x_{datum}.pdf",
            pdf_orientation="na_sirku",
            pdf_data_font_size=8.5,
            pdf_label_font_size=9.0,
            pdf_bold=True,
            category_separation=True,
            show_by_categories=False,
            show_by_norms=False,
        )
        self.page.set_settings(settings)
        self.assertEqual(self.page.settings(), settings)

    def test_selection_label_shows_count_and_lists_codes_in_tooltip(self):
        self.page.set_category_options([(str(code), "") for code in range(1, 22)])
        self.page.set_selected_categories([str(code) for code in range(1, 22)])
        self.assertEqual(self.page._selection_label.text(), "21 z 21 vybráno")
        self.assertIn("1, 2, 3", self.page._selection_label.toolTip())

    def test_options_prune_unknown_selection(self):
        self.page.set_selected_categories(["1", "STARA"])
        self.page.set_category_options([("1", "Žáci")])
        self.assertEqual(self.page.selected_categories(), ("1",))

    def test_action_state_controls_buttons(self):
        self.page.set_action_state(ActionState(False, False, False, "důvod"))
        self.assertFalse(self.page._create.isEnabled())
        self.assertFalse(self.page._send.isEnabled())
        self.assertFalse(self.page._open_last.isEnabled())
        self.assertEqual(self.page._create.toolTip(), "důvod")
        self.page.set_action_state(ActionState(True, True, True))
        self.assertTrue(self.page._create.isEnabled())
        self.assertTrue(self.page._send.isEnabled())
        self.assertTrue(self.page._open_last.isEnabled())

    def test_advanced_section_starts_collapsed(self):
        self.assertFalse(self.page._advanced.is_expanded())
        self.assertFalse(self.page._advanced.content.isVisible())
        self.page._advanced.set_expanded(True)
        self.assertTrue(self.page._advanced.is_expanded())

    def test_overview_fills_table_and_summary(self):
        overview = DailyOverview(
            report_date=date(2026, 8, 5),
            rows=(OverviewRow("Obed", 1, "Kaše", 253),),
            diners=295,
            categories=21,
        )
        self.page.set_overview(overview)
        self.assertEqual(self.page._overview_model.rowCount(), 1)
        self.assertIn("253 porcí", self.page._overview_summary.text())
        self.page.clear_overview()
        self.assertEqual(self.page._overview_model.rowCount(), 0)

    def test_empty_state_is_visible_only_without_rows(self):
        self.page.resize(900, 600)
        self.page.show()
        QApplication.processEvents()
        self.page.clear_overview()
        self.assertTrue(self.page._empty_state.isVisible())
        self.page.set_overview(
            DailyOverview(rows=(OverviewRow("Obed", 1, "Kaše", 10),))
        )
        self.assertFalse(self.page._empty_state.isVisible())
        self.page.hide()

    def test_date_change_invalidates_overview(self):
        self.page.set_overview(
            DailyOverview(rows=(OverviewRow("Obed", 1, "Kaše", 10),))
        )
        self.page._date.setDate(QDate(2026, 8, 23))
        self.assertEqual(self.page._overview_model.rowCount(), 0)

    def test_page_fits_common_desktop_resolutions(self):
        for size in ((1920, 1080), (1366, 768)):
            with self.subTest(size=size):
                self.page.resize(*size)
                self.page.show()
                QApplication.processEvents()
                self.assertFalse(self.page.needs_scroll())
                self.page._advanced.set_expanded(True)
                QApplication.processEvents()
                self.assertFalse(self.page.needs_scroll())
                self.page._advanced.set_expanded(False)
        self.page.hide()


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class ScaledPageTests(unittest.TestCase):
    """Obsah se při větším zvětšení nesmí ořezávat."""

    def test_pages_fit_or_scroll_at_every_scale(self):
        _application()
        for scale in (UI_SCALES[0], 1.0, 1.25, MAX_UI_SCALE):
            metrics = metrics_for(scale)
            palette = palette_for("light")
            pages = (
                DailyPage(metrics, palette=palette),
                ClosingPage(metrics, palette=palette),
                SpecialPage(metrics, palette=palette),
                BulkPage(metrics, palette=palette),
            )
            for page in pages:
                with self.subTest(scale=scale, page=type(page).__name__):
                    page.resize(1366, 768)
                    page.show()
                    QApplication.processEvents()
                    self.assertLessEqual(
                        page.minimumSizeHint().width(), 1366
                    )
                    page.hide()
                    page.deleteLater()


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class WindowSizeTests(unittest.TestCase):
    """Okno musí jít zmenšit na 1366×768 i při největším zvětšení."""

    SMALL = (1366, 768)

    def setUp(self):
        _application()
        self.directory = Path(tempfile.mkdtemp(prefix="autoreport_qt_size_"))
        self.config = self.directory / "config.json"
        shutil.copy2(ROOT / "config.example.json", self.config)
        self.stored = mock.patch(
            "gui_qt.main_window.stored_password", return_value=""
        )
        self.stored.start()
        self.addCleanup(self.stored.stop)

    def _window(self, scale: float):
        raw = json.loads(self.config.read_text(encoding="utf-8"))
        window = MainWindow(self.config, peek_ui_settings(raw).with_scale(scale))
        self.addCleanup(window.deleteLater)
        window.setMinimumSize(0, 0)
        window.setAttribute(Qt.WA_DontShowOnScreen, True)
        window.show()
        window.resize(*self.SMALL)
        QApplication.processEvents()
        return window

    def test_window_fits_small_screen_at_every_scale(self):
        for scale in (1.0, 1.25, MAX_UI_SCALE):
            with self.subTest(scale=scale):
                window = self._window(scale)
                self.assertLessEqual(window.width(), self.SMALL[0])
                self.assertLessEqual(window.height(), self.SMALL[1])

    def test_no_page_is_clipped_at_largest_scale(self):
        window = self._window(MAX_UI_SCALE)
        for key in (PAGE_DAILY, PAGE_CLOSING, PAGE_SPECIAL, PAGE_BULK, PAGE_ADMIN):
            window.sidebar.select(key)
            QApplication.processEvents()
            page = window.stack.currentWidget()
            with self.subTest(page=key):
                self.assertTrue(
                    page.findChildren(QScrollArea)
                    or page.minimumSizeHint().height() <= page.height(),
                    f"{key} nemá posuvník a nevejde se",
                )


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class HighDpiTests(unittest.TestCase):
    """Zvětšení řídí Windows a volba v aplikaci, nikdy obojí navíc."""

    def test_rounding_policy_passes_windows_scale_through(self):
        _application()
        self.assertEqual(
            QApplication.highDpiScaleFactorRoundingPolicy(),
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough,
        )

    def test_application_does_not_force_extra_scale_factor(self):
        source = (ROOT / "gui_qt" / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("QT_SCALE_FACTOR", source)
        self.assertNotIn("AA_EnableHighDpiScaling", source)

    def test_saved_geometry_never_exceeds_screen(self):
        _application()
        directory = Path(tempfile.mkdtemp(prefix="autoreport_qt_dpi_"))
        self.addCleanup(shutil.rmtree, directory, True)
        config = directory / "config.json"
        shutil.copy2(ROOT / "config.example.json", config)
        raw = json.loads(config.read_text(encoding="utf-8"))
        available = QApplication.primaryScreen().availableGeometry()
        settings = peek_ui_settings(raw).with_geometry(
            width=available.width() + 2000,
            height=available.height() + 2000,
            x=available.right() + 500,
            y=available.bottom() + 500,
            maximized=False,
        )
        with mock.patch("gui_qt.main_window.stored_password", return_value=""):
            window = MainWindow(config, settings)
        self.addCleanup(window.deleteLater)
        # Menší než plocha okna nejde, pod minimum obsahu se okno nezmenší.
        limit = window.minimumSizeHint()
        self.assertLessEqual(
            window.width(), max(available.width(), limit.width())
        )
        self.assertLessEqual(
            window.height(), max(available.height(), limit.height())
        )
        self.assertGreaterEqual(window.x(), available.left())
        self.assertGreaterEqual(window.y(), available.top())


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class ClosingPageTests(unittest.TestCase):
    def setUp(self):
        _application()
        self.page = ClosingPage(metrics_for(1.0), palette=palette_for("light"))

    def test_form_round_trip(self):
        form = ClosingForm(
            year=2026,
            month=7,
            use_current_period=False,
            reports=("fksp", "stravovaci_arch"),
            output="vystup/uzaverka/{rok}-{mesic}",
            pack_zip=False,
            send_mail=True,
            arch_variant="StravovaciArch",
            include_bulk_arch=False,
            recap_variant="R",
            use_all_categories=False,
            recipients=("ucetni@example.com",),
        )
        self.page.set_form(form)
        self.assertEqual(self.page.form(), form)

    def test_current_period_disables_manual_fields(self):
        self.page.set_form(ClosingForm(year=2026, month=3, use_current_period=True))
        self.assertFalse(self.page._month.isEnabled())
        self.assertFalse(self.page._year.isEnabled())

    def test_missing_recipients_are_reported_when_sending(self):
        self.page.set_form(
            ClosingForm(year=2026, month=3, send_mail=True, recipients=())
        )
        self.assertEqual(self.page._recipients_label.property("role"), "error")
        self.page.set_recipients(("ucetni@example.com",))
        self.assertEqual(self.page._recipients_label.property("role"), "hint")

    def test_progress_and_result_switch_the_bar(self):
        self.page.set_progress(40, "Tvořím arch…")
        self.assertTrue(self.page._progress.isVisibleTo(self.page))
        self.assertEqual(self.page._progress.value(), 40)
        self.page.set_result("Hotovo")
        self.assertFalse(self.page._progress.isVisibleTo(self.page))
        self.assertEqual(self.page._state_dot.property("role"), "statusOk")

    def test_run_button_reports_reason_when_disabled(self):
        self.page.set_run_enabled(False, "Nejprve ověřte připojení.")
        self.assertFalse(self.page._run.isEnabled())
        self.assertIn("připojení", self.page._run.toolTip())


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class SpecialPageTests(unittest.TestCase):
    def setUp(self):
        _application()
        self.page = SpecialPage(metrics_for(1.0), palette=palette_for("light"))

    def test_form_round_trip_with_selected_categories(self):
        self.page.set_category_options((("1", "Žáci"), ("2", "Žáci 2")))
        form = SpecialForm(
            year=2026,
            output="vystup/z17/{rok}",
            use_all_categories=False,
            categories=("1",),
        )
        self.page.set_form(form)
        self.assertEqual(self.page.form(), form)

    def test_selection_is_kept_when_switching_to_all_categories(self):
        self.page.set_category_options((("1", "Žáci"), ("2", "Žáci 2")))
        self.page.set_form(
            SpecialForm(year=2026, use_all_categories=False, categories=("1",))
        )
        self.page._mode_all.setChecked(True)
        form = self.page.form()
        self.assertTrue(form.use_all_categories)
        self.assertEqual(form.categories, ("1",))

    def test_school_year_hint_follows_year(self):
        self.page.set_form(SpecialForm(year=2026))
        self.assertIn("2025/2026", self.page._school_year.text())
        self.assertIn("31. 10. 2026", self.page._school_year.text())


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class BulkPageTests(unittest.TestCase):
    def setUp(self):
        _application()
        self.page = BulkPage(metrics_for(1.0), palette=palette_for("light"))

    def test_message_round_trip(self):
        form = BulkForm(subject="Přerušení provozu", body="Dobrý den,\nzítra…")
        self.page.set_form(form)
        self.assertEqual(self.page.form(), form)

    def test_recipient_table_shows_summary(self):
        self.page.set_recipients(
            (
                ("Novák Jan", "3.A", "1", "jan@example.com"),
                ("Malá Eva", "3.A", "1", "eva@example.com"),
            ),
            "2 příjemci",
            can_send=True,
        )
        self.assertIn("2", self.page._summary.text())
        self.assertTrue(self.page._send.isEnabled())

    def test_empty_recipients_show_empty_state(self):
        self.page.set_recipients((), "0 příjemců", can_send=False)
        self.assertFalse(self.page._send.isEnabled())

    def test_send_is_blocked_without_recipients(self):
        self.page.set_send_enabled(False, "Vyberte příjemce s platným e-mailem.")
        self.assertFalse(self.page._send.isEnabled())
        self.assertIn("příjemce", self.page._send.toolTip())


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class HeaderTests(unittest.TestCase):
    def setUp(self):
        _application()
        self.header = HeaderBar(metrics_for(1.0))

    def test_states_use_color_roles(self):
        self.header.set_state(STATE_OK, "Připojeno", "detail")
        self.assertEqual(self.header._state_label.property("role"), "statusOk")
        self.assertEqual(self.header._dot.property("role"), "statusOk")
        self.assertEqual(self.header._state_label.toolTip(), "detail")
        self.header.set_state(STATE_ERROR, "Odpojeno", "chyba")
        self.assertEqual(self.header._state_label.property("role"), "statusError")
        self.assertEqual(self.header._dot.property("role"), "statusError")

    def test_meta_is_hidden_without_connection(self):
        self.header.set_connection_meta("", "")
        self.assertFalse(self.header._subject.isVisible())
        self.header.set_connection_meta(
            "ZŠ Kozinova", "vyvoj · 07/2026", "127.0.0.1:5433"
        )
        self.assertEqual(self.header._subject.full_text(), "ZŠ Kozinova")
        self.assertEqual(self.header._meta.toolTip(), "127.0.0.1:5433")

    def test_header_uses_overview_and_admin_buttons(self):
        self.assertEqual(self.header._home_button.text(), "Přehled")
        self.assertIn("Administrace", self.header._admin_button.text())

    def test_height_follows_scale(self):
        large = HeaderBar(metrics_for(1.6))
        self.assertGreater(large.height(), self.header.height())


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class SidebarTests(unittest.TestCase):
    def test_separator_is_not_selectable(self):
        _application()
        sidebar = NavigationSidebar(
            (
                NavItem("a", "Denní stav"),
                NavItem(SEPARATOR, ""),
                NavItem("b", "Administrace"),
            ),
            metrics_for(1.0),
        )
        keys = []
        sidebar.page_selected.connect(keys.append)
        sidebar.select("b")
        self.assertEqual(sidebar.current_key(), "b")
        self.assertEqual(keys, ["b"])
        self.assertEqual(sidebar.item(1).flags(), Qt.NoItemFlags)

    def test_width_follows_scale(self):
        _application()
        items = (NavItem("a", "Denní stav"),)
        small = NavigationSidebar(items, metrics_for(1.0))
        large = NavigationSidebar(items, metrics_for(1.6))
        self.assertGreater(large.width(), small.width())


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class MainWindowTests(unittest.TestCase):
    def setUp(self):
        _application()
        self.directory = Path(tempfile.mkdtemp(prefix="autoreport_qt_test_"))
        self.config = self.directory / "config.json"
        shutil.copy2(ROOT / "config.example.json", self.config)
        raw = json.loads(self.config.read_text(encoding="utf-8"))
        raw["povolene_kategorie"] = ["1", "2"]
        raw["mail_prijemci"] = ["prijemce@example.com"]
        self.config.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.stored = mock.patch(
            "gui_qt.main_window.stored_password", return_value=""
        )
        self.stored.start()
        self.addCleanup(self.stored.stop)
        self.window = MainWindow(self.config, peek_ui_settings(raw))
        self.window._admin_unlocked = True
        self.window._refresh_admin_lock_state()
        self.addCleanup(self.window.deleteLater)

    def _connection(self):
        return ConnectionInfo(
            categories=(("1", "Žáci"), ("2", "Žáci 2"), ("HOST", "Hosté")),
            database_name="vyvoj",
            subject_name="ZŠ Kozinova",
            period=(2026, 7),
            database={"host": "127.0.0.1", "port": 5433},
        )

    def test_starts_on_overview_without_connection(self):
        self.assertEqual(self.window._current_page_key(), PAGE_USER)
        self.assertEqual(self.window.sidebar.current_key(), "")
        self.assertFalse(self.window.daily_page._create.isEnabled())
        self.assertFalse(self.window.daily_page._send.isEnabled())

    def test_all_pages_are_reachable(self):
        for key in (PAGE_CLOSING, PAGE_SPECIAL, PAGE_BULK, PAGE_DAILY):
            with self.subTest(page=key):
                self.window.sidebar.select(key)
                self.assertIs(
                    self.window.stack.currentWidget(), self.window._pages[key]
                )

    def test_admin_uses_single_local_navigation(self):
        self.window._activate_page(PAGE_ADMIN)
        admin = self.window.admin_page
        self.assertIsInstance(admin.nav, SegmentedNav)
        self.assertEqual(admin.current_section(), SECTION_DATABASE)
        admin.show_section(SECTION_APPEARANCE)
        self.assertEqual(admin.current_section(), SECTION_APPEARANCE)
        self.assertEqual(
            len(admin.findChildren(NavigationSidebar)), 0
        )

    def test_successful_connection_updates_header_and_actions(self):
        self.window._connection_ok(self._connection(), silent=True)
        header = self.window.header
        self.assertEqual(header._state_label.text(), "Připojeno")
        self.assertEqual(header._subject.full_text(), "ZŠ Kozinova")
        self.assertIn("07/2026", header._meta.text())
        self.assertTrue(self.window.daily_page._create.isEnabled())
        self.assertTrue(self.window.daily_page._send.isEnabled())

    def test_connection_enables_closing_and_special(self):
        self.window._connection_ok(self._connection(), silent=True)
        self.assertTrue(self.window.closing_page._run.isEnabled())
        self.assertTrue(self.window.special_page._run.isEnabled())

    def test_connection_drops_categories_missing_in_database(self):
        self.window.daily_page.set_selected_categories(["1", "STARA", "JINA"])
        self.window._connection_ok(self._connection(), silent=True)
        self.assertEqual(self.window.daily_page.selected_categories(), ("1",))
        self.assertIn(
            "výběr kategorií upraven", self.window.statusBar().currentMessage()
        )
        self.assertIn("vypadly", self.window.statusBar().toolTip())

    def test_connection_selects_all_when_stored_codes_are_obsolete(self):
        self.window.daily_page.set_selected_categories(["1DOB", "1HOL"])
        self.window._connection_ok(self._connection(), silent=True)
        self.assertEqual(
            self.window.daily_page.selected_categories(), ("1", "2", "HOST")
        )
        self.assertTrue(self.window.daily_page._create.isEnabled())
        self.assertTrue(self.window.daily_page._refresh_overview.isEnabled())
        detail = self.window.statusBar().toolTip()
        self.assertIn("vypadly", detail)
        self.assertIn("vybrány všechny 3", detail)
        saved = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(saved["povolene_kategorie"], ["1", "2", "HOST"])

    def test_failed_connection_shows_error_state(self):
        self.window._connection_failed("timeout", silent=True)
        self.assertEqual(
            self.window.header._state_label.text(),
            "DB nepřipojeno - nastav zde",
        )
        self.assertFalse(self.window.daily_page._create.isEnabled())

    def test_theme_change_is_saved_to_config(self):
        self.window._ui = self.window._ui.with_theme("dark")
        self.window._persist_ui_only()
        saved = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(saved["ui"]["theme"], "dark")
        self.assertEqual(self.window._ui.theme, "dark")

    def test_scale_change_rebuilds_ui_and_keeps_page(self):
        self.window._connection_ok(self._connection(), silent=True)
        self.window._activate_page(PAGE_ADMIN)
        self.window._change_scale(1.25)
        saved = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(saved["ui"]["ui_scale"], 1.25)
        self.assertEqual(self.window._current_page_key(), PAGE_ADMIN)
        self.assertEqual(self.window.header._state_label.text(), "Připojeno")
        self.assertEqual(self.window._metrics.scale, 1.25)

    def test_zoom_steps_stop_at_limits(self):
        for _ in range(10):
            self.window._zoom(1)
        self.assertEqual(self.window._ui.ui_scale, MAX_UI_SCALE)
        for _ in range(10):
            self.window._zoom(-1)
        self.assertEqual(self.window._ui.ui_scale, UI_SCALES[0])

    def test_daily_settings_are_persisted(self):
        self.window._connection_ok(self._connection(), silent=True)
        self.window.daily_page._date.setDate(QDate(2026, 8, 23))
        self.window.daily_page.set_selected_categories(["1", "2"])
        self.assertTrue(self.window._persist(silent=True))
        saved = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(saved["datum"], "23.08.2026")
        self.assertEqual(saved["povolene_kategorie"], ["1", "2"])
        self.assertEqual(saved["poctyemailem"]["povolene_kategorie"], ["1", "2"])

    def test_closing_settings_are_persisted(self):
        page = self.window.closing_page
        page.set_form(
            ClosingForm(
                year=2026,
                month=5,
                reports=("fksp",),
                output="vystup/uzaverka/{rok}-{mesic}",
                pack_zip=False,
            )
        )
        self.window._save_closing_settings()
        saved = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(saved["uzaverka"]["sestavy"], ["fksp"])
        self.assertEqual(saved["uzaverka"]["prilohy"], "samostatne")

    def test_special_settings_are_persisted(self):
        self.window.special_page.set_form(
            SpecialForm(year=2027, output="vystup/z17/{rok}")
        )
        self.window._save_special_settings()
        saved = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(saved["z17"]["rok"], 2027)

    def test_bulk_message_is_persisted(self):
        self.window.bulk_page.set_form(
            BulkForm(subject="Předmět", body="Text zprávy")
        )
        self.window._save_bulk_settings()
        saved = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(saved["hromadna_zprava"]["predmet"], "Předmět")

    def test_persist_reports_invalid_selection(self):
        self.window.daily_page.set_selected_categories([])
        self.assertFalse(self.window._persist(silent=True))
        self.assertIn("kategorii", self.window.statusBar().currentMessage())

    def test_window_geometry_is_stored_on_close(self):
        self.window.resize(1280, 800)
        self.window.close()
        saved = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(saved["ui"]["window_width"], 1280)
        self.assertEqual(saved["ui"]["window_height"], 800)
        self.assertFalse(saved["ui"]["maximized"])

    def test_pdf_result_updates_overview_and_last_file(self):
        from services.daily import DailyResult

        pdf = self.directory / "sestava.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        overview = DailyOverview(
            rows=(OverviewRow("Obed", 1, "Kaše", 12),), diners=12, categories=2
        )
        with mock.patch.object(self.window, "_open_document") as opener:
            self.window._pdf_created(DailyResult(pdf_path=pdf, overview=overview))
        opener.assert_called_once_with(pdf)
        self.assertEqual(self.window.daily_page._overview_model.rowCount(), 1)
        self.assertIn("sestava.pdf", self.window.statusBar().currentMessage())

    def test_legacy_config_without_ui_block_opens(self):
        legacy = self.directory / "legacy.json"
        raw = json.loads(self.config.read_text(encoding="utf-8"))
        raw.pop("ui", None)
        raw["ui_barevne_schema"] = "tmave"
        raw["ui_hustota_poli"] = "volna"
        legacy.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        settings = peek_ui_settings(raw)
        window = MainWindow(legacy, settings)
        self.addCleanup(window.deleteLater)
        self.assertEqual(window._ui.theme, "dark")
        self.assertGreater(window._ui.ui_scale, 1.0)


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class UiSettingsIntegrationTests(unittest.TestCase):
    def test_settings_survive_round_trip(self):
        settings = UiSettings(theme=THEME_SYSTEM, ui_scale=1.4)
        self.assertEqual(settings.with_scale(1.4).ui_scale, 1.4)
        self.assertEqual(settings.with_theme("dark").theme, "dark")


if __name__ == "__main__":
    unittest.main()
