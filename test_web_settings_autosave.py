"""Autosave persists valid preferences without running services or sending mail."""
import asyncio
from unittest.mock import patch

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from services.web_mail_settings import load_settings, settings_path
from services.web_mail_settings_gui import build_web_settings_panel


def field(user, label):
    return next(e for e in user.client.elements.values()
                if isinstance(e, (ui.input, ui.number)) and e.props.get("label") == label)


@pytest.mark.asyncio
async def test_autosave_preserves_last_valid_values_and_rejects_locked_changes(tmp_path):
    access = {"valid": True}
    flushes = []
    with patch("services.web_mail_settings_gui.service_command") as command:
        async with user_simulation(lambda: build_web_settings_panel(
            tmp_path, require_admin=lambda: access["valid"], before_lock=flushes,
        )) as user:
            await user.open("/")
            with user:
                field(user, "Zobrazované jméno odesílatele").value = "Školní jídelna"
            await asyncio.sleep(.1)
            assert not settings_path(tmp_path).exists()
            await asyncio.sleep(.85)
            path = settings_path(tmp_path)
            assert load_settings(path)["from_name"] == "Školní jídelna"
            await user.should_see("Uloženo.")
            await user.should_not_see("Uložit nastavení")
            original = path.read_bytes()
            with user:
                field(user, "Výchozí předmět").value = "{unknown}"
            await asyncio.sleep(.85)
            assert path.read_bytes() == original
            await user.should_see("Změny nejsou uložené:")
            with user:
                field(user, "Výchozí předmět").value = "Přehled {report} – {date}"
                # Flush pending valid edits before a manual logout.
                flushes[0]()
            assert load_settings(path)["subject_template"] == "Přehled {report} – {date}"
            original = path.read_bytes()
            with user:
                field(user, "Zobrazované jméno odesílatele").value = "Neuložená změna"
                access["valid"] = False
            await asyncio.sleep(.85)
            assert path.read_bytes() == original
            command.assert_not_called()


@pytest.mark.asyncio
async def test_browse_selected_files_are_saved_and_cancel_keeps_path(tmp_path):
    binary = tmp_path / "nssm.exe"; binary.touch()
    template = tmp_path / "dashboard.template.html"; template.write_text("<html></html>")
    with patch("services.web_mail_settings_gui.pick_local_file", side_effect=[str(binary), str(template), None]):
        async with user_simulation(lambda: build_web_settings_panel(tmp_path)) as user:
            await user.open("/")
            user.find(marker="browse-nssm").click()
            await asyncio.sleep(.9)
            assert load_settings(settings_path(tmp_path))["nssm_path"] == str(binary)
            user.find(marker="browse-dashboard").click()
            await asyncio.sleep(.9)
            assert load_settings(settings_path(tmp_path))["dashboard_path"] == str(template)
            original = settings_path(tmp_path).read_bytes()
            user.find(marker="browse-nssm").click()
            await asyncio.sleep(.1)
            assert settings_path(tmp_path).read_bytes() == original
