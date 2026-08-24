import json
import tempfile
import unittest
from pathlib import Path

from credential_store import (
    ADMIN_ACCOUNT,
    SERVICE_NAME,
    credential_account,
    sanitize_config,
    write_config,
)


class CredentialStoreTests(unittest.TestCase):
    def setUp(self):
        self.database = {
            "host": "DB-SERVER",
            "port": 5432,
            "dbname": "Jidelna",
            "user": "Altisima-Client",
        }

    def test_account_is_stable_and_contains_no_password(self):
        account = credential_account(self.database)
        self.assertEqual(account, "altisima-client@db-server:5432/jidelna")
        self.assertNotIn("secret", account)

    def test_sanitize_removes_password_without_mutating_input(self):
        raw = {
            "databaze": dict(self.database, password="secret"),
            "resend_api_key": "re_secret",
            "mail": {"mail_api_key": "nested_secret"},
        }
        sanitized = sanitize_config(raw)
        self.assertNotIn("password", sanitized["databaze"])
        self.assertNotIn("resend_api_key", sanitized)
        self.assertNotIn("mail_api_key", sanitized["mail"])
        self.assertEqual(raw["databaze"]["password"], "secret")
        self.assertEqual(raw["resend_api_key"], "re_secret")

    def test_admin_password_uses_separate_keyring_account(self):
        self.assertEqual(SERVICE_NAME, "Altisima.MailPilot")
        self.assertEqual(ADMIN_ACCOUNT, "Admin.Heslo")

    def test_write_config_never_writes_password(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            write_config(
                path,
                {
                    "databaze": dict(self.database, password="secret"),
                    "povolene_kategorie": ["Z1"],
                    "RESEND_API_KEY": "re_secret",
                },
            )
            written = path.read_text(encoding="utf-8")
            self.assertNotIn("secret", written)
            self.assertNotIn("password", json.loads(written)["databaze"])
            self.assertNotIn("RESEND_API_KEY", json.loads(written))


if __name__ == "__main__":
    unittest.main()
