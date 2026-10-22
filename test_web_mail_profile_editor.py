"""Check the one-choice editor and preservation of existing task settings."""
from datetime import date
from unittest.mock import patch

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from services.web_daily_profiles import DailyProfile, profile_file, save_profile
from services.web_mail_gui import build_mail_tasks_panel, LEGACY_PROFILE_LABEL
from services.web_mail_task_store import load_tasks, save_tasks, task_file
from services.web_mail_tasks import MailTask


def field(user, kind, label):
    return next(e for e in user.client.elements.values()
                if isinstance(e, kind) and (e.props.get("label") or e.props.get("aria-label")) == label)


@pytest.mark.asyncio
async def test_new_task_selects_a_named_profile_and_shows_its_contents(tmp_path):
    first = DailyProfile.from_dict({"name": "Školní obědy", "categories": ["1", "2"],
                                    "meal_type": "oběd", "show_diner_list": False})
    other = DailyProfile.from_dict({"name": "Ostatní", "categories": ["3"]})
    for p in (first, other):
        save_profile(profile_file(tmp_path), p)

    def root():
        build_mail_tasks_panel(tmp_path, category_names=lambda: {"1": "Žáci", "2": "Zaměstnanci"})

    with patch("services.web_mail_gui.resolve_task_date", return_value=date(2026, 10, 22)):
        async with user_simulation(root) as user:
            await user.open("/")
            user.find("Nové odesílání").click()
            with user:
                choices = field(user, ui.select, "Který přehled odesílat?")
                assert choices.options == {first.id: first.name, other.id: other.name}
                assert choices.value is None
                assert all(e.props.get("label") != "Sestava" for e in user.find(ui.select).elements)
                field(user, ui.input, "Název odesílání").value = "Ranní přehled"
                field(user, ui.input, "E-mail příjemce").value = "test@example.org"
            user.find("Uložit").click()
            assert not load_tasks(task_file(tmp_path))
            with user:
                choices.value = first.id
                assert not field(user, ui.number, "Posun od dneška (dní)").visible
                assert not field(user, ui.input, "Vybraný den").visible
                field(user, ui.select, "Za který den?").value = "offset"
                assert field(user, ui.number, "Posun od dneška (dní)").visible
            user.find("Co přehled obsahuje?").click()
            await user.should_see("Uložené kategorie: Žáci, Zaměstnanci.")
            await user.should_see("Bez seznamu strávníků.")
            user.find("Uložit").click()
            saved = load_tasks(task_file(tmp_path))
            assert len(saved) == 1
            assert saved[0].profile_id == first.id
            assert saved[0].report == "daily"


@pytest.mark.asyncio
async def test_editing_old_task_keeps_shared_settings_until_user_changes_them(tmp_path):
    saved = DailyProfile.from_dict({"name": "Škola", "categories": ["1"]})
    save_profile(profile_file(tmp_path), saved)
    old = MailTask.from_dict({"name": "Původní úloha", "recipients": ["test@example.org"],
                              "send_time": "08:00", "date_mode": "today"})
    save_tasks(task_file(tmp_path), [old])

    with patch("services.web_mail_gui.resolve_task_date", return_value=date(2026, 10, 22)):
        async with user_simulation(lambda: build_mail_tasks_panel(tmp_path)) as user:
            await user.open("/")
            user.find("Upravit").click()
            with user:
                choices = field(user, ui.select, "Který přehled odesílat?")
                assert choices.value == ""
                assert choices.options[""] == LEGACY_PROFILE_LABEL
            user.find("Uložit").click()
            assert load_tasks(task_file(tmp_path)) == [old]
