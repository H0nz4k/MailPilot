import base64
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mailsender_bridge import MailSenderBridgeError, _check_message_size, send_files, send_pdf, send_text


class FakeEmails:
    calls = []

    @classmethod
    def send(cls, message):
        cls.calls.append(message)
        return {"id": f"email-{len(cls.calls)}"}


class FakeResend:
    api_key = None
    Emails = FakeEmails


class MailSenderBridgeTests(unittest.TestCase):
    def setUp(self):
        FakeEmails.calls = []
        FakeResend.api_key = None

    def test_sends_private_messages_individually_with_pdf_attachment(self):
        recipients = [f"technik{index}@example.cz" for index in range(101)]
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "sestava.pdf"
            pdf_bytes = b"%PDF-1.4\nTEST\n%%EOF"
            pdf_path.write_bytes(pdf_bytes)
            detail = send_pdf(
                recipients=recipients,
                subject="Seznam strávníků: 05.08.2026",
                body="Dobrý den",
                pdf_path=pdf_path,
                api_key="re_test_key",
                sender_email="podpora@altisima.cz",
                resend_module=FakeResend,
            )

        self.assertEqual(FakeResend.api_key, "re_test_key")
        self.assertEqual(len(FakeEmails.calls), 101)
        first = FakeEmails.calls[0]
        self.assertEqual(first["to"], ["technik0@example.cz"])
        self.assertEqual(first["from"], "podpora@altisima.cz")
        self.assertEqual(
            base64.b64decode(first["attachments"][0]["content"]), pdf_bytes
        )
        self.assertEqual(FakeEmails.calls[-1]["to"], ["technik100@example.cz"])
        self.assertIn("101 samostatných zpráv s PDF", detail)
        self.assertIn("potvrzeno 101 ID", detail)

    def test_sends_multiple_attachments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "fksp.pdf"
            zip_path = Path(temp_dir) / "uzaverka.zip"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
            zip_path.write_bytes(b"PK\x03\x04")
            send_files(
                recipients=["ucetni@example.cz"],
                subject="Uzávěrka stravného: červenec 2026",
                body="Dobrý den",
                files=[pdf_path, zip_path],
                api_key="re_test_key",
                sender_email="podpora@altisima.cz",
                resend_module=FakeResend,
            )
        self.assertEqual(len(FakeEmails.calls[0]["attachments"]), 2)
        self.assertEqual(FakeEmails.calls[0]["attachments"][0]["filename"], "fksp.pdf")

    def test_uses_default_body_when_user_text_is_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "sestava.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
            send_pdf(
                recipients=["technik@example.cz"],
                subject="Předmět",
                body="   ",
                pdf_path=pdf_path,
                api_key="re_test_key",
                sender_email="podpora@altisima.cz",
                resend_module=FakeResend,
            )
        self.assertIn("příloze", FakeEmails.calls[0]["text"])

    def test_sends_text_without_attachments(self):
        detail = send_text(
            recipients=["rodic@example.cz", "dalsi@example.cz"],
            subject="Zavřeno",
            body="Jídelna zítra nevaří.",
            api_key="re_test_key",
            sender_email="podpora@altisima.cz",
            resend_module=FakeResend,
        )
        self.assertEqual(len(FakeEmails.calls), 2)
        self.assertNotIn("attachments", FakeEmails.calls[0])
        self.assertEqual(FakeEmails.calls[0]["subject"], "Zavřeno")
        self.assertEqual(FakeEmails.calls[0]["text"], "Jídelna zítra nevaří.")
        self.assertIn("2 samostatných zpráv bez přílohy", detail)

    def test_text_send_rejects_empty_body(self):
        with self.assertRaisesRegex(MailSenderBridgeError, "Text"):
            send_text(
                recipients=["rodic@example.cz"],
                subject="Zavřeno",
                body="  ",
                api_key="re_test_key",
                sender_email="podpora@altisima.cz",
                resend_module=FakeResend,
            )

    def test_rejects_message_over_resend_40_mb_limit(self):
        with mock.patch("mailsender_bridge.MAX_EMAIL_BYTES", 100):
            with self.assertRaisesRegex(MailSenderBridgeError, "40 MB"):
                _check_message_size(
                    "A" * 40,
                    sender="a@example.cz",
                    recipient="b@example.cz",
                    subject="PDF",
                    body="Text",
                )


if __name__ == "__main__":
    unittest.main()
