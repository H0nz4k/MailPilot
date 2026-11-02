"""BUILD regression: accessibility of expandable advanced options."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from gui_qt.theme import metrics_for
    from gui_qt.widgets.collapsible import CollapsibleSection
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication is not None, "PySide6 unavailable")
class CollapsibleAccessibilityTests(unittest.TestCase):
    def test_accessibility_state_tracks_expand_and_collapse(self):
        app = QApplication.instance() or QApplication([])
        section = CollapsibleSection("Pokročilé možnosti", metrics_for(1.0))
        self.assertEqual(section._toggle.accessibleName(), "Pokročilé možnosti")
        self.assertIn("Sbalená", section._toggle.accessibleDescription())
        self.assertIn("Rozbalit", section._toggle.toolTip())
        section.set_expanded(True)
        self.assertIn("Rozbalená", section._toggle.accessibleDescription())
        self.assertIn("Sbalit", section._toggle.toolTip())
        section.set_expanded(False)
        self.assertIn("Sbalená", section._toggle.accessibleDescription())
        section.deleteLater()
