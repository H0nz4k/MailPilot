"""Drain GUI report and delivery work before restarting the application."""
from __future__ import annotations

import asyncio

from nicegui import run

_active: set[asyncio.Task] = set()
_paused = False


async def run_report_job(callback, *args, **kwargs):
    if _paused:
        raise RuntimeError('Probíhá aktualizace DataShipu. Nové přehledy jsou dočasně pozastavené.')
    job = asyncio.create_task(run.io_bound(callback, *args, **kwargs))
    _active.add(job)
    job.add_done_callback(_active.discard)
    return await asyncio.shield(job)


async def pause_report_jobs() -> bool:
    global _paused
    if _paused:
        return False
    _paused = True
    try:
        await asyncio.gather(*(asyncio.shield(job) for job in _active), return_exceptions=True)
    except BaseException:
        resume_report_jobs()
        raise
    return True


def resume_report_jobs() -> None:
    global _paused
    _paused = False
