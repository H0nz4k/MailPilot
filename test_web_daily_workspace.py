"""Exercise saved filters in a real NiceGUI page without a DB or email delivery."""
import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from nicegui.testing.user_simulation import user_simulation

from services.web_daily_profiles import load_profiles, profile_file
from stravovaci_nicegui import NiceGuiApp


@pytest.mark.asyncio
async def test_saved_profiles_switch_and_summary_uses_current_filters(tmp_path):
    config = tmp_path / "config.json"
    shutil.copyfile(Path(__file__).with_name("config.example.json"), config)
    pages = []

    def root():
        page = NiceGuiApp(config)
        page.build()
        pages.append(page)

    def report(_self, config):
        categories = config.categories
        assert config.database["password"] == "test-only"
        assert not config.show_diner_list
        return SimpleNamespace(
            menus=[SimpleNamespace(portions=len(categories) * 10)],
            categories=[SimpleNamespace(code=c, name=f"Kategorie {c}", applications=10)
                        for c in categories],
        )

    with patch.object(NiceGuiApp, "_stored_password", return_value=""), \
         patch.object(NiceGuiApp, "_stored_api_key", return_value=""), \
         patch.object(NiceGuiApp, "_fetch_daily_summary", report), \
         patch.object(NiceGuiApp, "_send_mail_worker") as send:
        async with user_simulation(root) as user:
            await user.open("/")
            await user.should_see("Co zobrazit")
            with user:
                page = pages[0]
                assert not page.daily_summary_dialog.value
                assert not page.daily_pdf_settings_dialog.value
                assert page.daily_summary_detail_button.text == "Detail porcí"
                assert page.daily_pdf_settings_button.text == "Nastavení PDF"
                page.connection_ok = True
                page._connection_password = "test-only"
                page.populate_categories([(str(c), f"Kategorie {c}") for c in range(1, 7)])
                assert page.daily_category_button.text == "Kategorie (6)"
                page.daily_profile_name.value = "Školní"
                page._apply_daily_categories(["1", "2"])
                assert page.save_daily_profile()
                first = page.daily_profiles[0]
                page.new_daily_profile()
                page.daily_profile_name.value = "Ostatní"
                page._apply_daily_categories(["3", "4", "5", "6"])
                assert page.save_daily_profile()
                second = page.daily_profiles[1]
                page._choose_daily_profile(first)
                assert page.selected_categories == {"1", "2"}
                await page.refresh_daily_summary()
                assert page.daily_summary_total.text == "20"
                page._choose_daily_profile(second)
                assert page.selected_categories == {"3", "4", "5", "6"}
                await page.refresh_daily_summary()
                assert page.daily_summary_total.text == "40"
                # Editing then clicking the current profile must not restore an old object.
                page.daily_profile_name.value = "Ostatní upravený"
                page._choose_daily_profile(second)
                assert page.daily_profile_name.value == "Ostatní upravený"
                # A database retest must retain the profile instead of selecting all six.
                page.populate_categories([(str(c), f"Kategorie {c}") for c in range(1, 7)])
                assert page.selected_categories == {"3", "4", "5", "6"}
                page._daily_summary_timer.deactivate()
            stored = load_profiles(profile_file(tmp_path))
            assert [p.categories for p in stored] == [("1", "2"), ("3", "4", "5", "6")]
            send.assert_not_called()


@pytest.mark.asyncio
async def test_old_summary_is_discarded_after_filter_change(tmp_path):
    """A slower old DB response must not replace the newly selected profile."""
    config = tmp_path / "config.json"
    shutil.copyfile(Path(__file__).with_name("config.example.json"), config)
    pages = []

    def root():
        page = NiceGuiApp(config)
        page.build()
        pages.append(page)

    started = asyncio.Event()
    release = asyncio.Event()

    async def io_bound(*_args):
        started.set()
        await release.wait()
        return SimpleNamespace(menus=[SimpleNamespace(portions=999)], categories=[])

    with patch.object(NiceGuiApp, "_stored_password", return_value=""), \
         patch.object(NiceGuiApp, "_stored_api_key", return_value=""):
        async with user_simulation(root) as user:
            await user.open("/")
            with user:
                page = pages[0]
                page.connection_ok = True
                page._connection_password = "test-only"
                page.populate_categories([("1", "První"), ("2", "Druhá")])
                with patch("services.web_daily_design.run.io_bound", io_bound):
                    pending = asyncio.create_task(page.refresh_daily_summary())
                    await started.wait()
                    page._apply_daily_categories(["2"])
                    page._daily_summary_timer.deactivate()
                    release.set()
                    await pending
                assert page.daily_summary_total.text == "—"

