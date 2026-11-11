from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import shutil

import pytest
from pypdf import PdfReader

from services.collection_status import (
    normalize_collection_status, validate_report_history, validate_task_history,
)
from services.collection_report import fetch_collection_report
from services.web_daily_profiles import (
    DailyProfile, apply_profile, save_profile, load_profiles, profile_file, task_report_config,
)
from services.web_mail_task_store import load_tasks, task_file
from services.web_report_output import manual_pdf_path
from stravovaci_sestava import AppConfig, create_pdf


def config(**kwargs):
    return AppConfig(database={}, report_date=date(2026, 11, 10),
                     categories=("1", "2"), language="česky", menu_list_number=1,
                     collection_status="both", **kwargs)


class Cursor:
    def __init__(self, rows, rates=()):
        self.rows, self.rates = rows, rates
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query.as_string() if hasattr(query, "as_string") else query, params))

    def fetchall(self):
        return self.rows if len(self.calls) == 1 else self.rates


ROWS = [
    ("Alena Černá", "1", "Žáci", "Oběd", 1, "A", 12, "3.A", True),
    ("Jan Novák", "2", "Hosté", "Večeře", 2, "B", 45, None, False),
]


@pytest.mark.parametrize("status,expected", [("both", None), ("collected", True), ("uncollected", False)])
def test_collection_query_uses_exact_day_year_type_and_order(status, expected):
    cursor = Cursor(ROWS)
    cfg = replace(config(), collection_status=status, report_date=date(2024, 2, 29),
                  meal_type=("oběd", "večeře"))
    report = fetch_collection_report(cursor, cfg, cfg.categories, "Jídelna")
    query, params = cursor.calls[0]
    assert 'p."d29"' in query and 'FROM 29 FOR 1' in query
    assert "o.poradiprihl = p.poradiprihl" in query
    assert "o.rok = p.rok AND o.mesic = p.mesic" in query
    assert "LOWER(BTRIM(o.typstravy)) = LOWER(BTRIM(p.typsluzby))" in query
    assert "= 'O'" in query and "p.\"d29\" ~ '^[1-9]$'" in query
    assert "public.prihlasn" not in query
    assert params == (2024, 2, ["1", "2"], ["oběd", "večeře"], ["oběd", "večeře"], expected, expected)
    assert [d.collected for d in report.diners] == [True, False]
    assert sum(m.portions for m in report.menus) == 2


def test_collection_delivery_filter_preserves_status_and_uses_historical_rate_date():
    cursor = Cursor(ROWS, [("1", "oběd", "Rozvoz", True), ("2", "večeře", "Jídelna", True)])
    cfg = replace(config(), delivery_types=("Rozvoz",), report_date=date(2025, 12, 31))
    report = fetch_collection_report(cursor, cfg, cfg.categories, None)
    assert [d.diner_number for d in report.diners] == [12]
    assert report.diners[0].collected is True
    assert sum(m.portions for m in report.menus) == 1
    assert cursor.calls[1][1] == (["1", "2"], date(2025, 12, 31), date(2025, 12, 31))


@pytest.mark.parametrize("status", ["both", "collected", "uncollected"])
def test_collection_profile_roundtrip_and_legacy_isolation(tmp_path, status):
    profile = DailyProfile.from_dict({"name": "Odběry", "categories": ["1"],
                                     "meal_type": ["oběd", "večeře"],
                                     "delivery_types": ["Rozvoz"], "collection_status": status})
    save_profile(profile_file(tmp_path), profile)
    loaded = load_profiles(profile_file(tmp_path))[0]
    applied = apply_profile(config(), loaded, {"poctyemailem": {"vsechny_kategorie": True}})
    assert applied.collection_status == status
    assert applied.meal_type == ("oběd", "večeře")
    assert applied.delivery_types == ("Rozvoz",)
    assert task_report_config(config(), {}, SimpleNamespace(profile_id=None), tmp_path).collection_status is None
    assert DailyProfile.from_dict({"name": "Starý", "categories": ["1"]}).collection_status is None


