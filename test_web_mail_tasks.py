"""Tests for independent web scheduler task rules."""
from datetime import date, datetime

import pytest

from services.web_mail_tasks import MailTask, next_send_at, target_date


def task(**overrides):
    data = {
        "name": "Ranní počty", "recipients": ["test@example.org"],
        "report": "daily", "send_time": "08:00",
        "date_mode": "next_cooking_day",
    }
    data.update(overrides)
    return MailTask.from_dict(data)


def test_friday_targets_monday_when_weekend_is_not_cooking():
    job = task()
    assert target_date(
        job, date(2026, 10, 23),
        is_cooking_day=lambda day: day.weekday() < 5,
    ) == date(2026, 10, 26)


def test_can_skip_holiday_as_well_as_weekend():
    job = task()
    assert target_date(
        job, date(2026, 10, 23),
        is_cooking_day=lambda day: day.weekday() < 5 and day != date(2026, 10, 26),
    ) == date(2026, 10, 27)


def test_calendar_required_for_next_cooking_day():
    with pytest.raises(ValueError, match="varnedny"):
        target_date(task(), date(2026, 10, 23))


def test_other_date_modes():
    ref = date(2026, 10, 21)
    assert target_date(task(date_mode="today"), ref) == ref
    assert target_date(task(date_mode="tomorrow"), ref) == date(2026, 10, 22)
    assert target_date(task(date_mode="offset", day_offset=3), ref) == date(2026, 10, 24)
    assert target_date(task(date_mode="fixed", fixed_date="2026-11-02"), ref) == date(2026, 11, 2)


def test_each_task_keeps_own_recipients_and_target_date():
    a = task(name="Ráno", recipients=["a@example.org"], date_mode="tomorrow")
    b = task(name="Poledne", recipients=["b@example.org"], date_mode="today", send_time="13:00")
    assert a.recipients != b.recipients
    assert target_date(a, date(2026, 10, 21)) != target_date(b, date(2026, 10, 21))
    assert next_send_at(a, datetime(2026, 10, 21, 7, 0)).hour == 8
    assert next_send_at(b, datetime(2026, 10, 21, 7, 0)).hour == 13


def test_next_send_moves_to_tomorrow_after_due_time():
    assert next_send_at(task(), datetime(2026, 10, 21, 8, 1)) == datetime(2026, 10, 22, 8, 0)


def test_invalid_time_rejected():
    with pytest.raises(ValueError, match="HH:MM"):
        task(send_time="25:00")


def test_roundtrip():
    original = task()
    assert MailTask.from_dict(original.to_dict()) == original


def test_each_task_roundtrips_its_own_calendar():
    a = task(cooking_meal_type='  Oběd  ')
    b = task(cooking_meal_type='Večeře')
    assert a.cooking_meal_type == 'Oběd'
    assert b.cooking_meal_type == 'Večeře'
    assert MailTask.from_dict(a.to_dict()) == a
    assert MailTask.from_dict(b.to_dict()) == b
    assert task().cooking_meal_type is None  # Legacy tasks keep the previous rule.


@pytest.mark.parametrize('value', ['', '   ', 1, True, [], {}])
def test_calendar_must_be_a_real_name(value):
    with pytest.raises(ValueError, match='Kalendář'):
        task(cooking_meal_type=value)
