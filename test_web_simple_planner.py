"""Only the current planner is rendered; exports use current settings and wizard recipients."""
import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from mail_service import MailDispatchResult
from services.web_mail_settings import DEFAULTS, save_settings, settings_path
from stravovaci_nicegui import NiceGuiApp


def setup_page(tmp_path):
    config = tmp_path / 'config.json'
    shutil.copyfile(Path(__file__).with_name('config.example.json'), config)
    raw = json.loads(config.read_text())
    raw.update(mail_prijemci=['old@example.org'], mail_text='Původní text', mail_odesilatel='old-sender@example.org')
    config.write_text(json.dumps(raw))
    # Even an unreadable legacy plan no longer blocks or changes the new UI.
    (tmp_path / 'planovac.json').write_text('LEGACY-PLAN-UNCHANGED')
    pages = []

    def root():
        page = NiceGuiApp(config)
        page.build()
        page.populate_categories([('1', 'Žáci')])
        pages.append(page)

    return root, pages


@pytest.mark.asyncio
async def test_single_planner_and_pdf_preferences_preserve_legacy_data(tmp_path):
    root, pages = setup_page(tmp_path)
    with patch.object(NiceGuiApp, '_stored_password', return_value=''), \
         patch.object(NiceGuiApp, '_schedule_first_run'), \
         patch('stravovaci_nicegui.get_resend_api_key', side_effect=AssertionError('PDF does not require email credentials')):
        async with user_simulation(root) as user:
            await user.open('/')
            with user:
                page = pages[0]
                page.tabs.value = 'mail_tasks'
                labels = [e.props.get('label') for e in user.client.elements.values() if isinstance(e, ui.tab)]
                assert 'E-maily funkcí' not in labels
                assert 'Původní plánovač' not in labels
                assert not hasattr(page, 'api_key_input')
                assert not hasattr(page, 'sender_input')
                assert not hasattr(page, 'job_name_input')
                page._apply_daily_categories(['1'])
                await page._persist_settings()
            saved = json.loads((tmp_path / 'config.json').read_text())
            assert saved['mail_prijemci'] == ['old@example.org']
            assert saved['mail_text'] == 'Původní text'
            assert saved['mail_odesilatel'] == 'old-sender@example.org'
            assert (tmp_path / 'planovac.json').read_text() == 'LEGACY-PLAN-UNCHANGED'


@pytest.mark.asyncio
@pytest.mark.parametrize('transport', ['resend', 'smtp'])
async def test_one_off_mail_uses_wizard_recipients_and_outgoing_settings(tmp_path, transport):
    root, pages = setup_page(tmp_path)
    save_settings(settings_path(tmp_path), {
        **DEFAULTS, 'transport': transport, 'from_email': 'current@example.org',
        'subject_template': 'Přehled {date}', 'body_template': 'Příloha {report} za {date}',
    })
    result = {'skipped': False, 'path': tmp_path / 'preview.pdf',
              'dispatch': MailDispatchResult(('new@example.org',))}
    with patch.object(NiceGuiApp, '_stored_password', return_value=''), \
         patch.object(NiceGuiApp, '_schedule_first_run'), \
         patch.object(NiceGuiApp, '_confirm_send', new_callable=AsyncMock, return_value=True), \
         patch.object(NiceGuiApp, '_send_mail_worker', return_value=result) as send, \
         patch('stravovaci_nicegui.get_resend_api_key', return_value='re_test') as key:
        async with user_simulation(root) as user:
            await user.open('/')
            with user:
                page = pages[0]
                page.connection_ok = True
                page._apply_daily_categories(['1'])
                page.date_input.value = '29.10.2026'
                page.wizard_recipients.input.value = 'new@example.org'
                await page.send_mail()
            send.assert_called_once()
            args = send.call_args.args
            assert args[0] == ('new@example.org',)
            assert args[1] == ('re_test' if transport == 'resend' else '')
            assert args[2] == 'current@example.org'
            assert args[3] == 'Příloha Denní stav za 29.10.2026'
            assert send.call_args.kwargs['subject'] == 'Přehled 29.10.2026'
            if transport == 'smtp':
                key.assert_not_called()


def test_manual_pdf_worker_uses_smtp_without_resend(tmp_path):
    setup_page(tmp_path)
    save_settings(settings_path(tmp_path), {**DEFAULTS, 'transport': 'smtp'})
    with patch.object(NiceGuiApp, '_stored_password', return_value=''), \
         patch('stravovaci_sestava.get_password', return_value='test-password'), \
         patch('stravovaci_nicegui.fetch_report', return_value=object()), \
         patch('stravovaci_nicegui.create_pdf', return_value=tmp_path / 'preview.pdf'), \
         patch('stravovaci_nicegui.smtp_send', return_value=('new@example.org',)) as smtp, \
         patch('stravovaci_nicegui.send_pdf_via_mailsender') as resend:
        page = NiceGuiApp(tmp_path / 'config.json')
        result = page._send_mail_worker(
            ('new@example.org',), '', 'current@example.org', 'Text', False, subject='Předmět',
        )
        assert result['dispatch'].recipients == ('new@example.org',)
        smtp.assert_called_once()
        resend.assert_not_called()
