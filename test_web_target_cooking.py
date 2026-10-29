"""Target cooking-day checks: no database connections or email delivery."""
import ast
import importlib.util
import sys
import unittest
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_web_calendar_auto import load_calendar, module

ROOT = Path(__file__).parent


class TargetCookingTests(unittest.TestCase):
    def check_calendar(self, meal, cooks):
        calendar, deps = load_calendar([SimpleNamespace(id='p', meal_type=meal)])
        day = date(2026, 10, 28)
        task = SimpleNamespace(profile_id='p', cooking_meal_type=None,
                               only_cooking_days=True, date_mode='offset')
        calls = []

        @contextmanager
        def lookup(*args):
            calls.append(args)
            yield lambda actual: cooks if actual == day else self.fail('Wrong target date')

        calendar.load_config = Mock(return_value=SimpleNamespace(database={'db': 'test'}))
        calendar.cooking_day_lookup = lookup
        calendar.any_cooking_day_lookup = lookup
        with patch.dict(sys.modules, deps):
            self.assertEqual(calendar.report_is_cooking_day(Path('config.json'), task, day), cooks)
        self.assertEqual(calls, [({'db': 'test'},)] if meal is None else [({'db': 'test'}, meal)])
        calendar.load_config.assert_called_once_with(Path('config.json'), date_override='28.10.2026')

    def test_lunch_target_cooking(self):
        self.check_calendar('Oběd', True)

    def test_lunch_target_not_cooking(self):
        self.check_calendar('Oběd', False)

    def test_all_types_any_cooking(self):
        self.check_calendar(None, True)

    def test_all_types_none_cooking(self):
        self.check_calendar(None, False)

    def test_disabled_and_next_cooking_need_no_extra_db_lookup(self):
        calendar, _ = load_calendar()
        calendar.load_config = Mock(side_effect=AssertionError('Unexpected DB lookup'))
        for enabled, mode in [(False, 'offset'), (True, 'next_cooking_day')]:
            task = SimpleNamespace(only_cooking_days=enabled, date_mode=mode)
            self.assertTrue(calendar.report_is_cooking_day(Path('config.json'), task, date.today()))

    def test_calendar_error_is_not_a_non_cooking_day(self):
        calendar, deps = load_calendar()
        task = SimpleNamespace(profile_id='missing', only_cooking_days=True, date_mode='offset')
        with patch.dict(sys.modules, deps), self.assertRaises(ValueError):
            calendar.report_is_cooking_day(Path('config.json'), task, date.today())

    def worker_namespace(self):
        tree = ast.parse((ROOT / 'services/web_mail_worker.py').read_text(encoding='utf-8'))
        wanted = {'dispatch', 'tick'}
        body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
        ns = {'Path': Path, 'date': date, 'datetime': datetime, 'WEB_BUILD': 'test',
              'resolve_task_date': Mock(return_value=date(2026, 10, 28)),
              'report_is_cooking_day': Mock(return_value=False),
              'deliver_daily': Mock(), 'record_event': Mock(), 'LOG': Mock(),
              'state_path': lambda p: p, 'load_state': lambda p: {},
              'save_state': Mock(), 'task_file': lambda p: p, 'runtime_status': Mock()}
        exec(compile(ast.Module(body=body, type_ignores=[]), '<worker>', 'exec'), ns)
        return ns

    def test_skip_does_not_deliver_and_is_completed_once(self):
        ns = self.worker_namespace()
        task = SimpleNamespace(id='task', name='Lunch', report='daily', enabled=True, send_time='06:30')
        ns['load_tasks'] = lambda p: [task]
        ns['tick'](Path('config.json'), datetime(2026, 10, 26, 7))
        ns['deliver_daily'].assert_not_called()
        self.assertEqual(ns['record_event'].call_args.args[1], 'skipped')
        self.assertEqual(ns['record_event'].call_args.kwargs['report_date'], date(2026, 10, 28))
        completed = ns['save_state'].call_args.args[1]
        self.assertEqual(completed, {'task': '2026-10-26'})
        ns['load_state'] = lambda p: completed
        ns['tick'](Path('config.json'), datetime(2026, 10, 26, 8))
        ns['record_event'].assert_called_once()

    def test_cooking_target_delivers(self):
        ns = self.worker_namespace()
        ns['report_is_cooking_day'].return_value = True
        task = SimpleNamespace(id='task', name='Lunch', report='daily')
        ns['dispatch'](Path('config.json'), task, date(2026, 10, 26))
        ns['deliver_daily'].assert_called_once_with(Path('config.json'), task, date(2026, 10, 28))

    def test_flag_roundtrip_legacy_default_and_strict_validation(self):
        spec = importlib.util.spec_from_file_location('target_tasks_test', ROOT / 'services/web_mail_tasks.py')
        tasks = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'target_tasks_test': tasks}):
            spec.loader.exec_module(tasks)
        raw = dict(name='Lunch', recipients=['test@example.org'], send_time='06:30',
                   date_mode='offset', day_offset=2)
        with patch.dict(sys.modules, {'mail_service': module('mail', normalize_recipients=lambda x: x)}):
            self.assertFalse(tasks.MailTask.from_dict(raw).only_cooking_days)
            job = tasks.MailTask.from_dict(dict(raw, only_cooking_days=True))
            self.assertEqual(tasks.MailTask.from_dict(job.to_dict()), job)
            self.assertEqual(tasks.target_date(job, date(2026, 12, 31)), date(2027, 1, 2))
            for invalid in ('false', 1, None):
                with self.assertRaises(ValueError):
                    tasks.MailTask.from_dict(dict(raw, only_cooking_days=invalid))


if __name__ == '__main__':
    unittest.main()


