import tempfile
import unittest
from datetime import date
from pathlib import Path
from services.web_activity import record_event, read_events, friendly_error


class ActivityTests(unittest.TestCase):
    def test_roundtrip_and_latest_result(self):
        with tempfile.TemporaryDirectory() as directory:
            record_event(directory, 'error', 'Neodesláno', task_id='a', task_name='Škola')
            record_event(directory, 'sent', 'Odesláno', task_id='b', report_date=date(2026, 10, 26))
            events = read_events(directory)
            self.assertEqual([e['task_id'] for e in events], ['b', 'a'])
            self.assertEqual(events[0]['report_date'], '2026-10-26')
            self.assertEqual(events[1]['task_name'], 'Škola')

    def test_missing_store_read_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(read_events(directory), [])
            self.assertFalse((Path(directory) / 'logy').exists())

    def test_calendar_message(self):
        error = ValueError("Kalendář varnedny pro 11/2026 a typ služby 'Oběd' má 0 záznamů (očekáván 1).")
        self.assertEqual(friendly_error(error), 'Chybí kalendář varných dnů Oběd pro 11/2026. Doplňte jej v Jídelně.')

    def test_unknown_error_does_not_expose_credentials(self):
        self.assertNotIn('secret', friendly_error(ValueError('connection postgres://user:secret@host')))

    def test_activity_failure_does_not_interrupt_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'logy').write_text('not a directory')
            with self.assertLogs('services.web_activity', level='ERROR'):
                record_event(directory, 'sent', 'Odesláno')


if __name__ == '__main__':
    unittest.main()
