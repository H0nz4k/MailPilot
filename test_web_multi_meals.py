"""Multiple meal filtering and ordinary-user credentials; no external IO."""
import ast
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import credential_store as credentials
from services.web_daily_profiles import DailyProfile, save_profile, load_profiles
from services.web_meal_types import normalize_meal_filter, meal_filter_values
from services.web_report_output import manual_pdf_path
from stravovaci_sestava import AppConfig, fetch_report


class MultiMealTests(unittest.TestCase):
    def test_normalization_and_legacy(self):
        self.assertIsNone(normalize_meal_filter(None))
        self.assertIsNone(normalize_meal_filter([]))
        self.assertEqual(normalize_meal_filter(' Oběd '), 'oběd')
        self.assertEqual(normalize_meal_filter(['Večeře', ' Oběd ', 'OBĚD']), ('oběd', 'večeře'))
        for invalid in [True, [''], [3], {'meal': 'lunch'}]:
            with self.assertRaises(ValueError):
                normalize_meal_filter(invalid)

    def test_profiles_preserve_multiple_and_legacy(self):
        profile = DailyProfile.from_dict(dict(name='Lunch', categories=['A'], meal_type=['Oběd-A', 'Oběd-B']))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'daily_reports.json'
            save_profile(path, profile)
            self.assertEqual(load_profiles(path), [profile])
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['profiles'][0]['meal_type'], ['oběd-a', 'oběd-b'])
        old = DailyProfile.from_dict(dict(name='old', categories=['A'], meal_type='Oběd'))
        self.assertEqual(old.meal_type, 'oběd')

    def test_manual_output_is_stable_and_distinct(self):
        def output(meals):
            return manual_pdf_path(Path('report.pdf'), ['A'], ['A'], meals)
        self.assertEqual(output(('oběd-b','oběd-a')), output(('oběd-a','oběd-b')))
        self.assertNotEqual(output(('oběd-a','oběd-b')), output('oběd-a'))

    def test_all_five_queries_filter_selected_types(self):
        class SQL(str):
            def format(self, **kw):
                return SQL(str(self).format(**kw))
        cursor = Mock()
        cursor.fetchall.side_effect = [[('A',)], [], [], [], [], [] , []]
        cursor.fetchone.return_value = ('School',)
        cm = Mock()
        cm.__enter__ = Mock(return_value=cursor)
        cm.__exit__ = Mock(return_value=False)
        connection = Mock()
        connection.cursor.return_value = cm
        connect_cm = Mock()
        connect_cm.__enter__ = Mock(return_value=connection)
        connect_cm.__exit__ = Mock(return_value=False)
        fake = SimpleNamespace(connect=Mock(return_value=connect_cm), sql=SimpleNamespace(SQL=SQL, Identifier=lambda x:x))
        config = AppConfig(database={}, report_date=date(2026,10,28), categories=('A',), language='česky', menu_list_number=1, meal_type=('oběd-a','oběd-b'))
        with patch.dict(sys.modules, {'psycopg': fake}):
            fetch_report(config)
        filtered = [(str(call.args[0]), call.args[1]) for call in cursor.execute.call_args_list if 'ANY(%s::text[])' in str(call.args[0])]
        self.assertEqual(len(filtered), 5)
        for query, params in filtered:
            self.assertEqual(params.count(['oběd-a','oběd-b']), 2)
            self.assertNotIn('= %s::text)', query)

    def test_selected_calendars_only_and_all_are_validated(self):
        # Load calendar module with lightweight dependencies for this unit test.
        import importlib.util
        fake_settings = SimpleNamespace(load_settings=Mock(), settings_path=lambda p:p)
        fake_tasks = SimpleNamespace(MailTask=object, target_date=Mock())
        spec=importlib.util.spec_from_file_location('multi_calendar', Path(__file__).parent/'services/web_mail_cooking_days.py')
        calendar=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'services.web_mail_settings':fake_settings,'services.web_mail_tasks':fake_tasks}):
            spec.loader.exec_module(calendar)
        visited=[]
        @contextmanager
        def lookup(database, meal):
            visited.append(meal)
            yield lambda day: meal=='oběd-b'
        with patch.object(calendar,'cooking_day_lookup',lookup):
            with calendar.selected_cooking_day_lookup({}, ('oběd-a','oběd-b')) as check:
                self.assertTrue(check(date(2026,10,28)))
        self.assertEqual(visited,['oběd-a','oběd-b'])

    def test_keyring_write_denied_uses_user_dpapi(self):
        keyring=Mock()
        keyring.set_password.side_effect=PermissionError('denied')
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(credentials,'_user_admin_path',return_value=Path(tmp)/'admin.dpapi'), \
             patch.object(credentials,'_keyring_module',return_value=(keyring,RuntimeError)), \
             patch.object(credentials,'_is_windows',return_value=True), \
             patch.object(credentials,'_dpapi_encrypt_machine',return_value='encrypted') as encrypt:
            credentials.set_admin_password('secret')
            encrypt.assert_called_once_with(b'secret',flags=0)
            self.assertEqual((Path(tmp)/'admin.dpapi').read_text(),'encrypted')

    def test_legacy_password_read_does_not_require_migration_write(self):
        keyring=Mock()
        keyring.get_password.side_effect=[None,'secret']
        keyring.set_password.side_effect=PermissionError('denied')
        with patch.object(credentials,'_read_user_admin_password',return_value=None), \
             patch.object(credentials,'_keyring_module',return_value=(keyring,RuntimeError)):
            self.assertEqual(credentials.get_admin_password(),'secret')

    def test_unreadable_vault_is_error_not_password_reset(self):
        with patch.object(credentials,'_read_user_admin_password',side_effect=PermissionError('denied')):
            with self.assertRaises(credentials.CredentialStoreError):
                credentials.get_admin_password()


if __name__ == '__main__':
    unittest.main()
