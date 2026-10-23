"""Regression tests: MailPilot must trust public.varnedny, not weekdays."""
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from services import web_mail_cooking_days as calendar
from services.web_mail_tasks import MailTask


def task(date_mode="next_cooking_day"):
    return MailTask(
        id="test", name="Test", recipients=("test@example.invalid",),
        report="daily", send_time="08:00", date_mode=date_mode,
    )


def month_row(**day_values):
    """Postgres returns d01..d31 ordered, rather than a separate date column."""
    statuses = ["N"] * 31
    for number, status in day_values.items():
        statuses[int(number[1:]) - 1] = status
    return tuple(statuses)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.key = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, args):
        assert "FROM public.varnedny" in query
        assert all(f"d{n:02d}" in query for n in range(1, 32))
        assert "LOWER(BTRIM(typsluzby))" in query
        self.key = tuple(args)
        self.calls.append(self.key)

    def fetchall(self):
        return self.rows.get(self.key, [])


def fake_database(monkeypatch, rows):
    cursor = FakeCursor(rows)
    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def cursor(self):
            return cursor

    def connect(**kwargs):
        assert kwargs == {"dbname": "jidelna"}
        return Connection()

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    return cursor


@pytest.mark.parametrize(
    ("from_day", "cooking", "expected"),
    [
        (date(2026, 10, 23), {"d24": "A"}, date(2026, 10, 24)),  # Saturday
        (date(2026, 10, 23), {"d25": "A"}, date(2026, 10, 25)),  # Sunday
        (date(2026, 10, 27), {"d28": "A"}, date(2026, 10, 28)),  # Czech holiday
        (date(2026, 10, 26), {"d29": "A"}, date(2026, 10, 29)),  # Weekday N
    ],
)
def test_next_day_respects_only_a_values(monkeypatch, from_day, cooking, expected):
    cursor = fake_database(
        monkeypatch, {(2026, 10, "Oběd"): [month_row(**cooking)]}
    )
    with calendar.cooking_day_lookup({"dbname": "jidelna"}, "Oběd") as is_cooking:
        assert calendar.target_date(task(), from_day, is_cooking_day=is_cooking) == expected
    assert cursor.calls == [(2026, 10, "Oběd")]


def test_transition_to_next_month(monkeypatch):
    cursor = fake_database(
        monkeypatch,
        {
            (2026, 10, "Oběd"): [month_row()],
            (2026, 11, "Oběd"): [month_row(d01="A")],
        },
    )
    with calendar.cooking_day_lookup({"dbname": "jidelna"}, "Oběd") as is_cooking:
        assert calendar.target_date(
            task(), date(2026, 10, 30), is_cooking_day=is_cooking
        ) == date(2026, 11, 1)
    assert cursor.calls == [(2026, 10, "Oběd"), (2026, 11, "Oběd")]


def test_missing_month_fails_closed(monkeypatch):
    fake_database(monkeypatch, {})
    with calendar.cooking_day_lookup({"dbname": "jidelna"}, "Oběd") as is_cooking:
        with pytest.raises(ValueError, match="má 0 záznamů"):
            calendar.target_date(task(), date(2026, 10, 23), is_cooking_day=is_cooking)


def test_duplicate_service_month_fails_closed(monkeypatch):
    record = month_row(d24="A")
    fake_database(monkeypatch, {(2026, 10, "Oběd"): [record, record]})
    with calendar.cooking_day_lookup({"dbname": "jidelna"}, "Oběd") as is_cooking:
        with pytest.raises(ValueError, match="má 2 záznamů"):
            calendar.target_date(task(), date(2026, 10, 23), is_cooking_day=is_cooking)


@pytest.mark.parametrize("status", [None, "", "X", "1"])
def test_unknown_status_never_defaults_to_n_or_a(monkeypatch, status):
    fake_database(monkeypatch, {(2026, 10, "Oběd"): [month_row(d24=status)]})
    with calendar.cooking_day_lookup({"dbname": "jidelna"}, "Oběd") as is_cooking:
        with pytest.raises(ValueError, match="Neplatný stav"):
            calendar.target_date(task(), date(2026, 10, 23), is_cooking_day=is_cooking)


def test_service_type_is_part_of_calendar_key(monkeypatch):
    cursor = fake_database(
        monkeypatch,
        {
            (2026, 10, "Večeře"): [month_row(d24="N", d25="A")],
            (2026, 10, "Oběd"): [month_row(d24="A")],
        },
    )
    with calendar.cooking_day_lookup({"dbname": "jidelna"}, "Večeře") as is_cooking:
        assert calendar.target_date(
            task(), date(2026, 10, 23), is_cooking_day=is_cooking
        ) == date(2026, 10, 25)
    assert cursor.calls == [(2026, 10, "Večeře")]


def test_resolve_task_date_uses_saved_service_and_existing_db(monkeypatch, tmp_path):
    cursor = fake_database(
        monkeypatch, {(2026, 10, "Večeře"): [month_row(d25="A")]}
    )
    monkeypatch.setattr(
        calendar, "load_settings", lambda _: {"cooking_meal_type": "Večeře"}
    )
    def load_config(path, date_override):
        assert path == tmp_path / "config.json"
        assert date_override == "23.10.2026"
        return SimpleNamespace(database={"dbname": "jidelna"})
    monkeypatch.setattr(calendar, "load_config", load_config)
    resolved = calendar.resolve_task_date(
        tmp_path / "config.json", task(), date(2026, 10, 23)
    )
    assert resolved == date(2026, 10, 25)
    assert cursor.calls == [(2026, 10, "Večeře")]


