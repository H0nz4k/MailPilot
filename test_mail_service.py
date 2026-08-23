import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from mail_service import (
    CookingStatus,
    MailSenderUnavailable,
    cooking_status_message,
    mail_subject,
    normalize_recipients,
    send_pdf_via_mailsender,
    send_text_via_mailsender,
    should_send_on_cooking_day,
)
from stravovaci_sestava import ConfigError


class MailServiceTests(unittest.TestCase):
    def test_normalizes_recipients_and_removes_case_insensitive_duplicates(self):
        self.assertEqual(
            normalize_recipients([" a@example.cz ", "A@example.cz", "b@test.eu"]),
            ("a@example.cz", "b@test.eu"),
        )

    def test_rejects_invalid_recipient(self):
        with self.assertRaises(ConfigError):
            normalize_recipients(["neni-mail"])

    def test_allows_empty_recipient_list_only_for_saved_draft(self):
        self.assertEqual(normalize_recipients([], allow_empty=True), ())
        with self.assertRaises(ConfigError):
            normalize_recipients([])

    def test_formats_fixed_subject(self):
        self.assertEqual(
            mail_subject(date(2026, 8, 5)),
            "Seznam strávníků: 05.08.2026",
        )

    def test_cooking_day_requires_relevant_cooking_meal_type(self):
        statuses = (
            CookingStatus("Oběd", False),
            CookingStatus("Svačina", True),
        )
        self.assertTrue(should_send_on_cooking_day(statuses))
        self.assertFalse(
            should_send_on_cooking_day((CookingStatus("Oběd", False),))
        )
        self.assertFalse(should_send_on_cooking_day(()))

    def test_cooking_status_message_describes_empty_selection(self):
        self.assertIn("žádnou objednávku", cooking_status_message(()))

    def test_dispatches_pdf_through_injected_mailsender(self):
        captured = {}

        def sender(**values):
            captured.update(values)
            return "job-123"

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "sestava.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
            result = send_pdf_via_mailsender(
                ["technik@example.cz"],
                "Seznam strávníků: 05.08.2026",
                "Dobrý den",
                pdf_path,
                api_key="re_test_key",
                sender_email="podpora@altisima.cz",
                sender=sender,
            )

        self.assertEqual(result.detail, "job-123")
        self.assertEqual(captured["recipients"], ["technik@example.cz"])
        self.assertEqual(captured["pdf_path"].name, "sestava.pdf")
        self.assertEqual(captured["api_key"], "re_test_key")
        self.assertEqual(captured["sender_email"], "podpora@altisima.cz")

    def test_dispatches_text_without_attachment(self):
        captured = {}

        def sender(**values):
            captured.update(values)
            return "job-text"

        result = send_text_via_mailsender(
            ["rodic@example.cz"],
            "Zavřeno",
            "Jídelna zítra nevaří.",
            api_key="re_test_key",
            sender_email="podpora@altisima.cz",
            sender=sender,
        )
        self.assertEqual(result.detail, "job-text")
        self.assertEqual(captured["recipients"], ["rodic@example.cz"])
        self.assertNotIn("files", captured)
        self.assertNotIn("pdf_path", captured)

    def test_missing_bridge_has_clear_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "sestava.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
            with patch("mail_service._mailsender_bridge", None):
                with self.assertRaises(MailSenderUnavailable):
                    send_pdf_via_mailsender(
                        ["technik@example.cz"],
                        "Předmět",
                        "",
                        pdf_path,
                        api_key="re_test_key",
                        sender_email="podpora@altisima.cz",
                    )


if __name__ == "__main__":
    unittest.main()
