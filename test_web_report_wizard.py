"""Exercise the new flow, persisted PDF snapshot and scheduler timing without mail."""
from dataclasses import replace
from datetime import date, datetime, timedelta
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from nicegui.testing.user_simulation import user_simulation

from services.web_daily_profiles import DailyProfile, apply_profile, load_profiles, profile_file
from services.web_mail_task_store import load_tasks, save_tasks, task_file
from services.web_mail_tasks import MailTask, next_send_at
from services.web_worker_status import observed_status, write_runtime
from stravovaci_nicegui import NiceGuiApp
from stravovaci_sestava import AppConfig


@pytest.mark.asyncio
async def test_four_steps_save_snapshot_and_new_plan_starts_today(tmp_path):
    config = tmp_path / "config.json"
    shutil.copyfile(Path(__file__).with_name("config.example.json"), config)
    pages = []
    def root():
        page = NiceGuiApp(config)
        page.build()
        page.populate_categories([("1", "Žáci"), ("2", "Hosté")])
        pages.append(page)
    with patch.object(NiceGuiApp, "_stored_password", return_value=""), \
         patch.object(NiceGuiApp, "_stored_api_key", return_value=""), \
         patch.object(NiceGuiApp, "_schedule_first_run"), \
         patch.object(NiceGuiApp, "_send_mail_worker") as send:
        async with user_simulation(root) as user:
            await user.open("/")
            with user:
                page = pages[0]
                assert page.date_input.value == date.today().strftime("%d.%m.%Y")
                assert [c.visible for c in page._wizard_cards] == [True, False, False, False]
                page._wizard_next_step()
                assert page._wizard_step == 1 and "název" in page.wizard_error.text.lower()
                page.wizard_name.value = "Počty pro hosty"
                page._apply_daily_categories(["2"])
                page.meal_type_select.set_options({"oběd-a": "Oběd-A", "večeře": "Večeře"}, value=["oběd-a", "večeře"])
                page._wizard_next_step()
                assert page._wizard_step == 2
                page.wizard_content.value = "counts"
                assert not page.show_diner_list.value
                page.pdf_orientation.value = "na_sirku"
                page.pdf_data_size.value = 12
                page.pdf_bold.value = True
                page._wizard_next_step()
                assert page._wizard_step == 3
                page.wizard_mode.value = "after_tomorrow"
                await page._wizard_preview()
                assert (date.today() + timedelta(days=2)).strftime("%d.%m.%Y") in page.wizard_date_preview.text
                page._wizard_next_step()
                assert page._wizard_step == 4
                page.wizard_name.value = "Počty pro hosty"
                page.wizard_recipients.input.value = "vedouci@example.org"
                page._wizard_next_step()
                assert page._wizard_saved
                stored = load_tasks(task_file(tmp_path))
                assert len(stored) == 1
                task = stored[0]
                assert task.recipients == ("vedouci@example.org",)
                assert task.date_mode == "offset" and task.day_offset == 2
                profile = load_profiles(profile_file(tmp_path))[0]
                assert profile.categories == ("2",)
                assert profile.meal_type == ("oběd-a", "večeře")
                assert not profile.show_diner_list
                assert profile.pdf_orientation == "na_sirku"
                assert profile.pdf_data_font_size == 12 and profile.pdf_bold
                assert profile.id == task.profile_id
                assert task.first_send_date == next_send_at(task, datetime.now()).date().isoformat()
                assert "není potvrzen" in page.wizard_receipt_status.text
                page._wizard_save()  # repeated click cannot create duplicate tasks
                assert len(load_tasks(task_file(tmp_path))) == 1
                page._wizard_new()
                assert page._wizard_step == 1
                assert page.wizard_name.value == ""
                assert page.date_input.value == date.today().strftime("%d.%m.%Y")
            send.assert_not_called()


