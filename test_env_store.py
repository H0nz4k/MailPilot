import tempfile
import unittest
from pathlib import Path

import env_store


class EnvStoreTests(unittest.TestCase):
    def test_reads_resend_key_from_dotenv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("RESEND_API_KEY=re_test_123\n", encoding="utf-8")
            self.assertEqual(env_store.get_resend_api_key(path), "re_test_123")

    def test_missing_dotenv_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            self.assertIsNone(env_store.get_resend_api_key(path))

    def test_writes_key_without_touching_other_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("OTHER=value\n", encoding="utf-8")
            env_store.set_resend_api_key("re_new", path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("OTHER=value", text)
            self.assertIn("RESEND_API_KEY=re_new", text)


if __name__ == "__main__":
    unittest.main()
