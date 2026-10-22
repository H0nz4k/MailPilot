"""Manual closing cannot send mail or change the scheduler's delivery flag."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from nicegui.testing.user_simulation import user_simulation

from services.web_closing_design import export_closing_preview
from stravovaci_nicegui import NiceGuiApp


@pytest.mark.parametrize("fail", [False, True])
def test_preview_disables_mail_in_snapshot_and_cleans_it_up(tmp_path, fail):
    config = tmp_path / "config.json"
    original = {"uzaverka": {"odeslat_mail": True, "prilohy": "zip"}, "other": 123}
    config.write_text(json.dumps(original), encoding="utf-8")
    seen = []

    def closing(snapshot, **kwargs):
        seen.append(snapshot)
        assert snapshot.parent == config.parent
        assert json.loads(snapshot.read_text(encoding="utf-8"))["uzaverka"] == {
            "odeslat_mail": False, "prilohy": "zip",
        }
        assert kwargs == {"year": 2026, "month": 10}
        if fail:
            raise RuntimeError("Database unavailable")
        return "ready"

    with patch("services.web_closing_design.run_closing", closing):
        if fail:
            with pytest.raises(RuntimeError):
                export_closing_preview(config, year=2026, month=10)
        else:
            assert export_closing_preview(config, year=2026, month=10) == "ready"
    assert json.loads(config.read_text(encoding="utf-8")) == original
    assert seen and not seen[0].exists()


@pytest.mark.asyncio
async def test_closing_validates_period_and_shows_only_generated_outputs(tmp_path):
    config = tmp_path / "config.json"
    shutil.copyfile(Path(__file__).with_name("config.example.json"), config)
    pages = []

    def root():
        page = NiceGuiApp(config)
        page.build()
        pages.append(page)

    result = SimpleNamespace(files=(tmp_path / "Arch.pdf",), attachments=(tmp_path / "Uzaverka.zip",))
    with patch.object(NiceGuiApp, "_stored_password", return_value=""), \
         patch.object(NiceGuiApp, "_stored_api_key", return_value=""), \
         patch.object(NiceGuiApp, "_schedule_first_run"), \
         patch.object(NiceGuiApp, "_persist_settings", new_callable=AsyncMock), \
         patch("services.web_closing_design.export_closing_preview", return_value=result) as export:
        async with user_simulation(root) as user:
            await user.open("/")
            with user:
                page = pages[0]
                assert not page.closing_results.visible
                await page.generate_closing()
                export.assert_not_called()
                page.connection_ok = True
                page.closing_year.value = None
                await page.generate_closing()
                export.assert_not_called()
                page.closing_year.value = 2026
                page.closing_month.value = 10
                await page.generate_closing()
                assert page.closing_results.visible
                assert page.closing_generate_button.enabled
                export.assert_called_once_with(config, year=2026, month=10)
                page.tabs.value = "closing"
            await user.should_see("Arch.pdf")
            await user.should_see("Uzaverka.zip")
            await user.should_see("Soubory byly vytvořeny. E-mail se neodesílal.")
