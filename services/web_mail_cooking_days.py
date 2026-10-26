"""PostgreSQL calendar lookup for scheduled MailPilot reports.

public.varnedny stores one row per (rok, mesic, typsluzby).
The column d01..d31 identifies a day in that month; A means cooking,
N means not cooking. No weekday or public-holiday assumptions are made.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
from services.web_meal_types import meal_filter_values
from datetime import date
from pathlib import Path
from typing import Callable, Iterator, Mapping

from services.web_mail_settings import load_settings, settings_path
from services.web_mail_tasks import MailTask, target_date
from stravovaci_sestava import load_config

DAY_COLUMNS = tuple(f"d{day:02d}" for day in range(1, 32))
CALENDAR_QUERY = (
    f"SELECT {', '.join(DAY_COLUMNS)} FROM public.varnedny "
    "WHERE rok = %s AND mesic = %s "
    "AND LOWER(BTRIM(typsluzby)) = LOWER(%s)"
)

# Legacy generic 'Oběd' is not necessarily a calendar name. In JídelnaSQL
# actual month rows can be Oběd-A, Oběd-B, Oběd MŠ, ObědSZU-A etc.
# Resolve that generic label only if no exact Oběd calendar exists.
# Other named types must never silently expand to neighbouring types.
LUNCH_CALENDAR_QUERY = (
    f"SELECT BTRIM(typsluzby), {', '.join(DAY_COLUMNS)} FROM public.varnedny "
    "WHERE rok = %s AND mesic = %s "
    "AND LOWER(BTRIM(typsluzby)) LIKE LOWER(%s) || '%'"
)


def _calendar_status(value: object, *, day: date, meal_type: str) -> bool:
    status = value.strip().upper() if isinstance(value, str) else ""
    if status not in ("A", "N"):
        raise ValueError(
            f"Neplatný stav varného dne {day:%d.%m.%Y} "
            f"pro {meal_type!r}: {value!r}."
        )
    return status == "A"




@contextmanager
def cooking_day_lookup(
    database: Mapping[str, object],
    meal_type: str,
) -> Iterator[Callable[[date], bool]]:
    """Provide a month-cached checker from the configured JídelnaSQL database.

    Missing/ambiguous calendar rows and unknown status values are errors, not
    guesses. Always close both cursor and connection after date resolution.
    """
    if not isinstance(meal_type, str) or not meal_type.strip():
        raise ValueError("Pro varné dny není nastaven typ služby.")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Chybí psycopg pro načítání varných dnů.") from exc

    with psycopg.connect(**database) as connection:
        with connection.cursor() as cursor:
            # Cache a tuple of (actual calendar name, 31 A/N day flags) rows
            # so the generic Oběd alias can be evaluated as a scoped union.
            cache: dict[tuple[int, int], tuple[tuple[str, tuple[object, ...]], ...]] = {}

            def is_cooking_day(day: date) -> bool:
                key = (day.year, day.month)
                if key not in cache:
                    selected = meal_type.strip()
                    cursor.execute(CALENDAR_QUERY, (day.year, day.month, selected))
                    rows = cursor.fetchall()
                    if len(rows) > 1:
                        raise ValueError(
                            f"Kalendář varnedny pro {day.month:02d}/{day.year} "
                            f"a typ služby {meal_type!r} má {len(rows)} záznamů (očekáván 1)."
                        )
                    if len(rows) == 1:
                        records = ((selected, tuple(rows[0])),)
                    elif selected.casefold() == "oběd":
                        # Safe compatibility for old settings. Use only
                        # calendars whose real names start with Oběd, never
                        # breakfast, snacks or dinner. No heuristic weekdays.
                        cursor.execute(
                            LUNCH_CALENDAR_QUERY, (day.year, day.month, selected)
                        )
                        matches = cursor.fetchall()
                        records = tuple(
                            (str(row[0]).strip(), tuple(row[1:])) for row in matches
                        )
                        names = [name.casefold() for name, _ in records]
                        if len(names) != len(set(names)):
                            raise ValueError(
                                f"Duplicitní názvy kalendářů obědů pro "
                                f"{day.month:02d}/{day.year}."
                            )
                    else:
                        records = ()
                    if not records:
                        raise ValueError(
                            f"Kalendář varnedny pro {day.month:02d}/{day.year} "
                            f"a typ služby {meal_type!r} má 0 záznamů (očekáván 1 "
                            "nebo skutečné varianty Oběd-*)."
                        )
                    if any(len(values) != 31 for _, values in records):
                        raise ValueError("Tabulka varnedny nemá očekávané sloupce d01–d31.")
                    cache[key] = records

                # Evaluate ALL real lunch calendars; an invalid A/N value
                # must not be masked by another calendar already cooking.
                decisions = [
                    _calendar_status(values[day.day - 1], day=day, meal_type=name)
                    for name, values in cache[key]
                ]
                return any(decisions)

            yield is_cooking_day


def task_calendar_type(config_path: Path, task: MailTask) -> str | tuple[str, ...] | None:
    """Saved reports derive their calendar from meal_type; legacy tasks keep theirs."""
    if getattr(task, "profile_id", None):
        from services.web_daily_profiles import load_profiles, profile_file
        profile = next((p for p in load_profiles(profile_file(Path(config_path).parent)) if p.id == task.profile_id), None)
        if profile is None:
            raise ValueError("Uložený přehled této úlohy neexistuje.")
        return profile.meal_type
    if task.cooking_meal_type is not None:
        return task.cooking_meal_type
    settings = load_settings(settings_path(Path(config_path).parent))
    meal_type = settings["cooking_meal_type"]
    if not isinstance(meal_type, str) or not meal_type.strip():
        raise ValueError("U staršího odesílání není nastaven kalendář. Otevřete ho a vyberte kalendář varných dnů.")
    return meal_type.strip()


def available_cooking_calendars(config_path: Path) -> tuple[str, ...]:
    """Offer real calendars for this and the coming year, not guessed meal names."""
    today = date.today()
    config = load_config(Path(config_path), date_override=today.strftime("%d.%m.%Y"))
    import psycopg
    with psycopg.connect(**config.database) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT BTRIM(typsluzby) FROM public.varnedny "
                "WHERE rok IN (%s, %s) AND NULLIF(BTRIM(typsluzby), '') IS NOT NULL "
                "ORDER BY 1", (today.year, today.year + 1),
            )
            names = {}
            for (name,) in cursor.fetchall():
                if isinstance(name, str) and name.strip():
                    names.setdefault(name.strip().casefold(), name.strip())
    return tuple(names.values())


def resolve_task_date(config_path: Path, task: MailTask, sent_on: date) -> date:
    """Resolve a task date; only next_cooking_day needs a DB lookup."""
    if task.date_mode != "next_cooking_day":
        return target_date(task, sent_on)
    config_path = Path(config_path)
    meal_type = task_calendar_type(config_path, task)
    config = load_config(config_path, date_override=sent_on.strftime("%d.%m.%Y"))
    lookup = any_cooking_day_lookup if meal_type is None else selected_cooking_day_lookup if isinstance(meal_type, (list, tuple)) else cooking_day_lookup
    args = (config.database,) if meal_type is None else (config.database, meal_type)
    with lookup(*args) as is_day:
        return target_date(task, sent_on, is_cooking_day=is_day)




@contextmanager
def any_cooking_day_lookup(database):
    """Find the first day marked A for any calendar in the requested month."""
    import psycopg
    with psycopg.connect(**database) as connection:
        with connection.cursor() as cursor:
            cache = {}
            def is_day(day):
                key = (day.year, day.month)
                if key not in cache:
                    cursor.execute(
                        f"SELECT LOWER(BTRIM(typsluzby)), {', '.join(DAY_COLUMNS)} FROM public.varnedny WHERE rok = %s AND mesic = %s",
                        key,
                    )
                    rows = cursor.fetchall()
                    names = [row[0] for row in rows]
                    if not rows or any(not name for name in names) or len(names) != len(set(names)):
                        raise ValueError(f"Chybí nebo je duplicitní kalendář varných dnů pro {day.month:02d}/{day.year}.")
                    if any(len(row) != 32 for row in rows):
                        raise ValueError("Tabulka varnedny nemá očekávané sloupce d01–d31.")
                    cache[key] = rows
                values = [row[day.day] for row in cache[key]]
                statuses = [v.strip().upper() if isinstance(v, str) else "" for v in values]
                if any(v not in ("A", "N") for v in statuses):
                    raise ValueError(f"Neplatný stav varného dne {day:%d.%m.%Y}.")
                return "A" in statuses
            yield is_day


def report_is_cooking_day(config_path: Path, task: MailTask, report_date: date) -> bool:
    """Check the target report day, never the day the email is sent."""
    if not getattr(task, "only_cooking_days", False) or task.date_mode == "next_cooking_day":
        return True
    config_path = Path(config_path)
    meal_type = task_calendar_type(config_path, task)
    config = load_config(config_path, date_override=report_date.strftime("%d.%m.%Y"))
    lookup = any_cooking_day_lookup if meal_type is None else selected_cooking_day_lookup if isinstance(meal_type, (list, tuple)) else cooking_day_lookup
    args = (config.database,) if meal_type is None else (config.database, meal_type)
    with lookup(*args) as is_day:
        return is_day(report_date)



@contextmanager
def selected_cooking_day_lookup(database, meal_types):
    """Any selected type may cook; unrelated calendars cannot qualify a day."""
    with ExitStack() as stack:
        checks = [stack.enter_context(cooking_day_lookup(database, meal))
                  for meal in meal_filter_values(meal_types)]
        def is_day(day):
            # Evaluate every selected calendar so missing data is never hidden.
            states = [check(day) for check in checks]
            return any(states)
        yield is_day
