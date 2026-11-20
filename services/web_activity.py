"""Bounded, persistent worker activity shared with the GUI (no mail credentials)."""
from contextlib import closing
from datetime import datetime
from pathlib import Path
import logging
import re
import sqlite3

LOG = logging.getLogger(__name__)
ACTIVITY_SCHEMA = 1
CREATE_EVENTS = ('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, time TEXT, '
                 'kind TEXT, task_id TEXT, task_name TEXT, message TEXT, report_date TEXT)')


def _migrate(db):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == ACTIVITY_SCHEMA:
        return
    db.execute('BEGIN IMMEDIATE')
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == ACTIVITY_SCHEMA:
        return
    if version != 0:
        raise sqlite3.OperationalError(f'Nepodporovaná verze databáze historie ({version}).')
    db.execute(CREATE_EVENTS)
    # v0 was the same unversioned table. Validate an existing table before
    # marking it v1, without rewriting rows or preventing an older GUI rollback.
    db.execute('SELECT id,time,kind,task_id,task_name,message,report_date FROM events LIMIT 0')
    db.execute('PRAGMA user_version = 1')


def migrate_activity(directory):
    path = Path(directory) / 'logy/activity.sqlite3'
    if path.is_file():
        with closing(sqlite3.connect(path, timeout=5)) as db, db:
            _migrate(db)


def friendly_error(error):
    text = str(error)
    if text.startswith(("V Jídelně chybí kalendář", "V Jídelně má kalendář", "V Jídelně je pro")):
        return text
    missing = re.search(r"Pro (\d+/\d+) neexistuje v public\.varnedny kalendář typu služby '([^']+)'", text)
    if missing:
        month, meal = missing.groups()
        return f"V Jídelně chybí kalendář {meal} pro {month}. Doplňte jej nebo zvolte existující kalendář."
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
            _migrate(db)
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

