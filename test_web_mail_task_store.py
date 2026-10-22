"""Regression tests for persistent web mail task configuration."""
import json

import pytest

from services.web_mail_tasks import MailTask
from services.web_mail_task_store import load_tasks, save_tasks, task_file


def example_task():
    return MailTask.from_dict({
        "name": "Počty na další varný den",
        "recipients": ["kuchyne@example.org"],
        "report": "daily",
        "send_time": "08:00",
        "date_mode": "next_cooking_day",
    })


def test_load_empty_file(tmp_path):
    assert load_tasks(task_file(tmp_path)) == []


def test_save_load_roundtrip(tmp_path):
    path = task_file(tmp_path)
    task = example_task()
    save_tasks(path, [task])
    assert load_tasks(path) == [task]
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_reject_duplicate_ids(tmp_path):
    task = example_task()
    with pytest.raises(ValueError, match="Duplicitní"):
        save_tasks(task_file(tmp_path), [task, task])


def test_reject_invalid_config(tmp_path):
    path = task_file(tmp_path)
    path.write_text('{"tasks":{}}', encoding="utf-8")
    with pytest.raises(ValueError, match="pole"):
        load_tasks(path)


def test_calendar_survives_copy_disable_and_restart(tmp_path):
    from dataclasses import replace
    original = replace(example_task(), cooking_meal_type='Večeře')
    copied = replace(original, id='copy', name='Kopie', enabled=False)
    path = task_file(tmp_path)
    save_tasks(path, [original, copied])
    assert load_tasks(path) == [original, copied]
    assert [row['cooking_meal_type'] for row in json.loads(path.read_text(encoding='utf-8'))['tasks']] == ['Večeře', 'Večeře']
