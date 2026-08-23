import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from rekapitulace_sestava import (
    RecapCounts,
    RecapReport,
    RecapRow,
    create_recap_pdf,
)
from uzaverka_pdf import SubjectHeader, cell_markup, fit_column_widths, format_money


class RecapReportTests(unittest.TestCase):
    def test_daily_rates_match_jidelna_example(self):
        row = RecapRow(
            category_code="12",
            category_name="Gymn. učitelé",
            meal_type="Oběd",
            norm="C",
            portions=412,
            monthly_rate=28016,
            monthly_limit=16892,
            fksp=0,
            other_overhead=8240,
            payment=95214,
            credit_prev=87194,
            credit_now=0,
            registered=40,
            dining=39,
        )
        self.assertEqual(round(row.daily_rate), 68)
        self.assertEqual(round(row.daily_limit), 41)

    def test_previous_month_split_stays_per_person(self):
        from rekapitulace_sestava import _aggregate_rows

        rows = _aggregate_rows(
            [
                ("12", "Gymn. učitelé", "C", "Oběd", 10, 680, 410, 0, 200, 100, 80, 50, 1),
                ("12", "Gymn. učitelé", "C", "Oběd", 5, 340, 205, 0, 100, -40, -40, 0, 2),
            ],
            {"12": (2, 2)},
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.portions, 15)
        self.assertEqual(row.credit_prev_plus, 80)
        self.assertEqual(row.debit_prev, 40)
        self.assertEqual(row.payment, 100)
        self.assertEqual(row.debit_now, 40)
        self.assertEqual(row.credit_now_plus, 50)

    def test_counts_add_bulk_once(self):
        counts = RecapCounts(dining=1107, registered=1180, enrolled=1296, bulk=62)
        self.assertEqual(counts.dining_with_bulk, 1169)
        self.assertEqual(counts.registered_with_bulk, 1242)
        self.assertEqual(counts.enrolled_with_bulk, 1358)

    def test_creates_pdf_from_prepared_rows(self):
        report = RecapReport(
            header=SubjectHeader(
                subject_name="ZS Kozinova",
                address="Kozinova 1000",
                zip_code="102 00",
                city="Praha 15",
                company_id="47611332",
                vat_id="47611332",
            ),
            rows=(
                RecapRow(
                    category_code="6",
                    category_name="Učitelé",
                    meal_type="Oběd",
                    norm="C",
                    portions=632,
                    monthly_rate=25912,
                    monthly_limit=25912,
                    fksp=3160,
                    other_overhead=0,
                    payment=75436,
                    credit_prev=64242,
                    credit_now=82,
                    registered=48,
                    dining=46,
                ),
            ),
            counts=RecapCounts(dining=1107, registered=1180, enrolled=1296, bulk=62),
            variant="R",
            period=date(2026, 5, 1),
        )
        config = SimpleNamespace(
            pdf_data_font_size=8.5,
            pdf_label_font_size=9.0,
            pdf_bold=False,
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "Rekapitulace_2026-05.pdf"
            created = create_recap_pdf(config, report, output)
            self.assertTrue(created.is_file())
            self.assertGreater(created.stat().st_size, 1000)


class RecapColumnOrderTests(unittest.TestCase):
    def test_meal_headers_follow_jidelna_order(self):
        from rekapitulace_sestava import create_recap_pdf
        import inspect

        source = inspect.getsource(create_recap_pdf)
        meal_pos = source.find("meal_headers")
        finance_pos = source.find("finance_headers")
        meal = source[meal_pos:finance_pos]
        self.assertLess(meal.find("Evid."), meal.find("Nedo."))
        self.assertLess(meal.find("Nedo."), meal.find("Přepl."))
        self.assertLess(meal.find("Přepl."), meal.find("Předpis"))
        finance = source[finance_pos:]
        self.assertLess(finance.find('"Placeno"'), finance.find('"FKSP"'))
        self.assertLess(finance.find("Nedo."), finance.find("Přepl."))


class RecapLayoutTests(unittest.TestCase):
    def test_cell_markup_keeps_amount_and_currency_together(self):
        marked = cell_markup(format_money(441825), nowrap=True)
        self.assertIn("<nobr>", marked)
        self.assertIn("&nbsp;Kč", marked)
        self.assertNotIn(" Kč", marked.replace("&nbsp;Kč", ""))

    def test_fit_column_widths_gives_leftover_to_flex(self):
        widths = fit_column_widths(100, [(10, 1), (20, 0), (10, 0)])
        self.assertEqual(widths, [70.0, 20.0, 10.0])

    def test_money_paragraph_stays_on_one_line(self):
        from reportlab.lib.enums import TA_RIGHT
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph

        from uzaverka_pdf import measure_text_width, register_report_fonts

        regular, _bold = register_report_fonts()
        style = ParagraphStyle(
            "RecapMoneyTest",
            fontName=regular,
            fontSize=8.5,
            leading=10.2,
            alignment=TA_RIGHT,
            splitLongWords=0,
        )
        sample = format_money(441825)
        width = measure_text_width(sample, regular, 8.5) + 1.6 * mm
        paragraph = Paragraph(cell_markup(sample, nowrap=True), style)
        _w, height = paragraph.wrap(width, 200)
        self.assertLessEqual(height, style.leading * 1.15)


if __name__ == "__main__":
    unittest.main()
