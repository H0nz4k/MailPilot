"""Export a saved report once, without opening the web UI or sending email."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from hashlib import sha256
import os
from pathlib import Path
import sys
import tempfile

from automaticky_export import read_saved_settings, write_log
from services.config_io import open_document
from services.web_activity import record_event
from services.web_daily_profiles import DailyProfile, apply_profile, load_profiles, profile_file
from services.web_report_output import _slug
from stravovaci_sestava import load_config, fetch_report, create_pdf


def select_saved_report(directory: Path, *, name: str | None = None,
                        profile_id: str | None = None) -> DailyProfile:
    if bool(name) == bool(profile_id):
        raise ValueError('Vyberte přehled buď názvem, nebo jeho ID.')
    profiles = load_profiles(profile_file(directory))
    matches = [profile for profile in profiles if (
        profile.id == profile_id if profile_id else profile.name.casefold() == str(name).strip().casefold()
    )]
    if not matches:
        raise ValueError(f'Uložený přehled „{name or profile_id}“ nebyl nalezen. Nejprve jej uložte v Přehledech.')
    if len(matches) != 1:
        ids = ', '.join(profile.id for profile in matches)
        raise ValueError(f'Název „{name}“ má více přehledů. Přejmenujte je nebo použijte --export-report-id. ID: {ids}')
    return matches[0]


def export_date(value: str | None = None, days_ahead: int | None = None) -> date:
    if value is not None and days_ahead is not None:
        raise ValueError('Zvolte jen --date, nebo --days-ahead.')
    if days_ahead is not None:
        if isinstance(days_ahead, bool) or not isinstance(days_ahead, int) or not 0 <= days_ahead <= 370:
            raise ValueError('Počet dní dopředu musí být celé číslo od 0 do 370.')
        return date.today() + timedelta(days=days_ahead)
    if value is None:
        return date.today()
    for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
        try:
            parsed = datetime.strptime(value, fmt).date()
        except ValueError:
            continue
        if parsed.strftime(fmt) == value:
            return parsed
    raise ValueError('Datum musí být platné a ve formátu RRRR-MM-DD nebo DD.MM.RRRR.')


def export_saved_report(config_path: Path, *, name: str | None = None,
                        profile_id: str | None = None, report_date: date | None = None,
                        output: Path | None = None) -> Path:
    config_path = Path(config_path).resolve()
    profile = select_saved_report(config_path.parent, name=name, profile_id=profile_id)
    day = report_date or date.today()
    # Ignore the preview date left in config.json. Apply current admin category
    # permissions and the saved PDF options exactly as the scheduler does.
    raw = read_saved_settings(config_path)
    config = apply_profile(load_config(config_path, date_override=day.strftime('%d.%m.%Y')), profile, raw)
    if output is None:
        signature = sha256(profile.id.encode('utf-8')).hexdigest()[:8]
        output = Path('exporty') / f'{_slug(profile.name)[:64]}_{day.isoformat()}_{signature}.pdf'
    target = Path(output)
    if not target.is_absolute():
        target = config_path.parent / target
    target = target.resolve()
    if target.suffix.casefold() != '.pdf':
        raise ValueError('Výstupní soubor musí mít příponu .pdf.')
    config = replace(config, pdf_output=target)
    report = fetch_report(config)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.dataship-export-', suffix='.pdf', delete=False) as stream:
            temporary = Path(stream.name)
        create_pdf(config, report, output_path=temporary)
        if temporary.stat().st_size == 0:
            raise ValueError('Vytvořené PDF je prázdné; původní soubor zůstal zachovaný.')
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    record_event(config_path.parent, 'exported', f'Ruční export uloženého přehledu: {target}',
                 task_name=profile.name, report_date=day)
    return target


def run_saved_report_export(args) -> int:
    def log(level: str, message: str):
        print(message, file=sys.stderr if level == 'ERROR' else sys.stdout, flush=True)
        try:
            write_log(args.log, level, message)
        except OSError:
            pass  # Logging cannot invalidate a successfully created PDF.
    try:
        day = export_date(args.report_date, args.days_ahead)
        path = export_saved_report(args.config, name=args.export_report,
                                   profile_id=args.export_report_id, report_date=day,
                                   output=args.export_output)
    except Exception as exc:
        message = f'Export uloženého přehledu selhal: {exc}'
        log('ERROR', message)
        record_event(Path(args.config).resolve().parent, 'error', message)
        return 2
    log('INFO', f'PDF uloženo: {path}')
    if args.open_pdf:
        try:
            open_document(path)
        except Exception as exc:
            log('ERROR', f'PDF je uložené v {path}, ale nepodařilo se otevřít: {exc}')
            return 3
    return 0
