"""Recipient edits stay visible, reject invalid input and preserve prior addresses."""
import pytest
from nicegui.testing.user_simulation import user_simulation

from services.web_recipient_editor import RecipientEditor


@pytest.mark.asyncio
async def test_add_paste_duplicate_error_and_removal():
    editors = []

    def root():
        editors.append(RecipientEditor(["original@example.cz"]))

    async with user_simulation(root) as user:
        await user.open("/")
        editor = editors[0]
        with user:
            editor.input.value = "broken@"
        user.find("Přidat").click()
        assert editor.addresses == ["original@example.cz"]
        assert editor.input.value == "broken@"
        assert editor.input.props["error"]
        await user.should_see("Adresa nebyla přidána.")
        with user:
            editor.input.value = "new@example.cz, OTHER@example.cz; new@example.cz;"
        user.find("Přidat").click()
        assert editor.addresses == ["original@example.cz", "new@example.cz", "OTHER@example.cz"]
        assert not editor.input.value
        assert not editor.input.props.get("error")
        await user.should_see("new@example.cz")
        with user:
            editor.input.value = "NEW@example.cz"
            assert editor.commit_pending()
            assert len(editor.addresses) == 3
            editor.remove("new@example.cz")
        assert editor.addresses == ["original@example.cz", "OTHER@example.cz"]
        await user.should_see("Příjemce odebrán.")
