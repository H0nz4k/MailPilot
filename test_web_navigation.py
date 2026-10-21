"""Default and admin-selected top tab visibility."""
from services.web_navigation import DEFAULT_VISIBLE_TABS, EDITABLE_TABS, visible_tabs


def test_default_top_tabs():
    assert visible_tabs({}) == {
        "daily": True, "closing": True, "special": False,
        "bulk": False, "mail_tasks": True,
    }
    assert set(EDITABLE_TABS) == {"closing", "special", "bulk", "mail_tasks"}


def test_admin_can_enable_and_hide_extra_sections():
    assert visible_tabs({
        "ui_visible_tabs": {
            "closing": False, "special": True, "bulk": True, "mail_tasks": False,
        }
    }) == {
        "daily": True, "closing": False, "special": True,
        "bulk": True, "mail_tasks": False,
    }


def test_daily_cannot_be_hidden_and_invalid_values_are_ignored():
    visible = visible_tabs({"ui_visible_tabs": {"daily": False, "bulk": "false"}})
    assert visible["daily"]
    assert visible["bulk"] is False
    assert visible_tabs({"ui_visible_tabs": []}) == DEFAULT_VISIBLE_TABS