def test_history_is_exclusive_to_collection():
    today = date(2026, 1, 1)
    yesterday = date(2025, 12, 31)
    validate_report_history(today, None, today=today)
    with pytest.raises(ValueError, match="minulosti"):
        validate_report_history(yesterday, None, today=today)
    task = SimpleNamespace(date_mode="offset", day_offset=-1)
    with pytest.raises(ValueError, match="Dny zpět"):
        validate_task_history(task, None, today=today)
    for status in ("both", "collected", "uncollected"):
        validate_report_history(yesterday, status, today=today)
        validate_task_history(task, status, today=today)
    for invalid in (False, [], "all", "", 1):
        with pytest.raises(ValueError):
            normalize_collection_status(invalid)


def test_collection_outputs_do_not_overwrite_each_other():
    paths = {manual_pdf_path(Path("report.pdf"), ("1",), ("1",),
                            collection_status=status, delivery_types=delivery)
             for status in (None, "both", "collected", "uncollected")
             for delivery in ((), ("Rozvoz",))}
    assert len(paths) == 8


@pytest.mark.parametrize("orientation", ["na_vysku", "na_sirku"])
def test_collection_pdf_contains_identified_people_and_status(tmp_path, orientation):
    cfg = config(pdf_output=tmp_path / "odbery.pdf", pdf_orientation=orientation)
    report = fetch_collection_report(Cursor(ROWS), cfg, cfg.categories, "Testovací jídelna")
    text = "\n".join(p.extract_text() for p in PdfReader(create_pdf(cfg, report)).pages)
    assert "Odebraná / neodebraná strava" in text
    assert "Alena Černá" in text and "Jan Novák" in text
    assert "Odebraná: 1" in text and "Neodebraná: 1" in text
    assert "3.A" in text and "Večeře" in text and "45" in text
    assert "Jídelníček a počty porcí" not in text


def test_empty_collection_pdf_is_explicit(tmp_path):
    cfg = config(pdf_output=tmp_path / "prazdne.pdf")
    report = fetch_collection_report(Cursor([]), cfg, cfg.categories, None)
    text = "\n".join(p.extract_text() for p in PdfReader(create_pdf(cfg, report)).pages)
    assert "nebyly nalezeny žádné objednávky" in text


def test_large_collection_starts_on_first_page_and_continues(tmp_path):
    rows = [(f"Testovací osoba {i:04}", "1", "Žáci", "Oběd", 1, "A", i, "3.A", True)
            for i in range(787)]
    cfg = replace(config(), collection_status="collected", category_separation=True,
                  pdf_orientation="na_vysku", pdf_output=tmp_path / "dlouhy.pdf")
    report = fetch_collection_report(Cursor(rows), cfg, cfg.categories, "Testovací jídelna")
    pages = PdfReader(create_pdf(cfg, report)).pages
    assert len(pages) > 1
    assert "Testovací osoba 0000" in pages[0].extract_text()
    assert "Testovací osoba 0786" in "\n".join(page.extract_text() for page in pages)


def test_worker_only_dispatches_historical_collection_profiles(tmp_path):
    from services import web_mail_worker as worker
    from services.web_mail_tasks import MailTask
    profile = DailyProfile.from_dict({"name": "Odběry", "categories": ["1"], "collection_status": "both"})
    save_profile(profile_file(tmp_path), profile)
    task = MailTask.from_dict({"name": "Včera", "recipients": ["test@example.org"],
                               "send_time": "08:00", "date_mode": "offset", "day_offset": -1,
                               "profile_id": profile.id})
    with patch.object(worker, "resolve_task_date", return_value=date(2025, 12, 31)), \
         patch.object(worker, "report_is_cooking_day", return_value=True), \
         patch.object(worker, "deliver_daily") as deliver:
        worker.dispatch(tmp_path / "config.json", task, date(2026, 1, 1))
        deliver.assert_called_once_with(tmp_path / "config.json", task, date(2025, 12, 31))
        deliver.reset_mock()
        save_profile(profile_file(tmp_path), replace(profile, collection_status=None))
        with pytest.raises(ValueError, match="Dny zpět"):
            worker.dispatch(tmp_path / "config.json", task, date(2026, 1, 1))
        deliver.assert_not_called()


