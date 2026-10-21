"""Regression for the 525 individual + 170 bulk portions on 21 October."""
from collections import defaultdict
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from stravovaci_sestava import (
    AppConfig, BULK_DAILY_QUERY, CategorySummary, ConfigError, DinerOrder,
    MenuSummary, NormMenuSummary, ReportData, _include_bulk_orders,
    available_meal_types, create_pdf, fetch_report, render_table,
)


@pytest.fixture
def individual_report():
    # Per-category menu counts transcribed from the reference report.
    counts = [
        ("CIZ", "C", (5, 10, 0)),
        ("ZS11", "B", (153, 31, 0)),
        ("ZS15", "C", (29, 4, 0)),
        ("GYM11", "B", (50, 14, 1)),
        ("GYM15", "C", (103, 81, 6)),
        ("GIO", "C", (11, 22, 5)),
        ("ISŠ", "C", (0, 0, 0)),
        ("ZERO", "A", (0, 0, 0)),
    ]
    menus = defaultdict(int)
    norms = defaultdict(int)
    for code, norm, values in counts:
        for menu, portions in enumerate(values, 1):
            menus[menu] += portions
            norms[norm, menu] += portions
    return ReportData(
        tuple(MenuSummary("Oběd", m, p, "Jídlo") for m, p in menus.items()),
        tuple(CategorySummary(c, c, n, sum(v)) for c, n, v in counts),
        tuple(NormMenuSummary("Oběd", n, m, p) for (n, m), p in norms.items() if p),
        (), "Testovací škola", tuple(c for c, _, _ in counts),
    )


@pytest.fixture
def bulk_rows():
    # The daily values are quantities (62 is not menu 6 or a single order).
    return [
        (None, "ISŠ", "Integrovaná škola", "Oběd", "2", "C", "Jídlo", 40),
        (None, "ISŠ", "Integrovaná škola", "Oběd", "1", "C", "Jídlo", 62),
        (None, "ISŠ", "Integrovaná škola", "Snídaně", "1", "C", "Jídlo", 18),
        (None, "ISŠ", "Integrovaná škola", "Snídaně", "2", "C", "Jídlo", 18),
        (None, "ISŠ", "Integrovaná škola", "Večeře", "2", "C", "Jídlo", 32),
    ]


def test_reference_totals_agree_across_all_three_summaries(individual_report, bulk_rows):
    report = _include_bulk_orders(individual_report, bulk_rows, show_diner_list=False)
    assert {(r.meal_type, r.menu): r.portions for r in report.menus} == {
        ("Oběd", 1): 413, ("Oběd", 2): 202, ("Oběd", 3): 12,
        ("Snídaně", 1): 18, ("Snídaně", 2): 18, ("Večeře", 2): 32,
    }
    by_meal = defaultdict(int)
    for row in report.menus:
        by_meal[row.meal_type] += row.portions
    assert dict(by_meal) == {"Oběd": 627, "Snídaně": 36, "Večeře": 32}
    assert sum(r.portions for r in report.menus) == 695
    assert sum(r.applications for r in report.categories) == 695
    assert sum(r.portions for r in report.norms) == 695
    assert next(r.applications for r in report.categories if r.code == "ISŠ") == 170
    assert next(r.applications for r in report.categories if r.code == "ZERO") == 0
    assert sum(r.portions for r in report.norms if r.norm == "B") == 249
    assert sum(r.portions for r in report.norms if r.norm == "C") == 446
    assert not report.diners


@pytest.mark.parametrize("with_names", [False, True])
def test_fetch_report_includes_bulk_with_same_date_and_category_scope(
    individual_report, bulk_rows, with_names,
):
    config = AppConfig({}, date(2026, 10, 21), individual_report.active_categories,
                       "česky", 1, show_diner_list=with_names)
    cursor = MagicMock()
    results = [
        [(c,) for c in config.categories],
        [(r.meal_type, r.menu, r.portions, r.meal_name) for r in individual_report.menus],
        [(r.code, r.name, r.norm, r.applications) for r in individual_report.categories],
        [(r.meal_type, r.norm, r.menu, r.portions) for r in individual_report.norms],
    ]
    if with_names:
        results.append([])
    results.append(bulk_rows)
    cursor.fetchall.side_effect = results
    cursor.fetchone.return_value = ("Testovací škola",)
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    with patch("psycopg.connect") as connect:
        connect.return_value.__enter__.return_value = connection
        report = fetch_report(config)
    assert sum(r.portions for r in report.menus) == 695
    query, params = cursor.execute.call_args.args
    assert 'p."d21" > 0' in query.as_string()
    assert "BTRIM(p.varianta)" in query.as_string()
    assert params == (date(2026, 10, 21), "česky", 1, with_names, 2026, 10,
                      list(config.categories), None, None)
    assert sum(r.portions for r in report.diners) == (170 if with_names else 0)


