"""Manual report selection must not overwrite another selection for same day."""
from pathlib import Path
import unittest

from services.web_report_output import manual_pdf_path


class ManualReportFilenameTest(unittest.TestCase):
    def setUp(self):
        self.base = Path("vystup/DataShip_2026-10-21.pdf")
        self.allowed = ("Z1", "Z2", "Z3", "Z4", "Z5", "Z6")

    def test_all_allowed_uses_legacy_path(self):
        self.assertEqual(manual_pdf_path(self.base, self.allowed, self.allowed), self.base)

    def test_sequential_two_then_four_has_distinct_pdfs(self):
        first = manual_pdf_path(self.base, ("Z1", "Z2"), self.allowed)
        second = manual_pdf_path(self.base, ("Z3", "Z4", "Z5", "Z6"), self.allowed)
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, self.base)
        self.assertNotEqual(second, self.base)
        self.assertIn("kat-2", first.name)
        self.assertIn("kat-4", second.name)
        self.assertEqual(first.parent, self.base.parent)
        self.assertTrue(first.name.endswith(".pdf"))

    def test_many_categories_keep_filename_short(self):
        allowed = tuple(f"kategorie-{i:03}" for i in range(60))
        path = manual_pdf_path(self.base, allowed[:53], allowed, ("Oběd A", "Oběd B"))
        self.assertLessEqual(len(path.name), 46)
        self.assertIn("kat-53", path.name)

    def test_order_does_not_change_same_selection_path(self):
        self.assertEqual(
            manual_pdf_path(self.base, ("Z2", "Z1"), self.allowed),
            manual_pdf_path(self.base, ("Z1", "Z2"), self.allowed),
        )

    def test_meal_filter_creates_distinct_output(self):
        self.assertNotEqual(
            manual_pdf_path(self.base, self.allowed, self.allowed, "Oběd"),
            manual_pdf_path(self.base, self.allowed, self.allowed, "Snídaně"),
        )

    def test_renamed_or_unicode_category_codes_remain_distinct(self):
        self.assertNotEqual(
            manual_pdf_path(self.base, ("Č",), ("Č", "C")),
            manual_pdf_path(self.base, ("C",), ("Č", "C")),
        )

    def test_rejects_disallowed_or_empty_categories(self):
        for selected in ((), ("Z1", "DISALLOWED")):
            with self.subTest(selected=selected):
                with self.assertRaises(ValueError):
                    manual_pdf_path(self.base, selected, self.allowed)


if __name__ == "__main__":
    unittest.main()
