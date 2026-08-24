import importlib.util
import unittest

PYSIDE_AVAILABLE = importlib.util.find_spec("PySide6") is not None

if PYSIDE_AVAILABLE:
    from PySide6.QtWidgets import QApplication

    from gui_qt.pages.advanced import AdvancedPage
    from gui_qt.theme import metrics_for


def _app():
    return QApplication.instance() or QApplication([])


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 není nainstalované")
class WarningButtonStateTests(unittest.TestCase):
    def setUp(self):
        _app()
        self.page = AdvancedPage(metrics_for(1.0))

    def test_warning_off_disables_clear_button(self):
        self.page.set_warning_active(False)
        self.assertFalse(self.page._clear_warning_btn.isEnabled())
        self.assertEqual(self.page._show_warning_btn.styleSheet(), "")
        self.assertEqual(self.page._show_custom_warning_btn.styleSheet(), "")

    def test_warning_on_marks_show_as_danger_and_clear_as_enabled(self):
        self.page.set_warning_active(True)
        self.assertTrue(self.page._clear_warning_btn.isEnabled())
        self.assertIn("D64545", self.page._show_warning_btn.styleSheet())
        self.assertIn("2E8B57", self.page._clear_warning_btn.styleSheet())


if __name__ == "__main__":
    unittest.main()
