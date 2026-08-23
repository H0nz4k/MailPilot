import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from stravovaci_arch import (
    ArchMealRow,
    ArchPerson,
    ArchReport,
    create_arch_pdf,
    day_mark,
)
from uzaverka_pdf import SubjectHeader, format_money


class ArchReportTests(unittest.TestCase):
    def test_daily_rate_is_monthly_divided_by_portions(self):
        meal = ArchMealRow(
            meal_type="Oběd",
            days=tuple("1" if day <= 16 else "*" for day in range(1, 32)),
            portions=16,
            monthly_amount=624,
        )
        self.assertEqual(meal.daily_rate, 39)

    def test_day_mark_keeps_jidelna_codes(self):
        self.assertEqual(day_mark("S"), "S")
        self.assertEqual(day_mark(" * "), "*")
        self.assertEqual(day_mark(None), "")

    def test_payment_query_uses_typplatb_popis(self):
        from stravovaci_arch import PAYMENT_QUERY

        self.assertIn("typplatby", PAYMENT_QUERY)
        self.assertIn("popis", PAYMENT_QUERY)

    def test_creates_pdf_from_prepared_rows(self):
        report = ArchReport(
            header=SubjectHeader(
                subject_name="ZS Kozinova",
                address="Kozinova 1000",
                zip_code="102 00",
                city="Praha 15",
                company_id="47611332",
                vat_id="47611332",
            ),
            individuals=(
                ArchPerson(
                    name="Bohm Tomáš",
                    evidence_no=20102,
                    var_symbol="20102",
                    class_name="PRIM.A",
                    category_code="10",
                    category_name="Gymn. 2. stupeň",
                    payment_method="Z běžného účtu",
                    payment=2439,
                    credit_prev=1815,
                    credit_now=1074,
                    meals=(
                        ArchMealRow(
                            meal_type="Oběd",
                            days=tuple("1" for _ in range(31)),
                            portions=16,
                            monthly_amount=624,
                        ),
                    ),
                ),
            ),
            bulk=(),
            period=date(2026, 5, 1),
        )
        config = SimpleNamespace(
            pdf_data_font_size=8.5,
            pdf_label_font_size=9.0,
            pdf_bold=False,
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "StravovaciArch_2026-05.pdf"
            created = create_arch_pdf(config, report, output)
            self.assertTrue(created.is_file())
            self.assertGreater(created.stat().st_size, 1000)
        self.assertEqual(format_money(624), "624,00\u00a0Kč")


if __name__ == "__main__":
    unittest.main()
