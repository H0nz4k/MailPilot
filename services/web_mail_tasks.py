"""Independent email-task definitions for the NiceGUI scheduler.

This module deliberately has no GUI or Windows dependencies.  The service,
WebGUI and tests can share the same validation and date calculations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path, PureWindowsPath
from string import Formatter
from typing import Callable, Literal
from uuid import uuid4

DateMode = Literal["today", "tomorrow", "offset", "next_cooking_day", "fixed"]
ReportType = Literal["daily", "meal_summary"]
MAX_LOOKAHEAD_DAYS = 370


def validate_pdf_destination(directory: object, filename: object) -> tuple[str, str]:
    folder = str(directory or "").strip()
    if not folder or not (Path(folder).is_absolute() or PureWindowsPath(folder).is_absolute()):
        raise ValueError("Zadejte úplnou cestu ke složce pro PDF.")
    if any(ord(char) < 32 for char in folder):
        raise ValueError("Cesta ke složce obsahuje neplatné znaky.")
    template = str(filename or "").strip()
    try:
        if any(field not in (None, "date") or spec or conversion
               for _literal, field, spec, conversion in Formatter().parse(template)):
            raise ValueError()
        sample = template.format(date="2026-10-29")
    except (KeyError, ValueError, IndexError, AttributeError) as exc:
        raise ValueError("Název PDF může obsahovat pouze proměnnou {date}.") from exc
    if (not sample.lower().endswith(".pdf") or sample in (".pdf", "..pdf")
            or any(char in sample for char in '<>:"/\\|?*')
            or any(ord(char) < 32 for char in sample)
            or "{" in sample or "}" in sample):
        raise ValueError("Zadejte název souboru s příponou .pdf, bez cesty a speciálních znaků.")
    stem = sample.split(".")[0].rstrip(" .").upper()
    if stem in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raise ValueError("Tento název souboru je ve Windows vyhrazený.")
    return folder, template


@dataclass(frozen=True)
class MailTask:
    id: str
    name: str
    recipients: tuple[str, ...]
    report: ReportType
    send_time: str
    date_mode: DateMode
    day_offset: int = 0
    fixed_date: str | None = None
    enabled: bool = True
    profile_id: str | None = None
    cooking_meal_type: str | tuple[str, ...] | None = None
    only_cooking_days: bool = False
    first_send_date: str | None = None
    output_mode: Literal["email", "pdf"] = "email"
    output_directory: str | None = None
    output_filename: str = "Prehled_{date}.pdf"

    @classmethod
    def from_dict(cls, raw: dict) -> "MailTask":
        from mail_service import normalize_recipients

        if not isinstance(raw, dict):
            raise ValueError("Úloha musí být objekt.")
        name = str(raw.get("name", "")).strip()
        if not name:
            raise ValueError("Chybí název úlohy.")
        output_mode = raw.get("output_mode", "email")
        if output_mode not in ("email", "pdf"):
            raise ValueError("Neznámý způsob výstupu úlohy.")
        output_directory, output_filename = None, "Prehled_{date}.pdf"
        if output_mode == "pdf":
            output_directory, output_filename = validate_pdf_destination(
                raw.get("output_directory"), raw.get("output_filename", output_filename),
            )
        recipients = () if output_mode == "pdf" else tuple(normalize_recipients(raw.get("recipients", [])))
        if output_mode == "email" and not recipients:
            raise ValueError("Úloha musí mít alespoň jednoho příjemce.")
        report = str(raw.get("report", "daily"))
        if report not in ("daily", "meal_summary"):
            raise ValueError("Neznámý typ sestavy.")
        send_time = str(raw.get("send_time", "")).strip()
        try:
            hour, minute = send_time.split(":")
            if len(hour) != 2 or len(minute) != 2:
                raise ValueError()
            h, m = int(hour), int(minute)
            if not 0 <= h < 24 or not 0 <= m < 60:
                raise ValueError()
        except ValueError as exc:
            raise ValueError("Čas odeslání musí být HH:MM.") from exc
        mode = str(raw.get("date_mode", "today"))
        if mode not in ("today", "tomorrow", "offset", "next_cooking_day", "fixed"):
            raise ValueError("Neznámé pravidlo data.")
        try:
            offset = int(raw.get("day_offset", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("Neplatný posun dne.") from exc
        if not -MAX_LOOKAHEAD_DAYS <= offset <= MAX_LOOKAHEAD_DAYS:
            raise ValueError("Posun dne je mimo povolený rozsah.")
        fixed = raw.get("fixed_date") or None
        first_send_date = raw.get("first_send_date") or None
        if first_send_date is not None:
            try:
                date.fromisoformat(first_send_date)
            except (ValueError, TypeError) as exc:
                raise ValueError("Neplatný první den odeslání.") from exc
        if mode == "fixed":
            try:
                date.fromisoformat(str(fixed))
            except ValueError as exc:
                raise ValueError("Konkrétní datum musí být YYYY-MM-DD.") from exc
        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("enabled musí být true nebo false.")
        only_cooking_days = raw.get("only_cooking_days", False)
        if not isinstance(only_cooking_days, bool):
            raise ValueError("only_cooking_days musí být true nebo false.")
        profile_id = raw.get("profile_id") or None
        if profile_id is not None and (not isinstance(profile_id, str) or not profile_id.strip()):
            raise ValueError("Neplatné ID denního přehledu.")
        if profile_id and report != "daily":
            raise ValueError("Uložený přehled lze přiřadit pouze k Dennímu stavu.")
        cooking_meal_type = raw.get("cooking_meal_type")
        if isinstance(cooking_meal_type, (list, tuple)):
            if not cooking_meal_type or any(
                not isinstance(v, str) or not v.strip() or v.strip() == "*"
                for v in cooking_meal_type
            ):
                raise ValueError("Kalendář musí obsahovat alespoň jeden skutečný typ služby.")
            cooking_meal_type = tuple(
                dict.fromkeys(v.strip() for v in cooking_meal_type)
            )
        elif cooking_meal_type is not None:
            if not isinstance(cooking_meal_type, str) or not cooking_meal_type.strip():
                raise ValueError("Kalendář varných dnů musí být název typu služby.")
            cooking_meal_type = cooking_meal_type.strip()
        return cls(
            id=str(raw.get("id") or uuid4()), name=name, recipients=recipients,
            report=report, send_time=send_time, date_mode=mode,
            day_offset=offset, fixed_date=str(fixed) if fixed else None,
            enabled=enabled, profile_id=profile_id,
            cooking_meal_type=cooking_meal_type, only_cooking_days=only_cooking_days,
            first_send_date=first_send_date,
            output_mode=output_mode, output_directory=output_directory,
            output_filename=output_filename,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "recipients": list(self.recipients),
            "report": self.report, "send_time": self.send_time,
            "date_mode": self.date_mode, "day_offset": self.day_offset,
            "fixed_date": self.fixed_date, "enabled": self.enabled,
            "profile_id": self.profile_id,
            "cooking_meal_type": list(self.cooking_meal_type)
            if isinstance(self.cooking_meal_type, tuple) else self.cooking_meal_type,
            "only_cooking_days": self.only_cooking_days,
            "first_send_date": self.first_send_date,
            "output_mode": self.output_mode, "output_directory": self.output_directory,
            "output_filename": self.output_filename,
        }


def target_date(
    task: MailTask,
    sent_on: date,
    *,
    is_cooking_day: Callable[[date], bool] | None = None,
) -> date:
    """Resolve report date on the day the task executes.

    The cooking-day callback MUST read JídelnaSQL's varnedny calendar.
    Do not substitute weekday heuristics: holidays and weekend cooking vary.
    """
    if task.date_mode == "today":
        return sent_on
    if task.date_mode == "tomorrow":
        return sent_on + timedelta(days=1)
    if task.date_mode == "offset":
        return sent_on + timedelta(days=task.day_offset)
    if task.date_mode == "fixed":
        assert task.fixed_date is not None
        return date.fromisoformat(task.fixed_date)
    if is_cooking_day is None:
        raise ValueError("Pro následující varný den je nutný kalendář varnedny.")
    for days in range(1, MAX_LOOKAHEAD_DAYS + 1):
        candidate = sent_on + timedelta(days=days)
        if is_cooking_day(candidate):
            return candidate
    raise ValueError("V kalendáři nebyl nalezen následující varný den.")


def next_send_at(task: MailTask, now: datetime) -> datetime | None:
    """Daily local-wall-clock schedule; the service handles restarts and dedupe."""
    if not task.enabled:
        return None
    hour, minute = map(int, task.send_time.split(":"))
    result = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if result <= now:
        result += timedelta(days=1)
    if task.first_send_date and result.date() < date.fromisoformat(task.first_send_date):
        result = datetime.combine(date.fromisoformat(task.first_send_date), result.timetz())
    return result