def test_other_date_modes_do_not_require_database(monkeypatch, tmp_path):
    def no_database(*_, **__):
        pytest.fail("Ordinary date modes must not query database")
    monkeypatch.setattr(calendar, "load_config", no_database)
    assert calendar.resolve_task_date(
        tmp_path / "config.json", task("tomorrow"), date(2026, 10, 23)
    ) == date(2026, 10, 24)


# Two real example rows supplied with the JídelnaSQL schema export.
# No current production calendar or customer data is required for this fixture.
SEPTEMBER_2010_LUNCH = "NAANNAAAAANNAAAAANNAAAAANNANAAN"
OCTOBER_2010_LUNCH = "ANNAAAAANNAAAAANNAAAAANNAANNNNN"


def sample_calendar_rows():
    assert len(SEPTEMBER_2010_LUNCH) == len(OCTOBER_2010_LUNCH) == 31
    return {
        (2010, 9, "Oběd"): [tuple(SEPTEMBER_2010_LUNCH)],
        (2010, 10, "Oběd"): [tuple(OCTOBER_2010_LUNCH)],
    }


@pytest.mark.parametrize(
    ("sent_on", "expected"),
    [
        (date(2010, 9, 1), date(2010, 9, 2)),
        (date(2010, 9, 3), date(2010, 9, 6)),
        (date(2010, 9, 27), date(2010, 9, 29)),
        (date(2010, 9, 29), date(2010, 9, 30)),
        (date(2010, 9, 30), date(2010, 10, 1)),
        (date(2010, 10, 1), date(2010, 10, 4)),
    ],
)
def test_user_provided_september_october_2010_calendar(
    monkeypatch, sent_on, expected,
):
    """Real A/N patterns: skip N, accept A, cross the month boundary."""
    fake_database(monkeypatch, sample_calendar_rows())
    with calendar.cooking_day_lookup({"dbname": "jidelna"}, "Oběd") as is_cooking:
        actual = calendar.target_date(task(), sent_on, is_cooking_day=is_cooking)
    assert actual == expected


def test_user_provided_example_does_not_invent_missing_november(monkeypatch):
    """After last October A, a November row is required to choose a date."""
    fake_database(monkeypatch, sample_calendar_rows())
    with calendar.cooking_day_lookup({"dbname": "jidelna"}, "Oběd") as is_cooking:
        with pytest.raises(ValueError, match="11/2010"):
            calendar.target_date(
                task(), date(2010, 10, 26), is_cooking_day=is_cooking,
            )


def test_worker_dispatch_uses_each_tasks_calendar_instead_of_global_setting(monkeypatch, tmp_path):
    from dataclasses import replace
    from services import web_mail_worker as worker
    rows = {
        (2026, 10, 'Snídaně'): [month_row(d24='A')],
        (2026, 10, 'Oběd'): [month_row(d26='A')],
        (2026, 10, 'Večeře'): [month_row(d25='A')],
    }
    cursor = fake_database(monkeypatch, rows)
    monkeypatch.setattr(calendar, 'load_config', lambda *_a, **_k: SimpleNamespace(database={'dbname': 'jidelna'}))
    def no_global(_):
        pytest.fail('Explicit task calendars must not depend on the old shared setting')
    monkeypatch.setattr(calendar, 'load_settings', no_global)
    delivered = []
    monkeypatch.setattr(worker, 'deliver_daily', lambda path, job, day: delivered.append((job.cooking_meal_type, day)))
    for meal in ('Snídaně', 'Oběd', 'Večeře'):
        worker.dispatch(tmp_path / 'config.json', replace(task(), cooking_meal_type=meal), date(2026, 10, 23))
    assert delivered == [('Snídaně', date(2026, 10, 24)), ('Oběd', date(2026, 10, 26)), ('Večeře', date(2026, 10, 25))]
    assert cursor.calls == [(2026, 10, meal) for meal in ('Snídaně', 'Oběd', 'Večeře')]


def test_missing_explicit_calendar_never_falls_back_to_lunch(monkeypatch, tmp_path):
    from dataclasses import replace
    cursor = fake_database(monkeypatch, {(2026, 10, 'Oběd'): [month_row(d24='A')]})
    monkeypatch.setattr(calendar, 'load_config', lambda *_a, **_k: SimpleNamespace(database={'dbname': 'jidelna'}))
    monkeypatch.setattr(calendar, 'load_settings', lambda _: {'cooking_meal_type': 'Oběd'})
    with pytest.raises(ValueError, match='Večeře'):
        calendar.resolve_task_date(tmp_path / 'config.json', replace(task(), cooking_meal_type='Večeře'), date(2026, 10, 23))
    assert cursor.calls == [(2026, 10, 'Večeře')]


def test_calendar_choices_come_only_from_actual_calendar_rows(monkeypatch, tmp_path):
    today = date.today()
    queries = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, args): queries.append((sql, args))
        def fetchall(self): return [('Oběd',), (' oběd ',), ('Večeře',), ('',)]
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def cursor(self): return Cursor()
    monkeypatch.setitem(sys.modules, 'psycopg', SimpleNamespace(connect=lambda **_: Connection()))
    monkeypatch.setattr(calendar, 'load_config', lambda *_a, **_k: SimpleNamespace(database={}))
    assert calendar.available_cooking_calendars(tmp_path / 'config.json') == ('Oběd', 'Večeře')
    assert 'FROM public.varnedny' in queries[0][0]
    assert queries[0][1] == (today.year, today.year + 1)
