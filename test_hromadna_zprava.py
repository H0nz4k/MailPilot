import unittest

from hromadna_zprava import (
    FILTER_CATEGORY,
    FILTER_CLASS,
    apply_bulk_ui,
    build_preview,
    diner_email,
    option_label,
    peek_bulk_ui,
    send_bulk_message,
)
from stravovaci_sestava import ConfigError


class BulkMessageTests(unittest.TestCase):
    def test_option_label_adds_note(self):
        self.assertEqual(option_label("1.A", ""), "1.A")
        self.assertEqual(option_label("1.A", "1.A"), "1.A")
        self.assertEqual(option_label("ZAM", "Zaměstnanci"), "ZAM — Zaměstnanci")

    def test_diner_email_rejects_empty_and_invalid(self):
        self.assertEqual(diner_email(" rodic@example.cz "), "rodic@example.cz")
        self.assertIsNone(diner_email(""))
        self.assertIsNone(diner_email(None))
        self.assertIsNone(diner_email("není-mail"))

    def test_preview_counts_unique_recipients_and_missing_names(self):
        rows = [
            (1, "Novák Jan", "jan@example.cz", "1.A", "1"),
            (2, "Nováková Eva", "jan@example.cz", "1.A", "1"),
            (3, "Dvořák Petr", None, "1.A", "1"),
            (4, "Holá Marie", "neplatny", "1.A", "1"),
        ]
        preview = build_preview(
            rows, filter_type=FILTER_CLASS, filter_value="1.A"
        )
        self.assertEqual(preview.diner_count, 4)
        self.assertEqual(preview.recipient_count, 1)
        self.assertEqual(preview.recipients, ("jan@example.cz",))
        self.assertEqual(preview.missing_count, 2)
        self.assertEqual(
            [item.name for item in preview.missing],
            ["Dvořák Petr", "Holá Marie"],
        )

    def test_category_filter_preview_keeps_value(self):
        preview = build_preview(
            [(10, "Zaměstnanec", "a@b.cz", None, "ZAM")],
            filter_type=FILTER_CATEGORY,
            filter_value="ZAM",
        )
        self.assertEqual(preview.filter_type, FILTER_CATEGORY)
        self.assertEqual(preview.filter_value, "ZAM")
        self.assertEqual(preview.missing_count, 0)

    def test_send_requires_recipients_subject_and_body(self):
        empty = build_preview([], filter_type=FILTER_CLASS, filter_value="1.A")
        with self.assertRaisesRegex(ConfigError, "e-mail"):
            send_bulk_message(
                empty,
                subject="Info",
                body="Text",
                api_key="re_test",
                sender_email="podpora@altisima.cz",
                sender=lambda **_values: "ok",
            )
        preview = build_preview(
            [(1, "Novák", "a@b.cz", "1.A", "1")],
            filter_type=FILTER_CLASS,
            filter_value="1.A",
        )
        with self.assertRaisesRegex(ConfigError, "předmět"):
            send_bulk_message(
                preview,
                subject="  ",
                body="Text",
                api_key="re_test",
                sender_email="podpora@altisima.cz",
                sender=lambda **_values: "ok",
            )
        with self.assertRaisesRegex(ConfigError, "text"):
            send_bulk_message(
                preview,
                subject="Info",
                body="  ",
                api_key="re_test",
                sender_email="podpora@altisima.cz",
                sender=lambda **_values: "ok",
            )

    def test_send_dispatches_unique_recipients(self):
        preview = build_preview(
            [
                (1, "A", "a@example.cz", "1.A", "1"),
                (2, "B", "A@example.cz", "1.A", "1"),
            ],
            filter_type=FILTER_CLASS,
            filter_value="1.A",
        )
        captured = {}

        def sender(**values):
            captured.update(values)
            return "job-1"

        result = send_bulk_message(
            preview,
            subject="Uzavření jídelny",
            body="Zítra zavřeno.",
            api_key="re_test",
            sender_email="podpora@altisima.cz",
            sender=sender,
        )
        self.assertEqual(captured["recipients"], ["a@example.cz"])
        self.assertEqual(captured["subject"], "Uzavření jídelny")
        self.assertNotIn("files", captured)
        self.assertNotIn("pdf_path", captured)
        self.assertEqual(result.detail, "job-1")

    def test_missing_email_counts_and_names(self):
        from hromadna_zprava import (
            diner_from_row,
            missing_email_counts,
            missing_email_diners,
            preview_from_diners,
        )

        all_diners = [
            diner_from_row(row)
            for row in [
                (1, "Novák Jan", "jan@example.cz", "1.A", "1"),
                (2, "Dvořák Petr", None, "1.A", "1"),
                (3, "Holá Marie", "", "2.A", "1"),
                (4, "Učitel", "u@example.cz", None, "6"),
            ]
        ]
        self.assertEqual(missing_email_counts(all_diners, FILTER_CLASS)["1.A"], 1)
        self.assertEqual(missing_email_counts(all_diners, FILTER_CLASS)["2.A"], 1)
        self.assertEqual(
            [item.name for item in missing_email_diners(
                all_diners, filter_type=FILTER_CLASS, filter_value="1.A"
            )],
            ["Dvořák Petr"],
        )
        combined = preview_from_diners(
            all_diners, filter_type=FILTER_CLASS, filter_values=["1.A", "2.A"]
        )
        self.assertEqual(combined.recipient_count, 1)
        self.assertEqual(combined.missing_count, 2)
        self.assertEqual(combined.filter_values, ("1.A", "2.A"))

    def test_preview_summary_explains_missing_emails(self):
        from hromadna_zprava import bulk_preview_summary

        none = build_preview([], filter_type=FILTER_CLASS, filter_value="1.A")
        self.assertIn("nejsou žádní strávníci", bulk_preview_summary(none))
        all_missing = build_preview(
            [(1, "Petr", None, "2.B", "1")],
            filter_type=FILTER_CLASS,
            filter_value=["2.B", "2.C"],
        )
        text = bulk_preview_summary(all_missing)
        self.assertIn("2 třídy", text)
        self.assertIn("0 příjemců", text)
        self.assertIn("nedorazila nikomu", text)
        mixed = build_preview(
            [
                (1, "A", "a@example.cz", "0.C", "1"),
                (2, "B", None, "2.B", "1"),
            ],
            filter_type=FILTER_CLASS,
            filter_value=["0.C", "2.B"],
        )
        mixed_text = bulk_preview_summary(mixed)
        self.assertIn("1 příjemců", mixed_text)
        self.assertIn("nedorazí", mixed_text)
        self.assertNotIn("Třída:", mixed_text)

    def test_peek_and_apply_keep_last_message(self):
        updated = apply_bulk_ui(
            {}, subject="  Info  ", body="Dobrý den"
        )
        self.assertEqual(updated["hromadna_zprava"]["predmet"], "Info")
        peeked = peek_bulk_ui(updated)
        self.assertEqual(peeked["predmet"], "Info")
        self.assertEqual(peeked["text"], "Dobrý den")


if __name__ == "__main__":
    unittest.main()
