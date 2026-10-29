"""Observed worker state; an enabled task alone never proves it is running."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path


def write_runtime(directory, *, phase="waiting", task_id=None):
    path = Path(directory) / "web_mail_worker_runtime.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".worker-runtime-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"heartbeat": datetime.now().isoformat(), "phase": phase,
                       "task_id": task_id}, stream)
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def observed_status(directory, task=None, *, now=None):
    if task is not None and not task.enabled:
        return "Pozastaveno"
    try:
        raw = json.loads((Path(directory) / "web_mail_worker_runtime.json").read_text(encoding="utf-8"))
        heartbeat = datetime.fromisoformat(raw["heartbeat"])
        age = (now or datetime.now()) - heartbeat
        if not timedelta(seconds=-5) <= age <= timedelta(seconds=90):
            return "Běh plánovače není potvrzen"
        if raw["phase"] == "stopped":
            return "Plánovač je zastaven"
        if raw["phase"] == "running" and task is not None and raw.get("task_id") == task.id:
            return "Právě zpracovává přehled"
        if raw["phase"] in ("running", "waiting"):
            return "Plánovač běží · čeká na další spuštění"
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return "Běh plánovače není potvrzen"
