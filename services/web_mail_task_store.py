"""Persistent configuration for independent web mail tasks.

Saved separately from legacy planovac.json to avoid changing the Qt scheduler.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Sequence

from services.web_mail_tasks import MailTask


def task_file(config_directory: Path) -> Path:
    return Path(config_directory) / "web_mail_tasks.json"


def load_tasks(path: Path) -> list[MailTask]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise ValueError("Konfigurace musí obsahovat pole 'tasks'.")
    tasks = [MailTask.from_dict(row) for row in data["tasks"]]
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicitní ID e-mailové úlohy.")
    return tasks


def save_tasks(path: Path, tasks: Sequence[MailTask]) -> None:
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicitní ID e-mailové úlohy.")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"version": 1, "tasks": [task.to_dict() for task in tasks]},
        ensure_ascii=False, indent=2,
    ) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
