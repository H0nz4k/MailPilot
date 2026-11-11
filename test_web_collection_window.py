import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

import pytest
from nicegui.testing.user_simulation import user_simulation

from services.web_mail_task_store import task_file
from stravovaci_nicegui import NiceGuiApp


@pytest.mark.asyncio
async def test_one_off_collection_creates_pdf_and_sends_without_task(tmp_path):
    config_path = tmp_path / "config.json"
    shutil.copyfile(Path(__file__).with_name("config.example.json"), config_path)
    pages = []
    def root():
        page = NiceGuiApp(config_path)
        page.build()
        page.populate_categories([("1", "Žáci")])
        pages.append(page)
    async def direct(func, *args, **kwargs):
        return func(*args, **kwargs)
    settings = {"transport": "smtp", "subject_template": "{report}: {date}", "body_template": "{date}"}
    with patch.object(NiceGuiApp, "_stored_password", return_value=""), \
         patch.object(NiceGuiApp, "_stored_api_key", return_value=""), \
         patch.object(NiceGuiApp, "_schedule_first_run"), \
         patch.object(NiceGuiApp, "_confirm_send", new_callable=AsyncMock, return_value=True), \
         patch.object(NiceGuiApp, "_outgoing_mail_settings", return_value=settings), \
         patch("services.web_collection_window.run.io_bound", direct), \
         patch("services.web_collection_window.fetch_report", return_value=SimpleNamespace()) as fetch, \
         patch("services.web_collection_window.create_pdf", side_effect=lambda c, r: c.pdf_output) as create, \
         patch("services.web_collection_window.open_document"), \
         patch("services.web_mail_smtp.smtp_send") as smtp:
        async with user_simulation(root) as user:
            await user.open("/")
            with user:
                page = pages[0]
                page.connection_ok = True
                page._connection_password = "test-only"
                page.tabs.value = "collections"
            await user.should_see("Období a obsah")
            user.find(marker="collection-create").click()
            await user.should_see("PDF vytvořeno:")
            assert fetch.call_args.args[0].report_end_date is not None
            assert create.called
            assert not task_file(tmp_path).exists()
            # Enter an address through the same recipient editor used by the page.
            from nicegui import ui
            with user:
                inputs = [e for e in user.client.elements.values() if isinstance(e, ui.input)
                          and e.props.get("aria-label") == "E-mail příjemce"]
                inputs[-1].value = "test@example.org"
            user.find(marker="collection-send").click()
            await user.should_see("Odesláno 1 příjemcům")
            smtp.assert_called_once()
            assert not task_file(tmp_path).exists()
