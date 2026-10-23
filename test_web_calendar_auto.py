"""Automatic report calendar selection, without DB access or mail transport."""
import importlib.util
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch


def module(name, **values):
    result = ModuleType(name)
    result.__dict__.update(values)
    return result


def load_calendar(profiles=()):
    spec = importlib.util.spec_from_file_location('calendar_under_test', Path(__file__).parent / 'services/web_mail_cooking_days.py')
    result = importlib.util.module_from_spec(spec)
    deps = {
        'services.web_mail_settings': module('settings', load_settings=lambda p: {'cooking_meal_type': 'Oběd'}, settings_path=lambda p: p),
        'services.web_mail_tasks': module('tasks', MailTask=object, target_date=lambda *a, **k: None),
        'stravovaci_sestava': module('report', load_config=lambda *a, **k: None),
        'services.web_daily_profiles': module('profiles', load_profiles=lambda p: profiles, profile_file=lambda p: p),
    }
    with patch.dict(sys.modules, deps):
        spec.loader.exec_module(result)
    return result, deps


class AutomaticCalendarTests(unittest.TestCase):
    def test_profile_overrides_old_calendar(self):
        for meal in ('večeře', None):
            calendar, deps = load_calendar([SimpleNamespace(id='p', meal_type=meal)])
            with patch.dict(sys.modules, deps):
                self.assertEqual(calendar.task_calendar_type(Path('config.json'), SimpleNamespace(profile_id='p', cooking_meal_type='Oběd')), meal)

    def test_legacy_keeps_its_calendar(self):
        calendar, _ = load_calendar()
        self.assertEqual(calendar.task_calendar_type(Path('config.json'), SimpleNamespace(profile_id=None, cooking_meal_type='Snídaně')), 'Snídaně')

    def test_any_calendar_day_and_month_cache(self):
        calendar, _ = load_calendar()
        cursor = MagicMock()
        breakfast = ['N'] * 31
        dinner = ['N'] * 31
        dinner[25] = 'A'
        cursor.fetchall.return_value = [('snídaně', *breakfast), ('večeře', *dinner)]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        psycopg = MagicMock()
        psycopg.connect.return_value.__enter__.return_value = connection
        with patch.dict(sys.modules, {'psycopg': psycopg}):
            with calendar.any_cooking_day_lookup({}) as is_day:
                self.assertFalse(is_day(date(2026, 10, 25)))
                self.assertTrue(is_day(date(2026, 10, 26)))
                self.assertEqual(cursor.execute.call_count, 1)

    def test_missing_profile_does_not_fall_back(self):
        calendar, deps = load_calendar()
        with patch.dict(sys.modules, deps), self.assertRaises(ValueError):
            calendar.task_calendar_type(Path('config.json'), SimpleNamespace(profile_id='missing', cooking_meal_type='Oběd'))


if __name__ == '__main__':
    unittest.main()