@pytest.mark.asyncio
async def test_wizard_validates_email_and_resolves_unsaved_cooking_filters(tmp_path):
    config = tmp_path / "config.json"
    shutil.copyfile(Path(__file__).with_name("config.example.json"), config)
    pages = []
    def root():
        page = NiceGuiApp(config)
        page.build()
        page.populate_categories([("1", "Žáci")])
        pages.append(page)
    with patch.object(NiceGuiApp, "_stored_password", return_value=""), \
         patch.object(NiceGuiApp, "_stored_api_key", return_value=""), \
         patch.object(NiceGuiApp, "_schedule_first_run"):
        async with user_simulation(root) as user:
            await user.open("/")
            with user:
                page = pages[0]
                page.wizard_name.value = "Večeře"
                page.meal_type_select.set_options({"večeře": "Večeře"}, value=["večeře"])
                page.wizard_mode.value = "next_cooking_day"
                page._wizard_show_step(3)
                with patch("services.web_report_wizard.resolve_task_date", return_value=date(2026, 11, 2)) as resolve:
                    await page._wizard_preview()
                assert "pondělí 02.11.2026" in page.wizard_date_preview.text
                assert resolve.call_args.args[1].cooking_meal_type == "večeře"
                assert not profile_file(tmp_path).exists()
                page._wizard_next_step()
                page._wizard_next_step()
                assert not page._wizard_saved
                assert page.wizard_error.text
                assert not task_file(tmp_path).exists()
                page.wizard_recipients.input.value = "bad address"
                page._wizard_next_step()
                assert not task_file(tmp_path).exists()


def test_pdf_snapshot_overrides_global_but_legacy_profile_inherits_it():
    base = AppConfig(database={}, report_date=date.today(), categories=("1",), language="česky",
                     menu_list_number=1, pdf_data_font_size=7, pdf_orientation="na_vysku")
    old = DailyProfile.from_dict({"name": "Starý", "categories": ["1"]})
    assert apply_profile(base, old, {}).pdf_data_font_size == 7
    new = DailyProfile.from_dict({**old.to_dict(), "pdf_data_font_size": 12, "pdf_orientation": "na_sirku", "show_diner_list": False})
    result = apply_profile(base, new, {})
    assert result.pdf_data_font_size == 12 and result.pdf_orientation == "na_sirku"
    assert not result.show_diner_list
    for invalid in (float("nan"), float("inf"), 19, True):
        with pytest.raises(ValueError):
            DailyProfile.from_dict({**old.to_dict(), "pdf_data_font_size": invalid})


def test_observed_running_waiting_stopped_and_stale(tmp_path):
    task = MailTask.from_dict({"name": "Počty", "recipients": ["a@example.org"], "send_time": "08:00"})
    assert "není potvrzen" in observed_status(tmp_path, task)
    write_runtime(tmp_path, phase="waiting")
    assert "čeká" in observed_status(tmp_path, task)
    write_runtime(tmp_path, phase="running", task_id=task.id)
    assert "Právě zpracovává" in observed_status(tmp_path, task)
    assert "není potvrzen" in observed_status(tmp_path, task, now=datetime.now() + timedelta(minutes=2))
    write_runtime(tmp_path, phase="stopped")
    assert "zastaven" in observed_status(tmp_path, task)
    assert "Pozastaveno" == observed_status(tmp_path, replace(task, enabled=False))


def test_new_plan_does_not_send_immediately_when_todays_time_has_passed(tmp_path):
    from services import web_mail_worker as worker
    task = MailTask.from_dict({"name": "Počty", "recipients": ["a@example.org"], "send_time": "08:00",
                               "first_send_date": "2026-10-30"})
    save_tasks(task_file(tmp_path), [task])
    with patch.object(worker, "dispatch") as dispatch:
        worker.tick(tmp_path / "config.json", datetime(2026, 10, 29, 15))
        dispatch.assert_not_called()
        worker.tick(tmp_path / "config.json", datetime(2026, 10, 30, 8))
        dispatch.assert_called_once()
