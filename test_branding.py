import unittest
from pathlib import Path

from gui_qt import APP_TITLE, APP_VERSION


ROOT = Path(__file__).resolve().parent


class BrandingTests(unittest.TestCase):
    def test_app_identity_matches_mailpilot_v128(self):
        self.assertEqual(APP_TITLE, "MailPilot")
        self.assertEqual(APP_VERSION, "v12.8")

    def test_qt_cli_help_uses_mailpilot_name(self):
        text = (ROOT / "gui_qt" / "app.py").read_text(encoding="utf-8")
        self.assertIn('prog="MailPilot"', text)
        self.assertIn("MailPilotu", text)

    def test_build_artifact_name_is_v128(self):
        script = (ROOT / "build_windows.bat").read_text(encoding="utf-8")
        self.assertIn("MailPilot-v12.8-portable.zip", script)

    def test_readme_mentions_current_version(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("# MailPilot v12.8", readme)


if __name__ == "__main__":
    unittest.main()
