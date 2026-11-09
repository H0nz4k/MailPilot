"""Locally remembered recipients for the shared email editor."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from services.web_mail_task_store import load_tasks, task_file


def load_recipient_history(directory: Path) -> list[str]:
    directory = Path(directory)
    try:
        data = json.loads((directory / 'recipient_history.json').read_text(encoding='utf-8'))
        saved = data if isinstance(data, list) else []
    except (OSError, ValueError):
        saved = []
    try:
        saved += [address for task in load_tasks(task_file(directory)) for address in task.recipients]
    except (OSError, ValueError, TypeError):
        pass
    result = {}
    for address in saved:
        if isinstance(address, str) and address.strip():
            result.setdefault(address.casefold(), address)
    return list(result.values())[:200]


def save_recipient_history(directory: Path, addresses: list[str]) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory,
                                         prefix='.recipients-', delete=False) as file:
            temporary = Path(file.name)
            json.dump(addresses[:200], file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, directory / 'recipient_history.json')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