def test_category_and_meal_filter_are_passed_to_bulk_query():
    config = AppConfig({}, date(2026, 11, 1), ("ISŠ",), "česky", 1,
                       meal_type="večeře", show_diner_list=False)
    cursor = MagicMock()
    cursor.fetchall.side_effect = [[("ISŠ",)], [], [("ISŠ", "Škola", "C", 0)], [],
        [(None, "ISŠ", "Škola", "Večeře", "2", "C", None, 32)]]
    cursor.fetchone.return_value = None
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    with patch("psycopg.connect") as connect:
        connect.return_value.__enter__.return_value = connection
        report = fetch_report(config)
    query, params = cursor.execute.call_args.args
    assert 'p."d01" > 0' in query.as_string()
    assert params[-5:] == (2026, 11, ["ISŠ"], "večeře", "večeře")
    assert report.menus == (MenuSummary("Večeře", 2, 32, None),)
    # Monthly category overrides the diner's current category, as in closing reports.
    assert "COALESCE(NULLIF(BTRIM(p.kategorie), '')" in BULK_DAILY_QUERY
    assert "BTRIM(k.oznaceni) = ANY(%s::varchar[])" in BULK_DAILY_QUERY
    assert "LOWER(BTRIM(p.typsluzby)) = %s::text" in BULK_DAILY_QUERY


@pytest.mark.parametrize("variant", [None, "", "0", "10", "x"])
def test_positive_bulk_with_unknown_menu_does_not_silently_undercount(
    individual_report, variant,
):
    rows = [(None, "ISŠ", "Škola", "Oběd", variant, "C", None, 62)]
    with pytest.raises(ConfigError, match="varianta"):
        _include_bulk_orders(individual_report, rows, show_diner_list=False)


def test_empty_bulk_preserves_individual_counts(individual_report):
    report = _include_bulk_orders(individual_report, [], show_diner_list=False)
    assert sum(r.portions for r in report.menus) == 525
    assert report.categories == individual_report.categories


def test_bulk_only_meal_types_are_available():
    cursor = MagicMock()
    cursor.fetchall.return_value = [("Oběd",), ("Snídaně",), ("Večeře",)]
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    with patch("psycopg.connect") as connect:
        connect.return_value.__enter__.return_value = connection
        assert available_meal_types({}, date(2026, 10, 21)) == (
            "Oběd", "Snídaně", "Večeře",
        )
    query, params = cursor.execute.call_args.args
    assert "FROM public.prihlasn" in query
    assert params == (2026, 2026, 2026, date(2026, 1, 1), date(2027, 1, 1))


def test_bulk_quantities_are_visible_in_text_and_pdf(
    individual_report, bulk_rows, tmp_path,
):
    from pypdf import PdfReader

    report = _include_bulk_orders(individual_report, bulk_rows, show_diner_list=True)
    config = AppConfig({}, date(2026, 10, 21), report.active_categories, "česky", 1,
                       pdf_output=tmp_path / "bulk.pdf")
    text = render_table(config, report.menus, report.categories, report.norms, report.diners)
    assert "Celkem porcí: 695" in text
    assert "Menu 1 × 62" in text
    pdf = create_pdf(config, report)
    pdf_text = "\n".join(page.extract_text() for page in PdfReader(pdf).pages)
    assert "695" in pdf_text
    assert "Menu 1 × 62" in pdf_text
    assert "Menu 2 × 40" in pdf_text
    assert DinerOrder(None, "ISŠ", None, "Oběd", 1, "C", None).application_label == "Menu 1"
