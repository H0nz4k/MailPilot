"""Admin-configurable visibility of MailPilot Web's top-level tabs.

This is presentation configuration, NOT a substitute for access controls.
The Administration entry cannot be disabled.
"""
from __future__ import annotations

from collections.abc import Mapping

DEFAULT_VISIBLE_TABS: dict[str, bool] = {
    "daily": True,
    "closing": True,
    "special": False,
    "bulk": False,
    "mail_tasks": True,
}
EDITABLE_TABS: dict[str, str] = {
    "closing": "Uzávěrka",
    "special": "Speciál",
    "bulk": "Hromadná zpráva",
    "mail_tasks": "E-mailové úlohy",
}


def visible_tabs(config: Mapping[str, object]) -> dict[str, bool]:
    """Safe defaults for old/invalid configs. Daily and admin stay accessible."""
    stored = config.get("ui_visible_tabs")
    if not isinstance(stored, dict):
        stored = {}
    visibility: dict[str, bool] = {"daily": True}
    for tab, default in DEFAULT_VISIBLE_TABS.items():
        if tab == "daily":
            continue
        value = stored.get(tab, default)
        visibility[tab] = value if isinstance(value, bool) else default
    return visibility
