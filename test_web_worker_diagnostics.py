"""Separate task times, failure isolation, worker versions and precise calendar errors."""
from datetime import date, datetime
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from services.web_activity import friendly_error
from services.web_branding import WEB_BUILD
from services.web_mail_cooking_days import any_cooking_day_lookup
from services.web_mail_settings import DEFAULTS
from services.web_mail_task_store import save_tasks, task_file
from services.web_mail_tasks import MailTask
from services import web_mail_worker as worker
from services.web_worker_status import observed_status, write_runtime


def task(name, time):
    return MailTask.from_dict({'name': name, 'send_time': time,
                               'recipients': ['test@example.org'], 'date_mode': 'today'})


def test_tasks_at_2250_and_2255_run_independently_once(tmp_path):
    first = task('První', '22:50')
    second = task('Druhá', '22:55')
    save_tasks(task_file(tmp_path), [second, first])
    config = tmp_path / 'config.json'
    with patch.object(worker, 'dispatch') as dispatch:
        worker.tick(config, datetime(2026, 10, 29, 22, 49))
        dispatch.assert_not_called()
        worker.tick(config, datetime(2026, 10, 29, 22, 50))
        assert [call.args[1].id for call in dispatch.call_args_list] == [first.id]
        worker.tick(config, datetime(2026, 10, 29, 22, 54))
        assert dispatch.call_count == 1
        worker.tick(config, datetime(2026, 10, 29, 22, 55))
        assert [call.args[1].id for call in dispatch.call_args_list] == [first.id, second.id]
        worker.tick(config, datetime(2026, 10, 29, 23, 0))
        assert dispatch.call_count == 2


def test_calendar_failure_of_one_task_does_not_block_later_task(tmp_path):
    first = task('Chybějící kalendář', '22:50')
    second = task('Druhý přehled', '22:55')
    save_tasks(task_file(tmp_path), [first, second])
    def dispatch(_config, item, _day):
        if item.id == first.id:
            raise ValueError('V Jídelně chybí kalendář varných dnů pro 11/2026.')
    with patch.object(worker, 'dispatch', side_effect=dispatch) as run, \
         patch.object(worker, 'load_settings', return_value={**DEFAULTS, 'dashboard_enabled': False}):
        worker.tick(tmp_path / 'config.json', datetime(2026, 10, 29, 22, 50))
        worker.tick(tmp_path / 'config.json', datetime(2026, 10, 29, 22, 55))
        assert [call.args[1].id for call in run.call_args_list] == [first.id, second.id]
    assert worker.load_state(worker.state_path(tmp_path / 'config.json')) == {
        first.id: '2026-10-29', second.id: '2026-10-29',
    }


@pytest.mark.parametrize('old_build', [None, '20261029.3'])
def test_old_worker_is_not_reported_as_matching_current_app(tmp_path, old_build):
    write_runtime(tmp_path)
    path = tmp_path / 'web_mail_worker_runtime.json'
    raw = json.loads(path.read_text())
    assert raw['build'] == WEB_BUILD
    assert 'čeká' in observed_status(tmp_path)
    raw['build'] = old_build
    path.write_text(json.dumps(raw))
    assert 'jiné sestavení' in observed_status(tmp_path)
    assert 'aktualizujte a restartujte worker' in observed_status(tmp_path)


@pytest.mark.parametrize('rows, expected, absent', [
    ([], 'chybí kalendář', 'duplicit'),
    ([('oběd', *(['N'] * 31)), ('oběd', *(['N'] * 31))], 'více záznamů stejného kalendáře', 'chybí'),
    ([(None, *(['N'] * 31))], 'prázdný typ stravy', 'duplicit'),
])
def test_calendar_errors_distinguish_missing_duplicate_and_empty_names(rows, expected, absent):
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    psycopg = MagicMock()
    psycopg.connect.return_value.__enter__.return_value = connection
    with patch.dict(sys.modules, {'psycopg': psycopg}):
        with any_cooking_day_lookup({}) as lookup:
            with pytest.raises(ValueError) as error:
                lookup(date(2026, 11, 2))
    text = str(error.value)
    assert expected in text
    assert absent not in text
    assert '11/2026' in text
    assert friendly_error(error.value) == text
    if len(rows) == 2:
        assert 'oběd' in text and 'počet záznamů: 2' in text
