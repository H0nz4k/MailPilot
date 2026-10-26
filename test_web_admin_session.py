"""An expired admin session cannot be revived by activity or save callbacks."""
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from services.web_admin_session import ADMIN_IDLE_SECONDS
from stravovaci_nicegui import NiceGuiApp


@pytest.mark.asyncio
async def test_idle_expiry_closes_admin_dialogs_and_rejects_late_writes(tmp_path):
    config = tmp_path / "config.json"
    shutil.copyfile(Path(__file__).with_name("config.example.json"), config)
    pages = []
    clock = [1000.0]

    def root():
        page = NiceGuiApp(config)
        page.build()
        pages.append(page)

    with patch.object(NiceGuiApp, "_stored_password", return_value=""), \
         patch.object(NiceGuiApp, "_stored_api_key", return_value=""), \
         patch.object(NiceGuiApp, "_schedule_first_run"), \
         patch("stravovaci_nicegui.get_admin_password", return_value="secret"), \
         patch("services.web_admin_session.monotonic", side_effect=lambda: clock[0]), \
         patch("stravovaci_nicegui.save_jobs") as save_jobs:
        async with user_simulation(root) as user:
            await user.open("/")
            with user:
                page = pages[0]
                page.admin_password_input.value = "secret"
                page.confirm_admin()
                assert page.admin_unlocked
                assert page.admin_password_input.value == ""
                assert page.tabs.value == "admin"
                picker = ui.dialog()
                picker.open()
                clock[0] += ADMIN_IDLE_SECONDS - 1
                page._check_admin_idle()
                assert page.admin_unlocked
                clock[0] += 1
                page._check_admin_idle()
                assert not page.admin_unlocked
                assert not picker.value
                assert page.tabs.value == "daily"
                page._record_admin_activity()
                assert not page.admin_unlocked
                page.save_planned_jobs()
                save_jobs.assert_called_once()
                assert "10 minutách" in page.status_label.text
                with patch.object(page, "test_connection", new_callable=AsyncMock) as probe:
                    assert not await page._test_admin_connection()
                    await page._verify_database_setup()
                    probe.assert_not_awaited()
                # Login is the only way back in, with a fresh deadline.
                page.admin_password_input.value = "secret"
                page.confirm_admin()
                assert page.admin_unlocked
                clock[0] += 500
                page._record_admin_activity()
                clock[0] += 500
                page._check_admin_idle()
                assert page.admin_unlocked
                page.tabs.value = "mail_tasks"
                page.lock_admin()
                assert page.tabs.value == "mail_tasks"
                assert not page.admin_unlocked
