import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fksp_sestava import fksp_report_from_podklady
from rekapitulace_sestava import recap_report_from_podklady
from stravovaci_arch import arch_report_from_podklady
from uzaverka_pdf import SubjectHeader
from uzaverka_podklady import (
    FINGERPRINT_QUERY,
    ClosingCounts,
    ClosingPodklady,
    PrihlasPodklad,
    fingerprint_digest,
    load_cache,
    save_cache,
)


def sample_row(**overrides: object) -> PrihlasPodklad:
    values = dict(
        name="Novák Jan",
        evidence_no=101,
        var_symbol="101",
        class_name="1.A",
        category_code="6",
        diner_category="6",
        category_name="Učitelé",
        diner_category_name="Učitelé",
        norm="C",
        meal_type="Oběd",
        payment_method_code="4",
        deleted=False,
        days=("1",) * 16 + ("",) * 15,
        portions=16,
        portions_live=16,
        prescription=656,
        monthly_limit=656,
        fksp=80,
        fksp_diner=80,
        other_overhead=0,
        other_overhead_diner=0,
        payment=200,
        credit_prev=50,
        credit_now=30,
    )
    values.update(overrides)
    return PrihlasPodklad(**values)  # type: ignore[arg-type]


def sample_podklady(*rows: PrihlasPodklad, bulk: tuple[PrihlasPodklad, ...] = ()) -> ClosingPodklady:
    people = rows or (sample_row(),)
    return ClosingPodklady(
        header=SubjectHeader(
            subject_name="ZS Kozinova",
            address="Kozinova 1000",
            zip_code="102 00",
            city="Praha 15",
            company_id="47611332",
            vat_id="47611332",
        ),
        payments={"4": "Z běžného účtu"},
        individuals=people,
        bulk=bulk,
        counts=ClosingCounts(
            dining=1107,
            registered=1180,
            enrolled=1296,
            bulk=len(bulk),
            by_category={"6": (48, 46), "12": (2, 2)},
        ),
        period=date(2026, 5, 1),
        fingerprint="abc123",
    )


class FingerprintTests(unittest.TestCase):
    def test_query_placeholder_count_matches_fetch_params(self):
        self.assertEqual(FINGERPRINT_QUERY.count("%s"), 24)

    def test_digest_changes_when_a_part_changes(self):
        first = fingerprint_digest((10, "aaa", 1.5))
        second = fingerprint_digest((11, "aaa", 1.5))
        self.assertNotEqual(first, second)
        self.assertEqual(len(first), 64)


class CacheTests(unittest.TestCase):
    def test_roundtrip_keeps_rows_and_marks_cache(self):
        original = sample_podklady(sample_row(portions=19, fksp=95))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "2026-05.json"
            save_cache(path, original)
            loaded = load_cache(path)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertTrue(loaded.from_cache)
        self.assertEqual(loaded.fingerprint, "abc123")
        self.assertEqual(loaded.individuals[0].portions, 19)
        self.assertEqual(loaded.individuals[0].fksp, 95)
        self.assertEqual(len(loaded.individuals[0].days), 31)

    def test_rejects_wrong_version(self):
        original = sample_podklady()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "2026-05.json"
            save_cache(path, original)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["version"] = 999
            path.write_text(json.dumps(raw), encoding="utf-8")
            self.assertIsNone(load_cache(path))


class ReportFromPodkladyTests(unittest.TestCase):
    def test_arch_skips_zero_portions_and_other_categories(self):
        podklady = sample_podklady(
            sample_row(evidence_no=1, portions=16),
            sample_row(evidence_no=2, portions=0, name="Prázdný"),
            sample_row(evidence_no=3, portions=8, category_code="12", diner_category="12"),
        )
        report = arch_report_from_podklady(
            podklady, categories=("6",), include_bulk=False
        )
        self.assertEqual([person.evidence_no for person in report.individuals], [1])
        self.assertEqual(report.individuals[0].payment_method, "Z běžného účtu")
        self.assertEqual(report.bulk, ())

    def test_recap_keeps_zero_portion_payment_and_splits_credit(self):
        podklady = sample_podklady(
            sample_row(
                evidence_no=1,
                portions=10,
                prescription=680,
                monthly_limit=410,
                payment=100,
                credit_prev=80,
                credit_now=50,
            ),
            sample_row(
                evidence_no=2,
                portions=0,
                prescription=0,
                monthly_limit=0,
                fksp=0,
                payment=-40,
                credit_prev=-40,
                credit_now=0,
                name="Dluh",
            ),
        )
        report = recap_report_from_podklady(
            podklady, categories=("6",), variant="R"
        )
        self.assertEqual(len(report.rows), 1)
        row = report.rows[0]
        self.assertEqual(row.portions, 10)
        self.assertEqual(row.credit_prev_plus, 80)
        self.assertEqual(row.debit_prev, 40)
        self.assertEqual(row.payment, 100)
        self.assertEqual(row.debit_now, 40)
        self.assertEqual(row.credit_now_plus, 50)
        self.assertEqual(report.counts.dining, 1107)

    def test_fksp_skips_deleted_and_uses_diner_category(self):
        podklady = sample_podklady(
            sample_row(name="Učitel", portions_live=19, fksp_diner=95),
            sample_row(
                name="Smazaný",
                evidence_no=102,
                deleted=True,
                portions_live=5,
                fksp_diner=25,
            ),
            sample_row(
                name="Jiná kat",
                evidence_no=103,
                diner_category="12",
                portions_live=4,
                fksp_diner=20,
            ),
        )
        report = fksp_report_from_podklady(podklady, categories=("6",))
        self.assertEqual([row.name for row in report.individuals], ["Učitel"])
        self.assertEqual(report.individuals[0].total_amount, 95)
        self.assertEqual(report.individuals[0].portions, 19)


class GenerateReportsWiringTests(unittest.TestCase):
    def test_generate_reports_fetches_podklady_once_and_passes_them(self):
        import uzaverka as closing

        fake_podklady = SimpleNamespace(from_cache=True)
        settings = SimpleNamespace(
            reports=("fksp", "stravovaci_arch", "rekapitulace"),
            include_bulk_arch=True,
            recap_variant="R",
        )
        config = SimpleNamespace(categories=("6",), database={})
        seen: list[object] = []

        def exporter(_cfg, _stg, on_progress=None, podklady=None):
            del on_progress
            seen.append(podklady)
            return Path(f"sestava_{len(seen)}.pdf")

        with (
            mock.patch.object(
                closing, "fetch_closing_podklady", return_value=fake_podklady
            ) as fetch,
            mock.patch.object(closing, "export_fksp_pdf", side_effect=exporter),
            mock.patch.object(closing, "export_arch_pdf", side_effect=exporter),
            mock.patch.object(closing, "export_recap_pdf", side_effect=exporter),
        ):
            created = closing.generate_reports(config, settings)

        fetch.assert_called_once()
        self.assertEqual(len(created), 3)
        self.assertEqual(seen, [fake_podklady, fake_podklady, fake_podklady])


if __name__ == "__main__":
    unittest.main()
