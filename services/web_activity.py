"""Bounded, persistent worker activity shared with the GUI (no mail credentials)."""
from contextlib import closing
from datetime import datetime
from pathlib import Path
import logging
import re
import sqlite3

LOG = logging.getLogger(__name__)


def friendly_error(error):
    text = str(error)
    calendar = re.search(r"Kalendář varnedny pro (\d+/\d+) a typ služby '([^']+)' má (\d+) záznamů", text)
    if calendar:
        month, meal, count = calendar.groups()
        return (f"Chybí kalendář varných dnů {meal} pro {month}. Doplňte jej v Jídelně."
                if count == '0' else f"Kalendář {meal} pro {month} je duplicitní. Zkontrolujte jej v Jídelně.")
    if 'povolena' in text or 'povoleny' in text:
        return 'Kategorie přehledu již nejsou povoleny. Zkontrolujte přehled a oprávnění.'
    if 'přehled' in text.casefold() and 'neexistuje' in text:
        return 'Uložený přehled chybí. Vyberte jej znovu v úloze.'
    if any(word in text.casefold() for word in ('password', 'heslo', 'authentication', 'credential')):
        return 'Přihlášení se nezdařilo. Zkontrolujte přístupové údaje v nastavení.'
    return 'Úlohu se nepodařilo dokončit. Podrobnosti jsou v technickém logu workeru.'


def record_event(directory, kind, message, *, task_id=None, task_name='', report_date=None):
    """Diagnostics must never change delivery/retry behaviour."""
    try:
        folder = Path(directory) / 'logy'
        folder.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(folder / 'activity.sqlite3', timeout=5)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, time TEXT, kind TEXT, task_id TEXT, task_name TEXT, message TEXT, report_date TEXT)')
            db.execute('INSERT INTO events(time,kind,task_id,task_name,message,report_date) VALUES(?,?,?,?,?,?)',
                       (datetime.now().isoformat(timespec='seconds'), kind, task_id, task_name, message,
                        report_date.isoformat() if report_date else None))
            db.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 2000)')
    except (OSError, sqlite3.Error):
        LOG.exception('Cannot save worker activity')


def read_events(directory, limit=200):
    path = Path(directory) / 'logy/activity.sqlite3'
    if not path.exists():
        return []
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT ?', (min(max(limit, 1), 2000),))]


def activity_rows(directory):
    try:
        return read_events(directory, 2000)
    except (OSError, sqlite3.Error):
        return []