@pytest.mark.asyncio
async def test_wizard_collection_history_meal_filters_and_saved_schedule(tmp_path):
    from nicegui.testing.user_simulation import user_simulation
    from stravovaci_nicegui import NiceGuiApp
    path = tmp_path / "config.json"
    shutil.copyfile(Path(__file__).with_name("config.example.json"), path)
    pages = []
    def root():
        page = NiceGuiApp(path)
        page.build()
        page.populate_categories([("1", "Žáci"), ("2", "Hosté")])
        pages.append(page)
    with patch.object(NiceGuiApp, "_stored_password", return_value=""), \
         patch.object(NiceGuiApp, "_stored_api_key", return_value=""), \
         patch.object(NiceGuiApp, "_schedule_first_run"):
        async with user_simulation(root) as user:
            await user.open("/")
            with user:
                page = pages[0]
                page.wizard_name.value = "Včerejší odběry"
                page.date_input.value = (date.today() - timedelta(days=1)).strftime("%d.%m.%Y")
                with pytest.raises(ValueError, match="minulosti"):
                    page._wizard_validate(2)
                page.wizard_content.value = "collection"
                assert set(page.collection_status_select.options) == {"both", "collected", "uncollected"}
                page.collection_status_select.value = "uncollected"
                page.connection_ok = True
                page._connection_password = "test-only"
                sample = fetch_collection_report(Cursor(ROWS), config(), ("1", "2"), None)
                with patch.object(page, "_fetch_daily_summary", return_value=sample):
                    await page.refresh_daily_summary()
                assert [row["name"] for row in page.daily_collection_table.rows] == ["Alena Černá", "Jan Novák"]
                assert [row["status"] for row in page.daily_collection_table.rows] == ["Odebraná", "Neodebraná"]
                assert page.daily_collection_table.visible
                from credential_store import write_config
                write_config(path, page._collect_config())
                with patch("stravovaci_sestava.get_password", return_value="test-only"), \
                     patch("stravovaci_nicegui.fetch_report", return_value=sample):
                    output = page._create_pdf(categories=("1", "2"), allowed_categories=("1", "2"))
                pdf_text = "\n".join(p.extract_text() for p in PdfReader(output).pages)
                assert "Alena Černá" in pdf_text and "Jan Novák" in pdf_text
                assert "Neodebraná strava" in pdf_text
                page.meal_type_select.set_options({"oběd": "Oběd", "večeře": "Večeře"}, value=["oběd", "večeře"])
                page.delivery_type_select.set_options({"Rozvoz": "Rozvoz"}, value=["Rozvoz"])
                page._apply_daily_categories(["2"])
                page._wizard_validate(2)
                assert page.show_diner_list.value and not page.show_diner_list.enabled
                assert "yesterday" in page.wizard_mode.options
                page.wizard_mode.value = "yesterday"
                page.wizard_recipients.input.value = "test@example.org"
                page.wizard_enabled.value = False
                task = page._wizard_task(validate_recipients=False)
                assert task.date_mode == "offset" and task.day_offset == -1
                page.wizard_mode.value = "history"
                page.wizard_history_days.value = 10
                assert page._wizard_task(validate_recipients=False).day_offset == -10
                page.wizard_mode.value = "yesterday"
                page._wizard_save()
                profile = load_profiles(profile_file(tmp_path))[0]
                task = load_tasks(task_file(tmp_path))[0]
                assert profile.collection_status == "uncollected"
                assert profile.categories == ("2",) and profile.meal_type == ("oběd", "večeře")
                assert profile.delivery_types == ("Rozvoz",)
                assert task.day_offset == -1 and task.profile_id == profile.id
                page._wizard_new()
                assert page._selected_collection_status() is None
                assert not page.daily_collection_table.visible
                assert "yesterday" not in page.wizard_mode.options
