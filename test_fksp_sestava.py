import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from fksp_sestava import (
    FkspHeader,
    FkspReport,
    FkspRow,
    create_fksp_pdf,
    format_money,
)
from uzaverka_nastaveni import parse_closing_settings


class FkspReportTests(unittest.TestCase):
    def test_formats_czech_money(self):
        self.assertEqual(format_money(95), "95,00\u00a0Kč")
        self.assertEqual(format_money(4560), "4.560,00\u00a0Kč")
        self.assertEqual(format_money(5.0), "5,00\u00a0Kč")
        self.assertNotIn(" ", format_money(2381021))

    def test_unit_amount_is_total_divided_by_portions(self):
        row = FkspRow(
            name="Novák",
            category_code="6",
            category_name="Učitelé",
            meal_type="Oběd",
            portions=19,
            total_amount=95,
            other_overhead=0,
        )
        self.assertEqual(row.unit_amount, 5)

    def test_creates_pdf_from_prepared_rows(self):
        report = FkspReport(
            header=FkspHeader(
                subject_name="ZS Kozinova",
                address="Kozinova 1000",
                zip_code="102 00",
                city="Praha 15",
                company_id="47611332",
                vat_id="47611332",
            ),
            individuals=(
                FkspRow(
                    name="Novák Jan",
                    category_code="6",
                    category_name="Učitelé",
                    meal_type="Oběd",
                    portions=19,
                    total_amount=95,
                    other_overhead=0,
                ),
            ),
            bulk=(),
            period=date(2026, 7, 1),
        )
        config = SimpleNamespace(pdf_data_font_size=8.5, pdf_label_font_size=9.0, pdf_bold=False)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "FKSP_2026-07.pdf"
            created = create_fksp_pdf(config, report, output)
            self.assertTrue(created.is_file())
            self.assertGreater(created.stat().st_size, 1000)

    def test_example_output_placeholder_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = parse_closing_settings(
                {
                    "uzaverka": {
                        "sestavy": ["fksp"],
                        "vystup": "out/{rok}-{mesic}",
                    }
                },
                year=2026,
                month=7,
                config_directory=Path(directory),
            )
        self.assertIn("2026-07", str(settings.output_directory))


if __name__ == "__main__":
    unittest.main()
