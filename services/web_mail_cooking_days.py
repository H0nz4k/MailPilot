"""PostgreSQL calendar lookup for scheduled MailPilot reports.

public.varnedny stores one row per (rok, mesic, typsluzby).
The column d01..d31 identifies a day in that month; A means cooking,
N means not cooking. No weekday or public-holiday assumptions are made.
"""
from __future__ import annotations

from contextlib import contextmanager
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
            cache: dict[tuple[int, int], tuple[object, ...]] = {}

            def is_cooking_day(day: date) -> bool:
                key = (day.year, day.month)
                if key not in cache:
                    cursor.execute(CALENDAR_QUERY, (day.year, day.month, meal_type.strip()))
                    rows = cursor.fetchall()
                    if len(rows) != 1:
                        raise ValueError(
                            f"Kalendář varnedny pro {day.month:02d}/{day.year} "
                            f"a typ služby {meal_type!r} má {len(rows)} záznamů (očekáván 1)."
                        )
                    if len(rows[0]) != 31:
                        raise ValueError("Tabulka varnedny nemá očekávané sloupce d01–d31.")
                    cache[key] = tuple(rows[0])

                value = cache[key][day.day - 1]
                status = value.strip().upper() if isinstance(value, str) else ""
                if status not in ("A", "N"):
                    raise ValueError(
                        f"Neplatný stav varného dne {day:%d.%m.%Y} "
                        f"pro {meal_type!r}: {value!r}."
                    )
                return status == "A"

            yield is_cooking_day


def task_calendar_type(config_path: Path, task: MailTask) -> str:
    """An explicit task calendar wins; only old tasks inherit the former setting."""
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
    with cooking_day_lookup(config.database, meal_type) as is_day:
        return target_date(task, sent_on, is_cooking_day=is_day)

