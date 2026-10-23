"""Saved filter isolation, permission changes and backwards-compatible scheduling."""
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.web_daily_profiles import (
    DailyProfile, apply_profile, load_profiles, profile_file, save_profile, task_report_config,
)
from services.web_mail_task_store import load_tasks, save_tasks, task_file
from services.web_mail_tasks import MailTask
from stravovaci_sestava import AppConfig


def profile(name="Školní", categories=("1", "2"), **kwargs):
    return DailyProfile.from_dict({"name": name, "categories": categories, **kwargs})


def config():
    return AppConfig(database={}, report_date=date(2026, 10, 21), categories=(),
                     language="česky", menu_list_number=1)


def test_two_and_four_category_profiles_survive_updates_and_restart(tmp_path):
    path = profile_file(tmp_path)
    first = profile()
    second = profile("Ostatní", ("3", "4", "5", "6"), meal_type="Bezlepková")
    save_profile(path, first)
    save_profile(path, second)
    save_profile(path, replace(first, name="Školní stravování"))
    loaded = load_profiles(path)
    assert [p.categories for p in loaded] == [("1", "2"), ("3", "4", "5", "6")]
    assert loaded[0].name == "Školní stravování"
    assert loaded[1].meal_type == "bezlepková"


def test_profiles_never_expand_admin_permissions():
    raw = {"poctyemailem": {"vsechny_kategorie": False, "povolene_kategorie": ["2"]}}
    original = profile()
    assert apply_profile(config(), original, raw).categories == ("2",)
    assert original.categories == ("1", "2")
    with pytest.raises(ValueError, match="povolena"):
        apply_profile(config(), profile(categories=("3",)), raw)


def test_empty_or_malformed_filter_is_not_all_categories():
    with pytest.raises(ValueError):
        profile(categories=())
    with pytest.raises(ValueError):
        profile(categories="12")
    with pytest.raises(ValueError):
        profile(show_by_norms="false")


def test_damaged_profile_store_is_not_overwritten(tmp_path):
    path = profile_file(tmp_path)
    path.write_text('{"profiles": {}}', encoding="utf-8")
    with pytest.raises(ValueError):
        save_profile(path, profile())
    assert path.read_text(encoding="utf-8") == '{"profiles": {}}'


def test_scheduler_profile_roundtrip_and_legacy_tasks(tmp_path):
    saved = profile()
    save_profile(profile_file(tmp_path), saved)
    legacy = MailTask.from_dict({"name": "Legacy", "recipients": ["test@example.org"],
                                 "send_time": "07:00", "date_mode": "today"})
    selected = replace(legacy, id="other", profile_id=saved.id)
    save_tasks(task_file(tmp_path), [legacy, selected])
    tasks = load_tasks(task_file(tmp_path))
    assert tasks[0].profile_id is None
    assert tasks[1].profile_id == saved.id
    original = config()
    assert task_report_config(original, {}, tasks[0], tmp_path) is original
    assert task_report_config(original, {}, tasks[1], tmp_path).categories == ("1", "2")
    with pytest.raises(ValueError, match="neexistuje"):
        task_report_config(original, {}, replace(selected, profile_id="missing"), tmp_path)


def test_worker_generates_selected_profile_without_sending_real_mail(tmp_path):
    from services import web_mail_worker as worker
    saved = profile(categories=("3", "4", "5", "6"), meal_type="bezlepková", show_diner_list=False)
    save_profile(profile_file(tmp_path), saved)
    task = SimpleNamespace(profile_id=saved.id, recipients=("test@example.org",), id="test")
    settings = {"transport": "smtp", "subject_template": "{report} {date}", "body_template": "{date}"}
    with patch.object(worker, "read_saved_settings", return_value={}), \
         patch.object(worker, "load_settings", return_value=settings), \
         patch.object(worker, "load_config", return_value=config()), \
         patch.object(worker, "fetch_report", return_value=object()) as fetch, \
         patch.object(worker, "create_pdf", return_value=tmp_path / "report.pdf") as pdf, \
         patch.object(worker, "smtp_send", return_value=task.recipients) as send:
        worker.deliver_daily(tmp_path / "config.json", task, date(2026, 10, 21))
    passed = fetch.call_args.args[0]
    assert passed.categories == ("3", "4", "5", "6")
    assert passed.meal_type == "bezlepková"
    assert not passed.show_diner_list
    assert "_prehled_" in str(pdf.call_args.kwargs["output_path"])
    send.assert_called_once()
