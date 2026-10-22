"""Custom colors survive restart and cannot inject CSS or mutate built-in themes."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest
from nicegui.testing.user_simulation import user_simulation

from services.web_custom_palette import DEFAULT_CUSTOM_PALETTE, hex_color, contrast
from stravovaci_nicegui import NiceGuiApp
from ui_theme import (
    UI_THEMES, appearance_config, appearance_css_vars, appearance_theme,
    appearance_html_classes, peek_ui_appearance,
)


@pytest.mark.parametrize("value", [None, "red", "#1234", "#abcdef; color:red", "url(example)"])
def test_invalid_color_is_not_inserted_into_css(value):
    assert hex_color(value) is None
    variables = appearance_css_vars({"schema": "vlastni", "vlastni_barvy": {"primary": value}})
    assert variables["--app-primary"] == DEFAULT_CUSTOM_PALETTE["primary"]


def test_roundtrip_dark_mode_and_button_text_contrast():
    original = deepcopy(UI_THEMES)
    palette = {**DEFAULT_CUSTOM_PALETTE, "primary": "#ffff00", "page": "#101010",
               "surface": "#222222", "text": "#ffffff", "muted": "#bbbbbb"}
    appearance = peek_ui_appearance({"ui_barevne_schema": "vlastni", "ui_vlastni_barvy": palette})
    restored = peek_ui_appearance(appearance_config(appearance))
    assert restored == appearance
    assert appearance_theme(restored)["dark"]
    variables = appearance_css_vars(restored)
    assert variables["--app-primary"] == "#ffff00"
    assert variables["--app-surface"] == "#222222"
    assert variables["--custom-on-primary"] == "#000000"
    assert contrast(variables["--custom-on-primary"], "#ffff00") >= 4.5
    assert "theme-vlastni" in appearance_html_classes(restored)
    assert UI_THEMES == original
    assert hex_color(" #AbC ") == "#aabbcc"


@pytest.mark.asyncio
async def test_editor_updates_saves_retains_and_resets_colors(tmp_path):
    config = tmp_path / "config.json"
    shutil.copyfile(Path(__file__).with_name("config.example.json"), config)
    pages = []

    def root():
        page = NiceGuiApp(config)
        page.build()
        page.admin_unlocked = True
        page._apply_admin_visibility()
        page.tabs.value = "admin"
        page.admin_sections.value = "appearance"
        pages.append(page)

    with patch.object(NiceGuiApp, "_stored_password", return_value=""), \
         patch.object(NiceGuiApp, "_stored_api_key", return_value=""):
        async with user_simulation(root) as user:
            await user.open("/")
            page = pages[0]
            assert not page.ui_palette_panel.visible
            user.find("Upravit vlastní barvy").click()
            assert page.ui_palette_panel.visible
            with user:
                page.ui_custom_colors["primary"].value = "#facc15"
                page.ui_custom_colors["page"].value = "#111111"
            saved = json.loads(config.read_text(encoding="utf-8"))
            assert saved["ui_barevne_schema"] == "vlastni"
            assert saved["ui_vlastni_barvy"]["primary"] == "#facc15"
            assert appearance_theme(peek_ui_appearance(saved))["dark"]
            with user:
                page.ui_custom_colors["primary"].value = "not-a-color"
            assert page.ui_custom_colors["primary"].props["error"]
            assert json.loads(config.read_text(encoding="utf-8"))["ui_vlastni_barvy"]["primary"] == "#facc15"
            with user:
                page.ui_theme.value = "svetle"
                page.save_ui_appearance()
            assert not page.ui_palette_panel.visible
            assert json.loads(config.read_text(encoding="utf-8"))["ui_vlastni_barvy"]["primary"] == "#facc15"
            user.find("Upravit vlastní barvy").click()
            user.find("Obnovit výchozí barvy").click()
            assert json.loads(config.read_text(encoding="utf-8"))["ui_vlastni_barvy"] == DEFAULT_CUSTOM_PALETTE
            assert not page.ui_custom_colors["primary"].props.get("error")
