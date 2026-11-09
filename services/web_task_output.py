"""Shared email/PDF-only destination controls for the wizard and task editor."""
from pathlib import Path
from nicegui import run, ui

from services.web_path_picker import pick_local_directory
from services.web_recipient_editor import RecipientEditor


class TaskOutputEditor:
    def __init__(self, directory: Path, task=None):
        self.default_directory = str(Path(directory).resolve() / "Exporty")
        self.pdf_only = ui.checkbox(
            "Pouze exportovat a uložit PDF", value=bool(task and task.output_mode == "pdf"),
        ).classes("ds-output-choice").mark("task-pdf-only")
        with ui.column().classes("w-full gap-3") as self.mail_fields:
            self.recipients = RecipientEditor(task.recipients if task else (), directory=Path(directory))
        with ui.column().classes("w-full gap-3 ds-output-fields") as self.pdf_fields:
            with ui.row().classes("w-full ds-output-path items-center no-wrap"):
                self.directory = ui.input(
                    "Kam uložit PDF", value=(task.output_directory if task else None) or self.default_directory,
                ).props("outlined").classes("grow min-w-0").mark("task-output-directory")
                ui.button("Procházet…", icon="folder_open", on_click=self.browse).props("outline no-caps").mark("browse-export-directory")
            self.filename = ui.input(
                "Název souboru", value=task.output_filename if task else "Prehled_{date}.pdf",
            ).props("outlined").classes("w-full").mark("task-output-filename")
            ui.label("{date} se nahradí datem přehledu ve tvaru RRRR-MM-DD. Stejný název souboru se při dalším spuštění přepíše.").classes("ui-help")
        self.mail_fields.bind_visibility_from(self.pdf_only, "value", backward=lambda value: not value)
        self.pdf_fields.bind_visibility_from(self.pdf_only, "value")

    async def browse(self):
        try:
            chosen = await run.io_bound(pick_local_directory, str(self.directory.value or self.default_directory))
            if chosen:
                self.directory.value = chosen
        except (OSError, ValueError) as exc:
            ui.notify(str(exc), type="negative")

    def values(self, *, preview=False):
        return {
            "output_mode": "pdf" if self.pdf_only.value else "email",
            "output_directory": self.default_directory if preview else self.directory.value,
            "output_filename": "Prehled_{date}.pdf" if preview else self.filename.value,
        }

    def commit(self):
        return self.pdf_only.value or self.recipients.commit_pending()
