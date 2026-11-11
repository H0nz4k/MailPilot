from datetime import date
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('prototype_engine', Path(__file__).parent / 'backend' / 'engine.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def test_period_cross_year_and_selected_status():
    result = engine.handle({'start':'2026-12-31','end':'2027-01-01','status':'collected','category':'ZACI'})
    assert result['collected'] == 2 and result['uncollected'] == 0
    assert [r['date'] for r in result['rows']] == ['2026-12-31', '2027-01-01']
    assert all(r['name'] == 'Anna Nováková' for r in result['rows'])


def test_reject_invalid_period_and_filters():
    import pytest
    for request in [
        {'start':'2026-01-02','end':'2026-01-01','status':'both','category':'all'},
        {'start':'2026-01-01','end':'2027-01-02','status':'both','category':'all'},
        {'start':'2026-01-01','end':'2026-01-01','status':'invalid','category':'all'},
    ]:
        with pytest.raises(ValueError): engine.handle(request)


def test_period_pdf_groups_each_diner_and_keeps_counts(tmp_path):
    from pypdf import PdfReader
    result = engine.handle({'start':'2026-11-10','end':'2026-11-12','status':'both',
                            'category':'all','action':'pdf','output_dir':str(tmp_path)})
    assert (result['collected'], result['uncollected']) == (6, 6)
    text = '\n'.join(p.extract_text() for p in PdfReader(result['pdf']).pages)
    assert 'Součty podle strávníků' in text
    assert text.count('Anna Nováková') == 1
    assert text.count('Jan Dvořák') == 1
    assert 'Odebráno: 6' in text and 'Neodebráno: 6' in text
    assert '10.11.2026' not in text.split('Součty podle strávníků', 1)[1]


def test_period_pdf_single_status_hides_other_column(tmp_path):
    from pypdf import PdfReader
    result = engine.handle({'start':'2026-11-10','end':'2026-11-12','status':'collected',
                            'category':'all','action':'pdf','output_dir':str(tmp_path)})
    text = '\n'.join(p.extract_text() for p in PdfReader(result['pdf']).pages)
    assert 'Odebráno: 6' in text and 'Neodebráno' not in text
    assert text.count('Anna Nováková') == 1


def test_legacy_connection_respects_category_permissions_and_does_not_store_password(monkeypatch):
    from types import SimpleNamespace
    import sys
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge
    config = SimpleNamespace(database={'host':'example', 'password':'secret'}, categories=('ZACI',))
    monkeypatch.setattr(legacy_bridge, 'configuration', lambda path: config)
    seen = {}
    def probe(db, password, *, remember):
        seen.update(db=db, password=password, remember=remember)
        return SimpleNamespace(subject_name='Jídelna', database_name='db', categories=(('ZACI','Žáci'),('HOST','Hosté')))
    monkeypatch.setattr(legacy_bridge, 'probe_connection', probe)
    assert legacy_bridge.info('config.json') == {'subject':'Jídelna','categories':[{'code':'ZACI','name':'Žáci'}]}
    assert seen['remember'] is False and 'password' not in seen['db']


def test_legacy_collection_reuses_fetch_and_rejects_unpermitted_category(monkeypatch, tmp_path):
    import sys
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge
    from dataclasses import replace
    from unittest.mock import Mock
    from stravovaci_sestava import AppConfig
    cfg = AppConfig(database={}, report_date=date(2026,11,9), categories=('ZACI',), language='česky', menu_list_number=1)
    monkeypatch.setattr(legacy_bridge, 'configuration', lambda path: cfg)
    report = engine.fetch_collection_period(engine.FixtureCursor(), replace(cfg, report_end_date=date(2026,11,11), collection_status='both'), cfg.categories, 'Test')
    fetch = Mock(return_value=report)
    monkeypatch.setattr(legacy_bridge, 'fetch_report', fetch)
    req = {'start':'2026-11-09','end':'2026-11-11','status':'both','category':'ZACI','config_path':'config.json','action':'legacy_preview'}
    result = legacy_bridge.collection(req, tmp_path)
    assert (result['collected'],result['uncollected']) == (3,3)
    assert fetch.call_args.args[0].categories == ('ZACI',)
    import pytest
    with pytest.raises(ValueError, match='není povolená'):
        legacy_bridge.collection({**req,'category':'HOST'}, tmp_path)


def test_wizard_saves_legacy_profile_and_paused_task(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge
    from services.web_mail_task_store import load_tasks, task_file
    from services.web_daily_profiles import load_profiles, profile_file
    from services.web_mail_worker import tick
    from datetime import datetime
    monkeypatch.setattr(legacy_bridge, 'configuration', lambda path: SimpleNamespace())
    monkeypatch.setattr(legacy_bridge, 'info', lambda path: {'categories':[{'code':'ZACI'},{'code':'HOST'}]})
    data = {'name':'Včerejší odběry','date':date.today().isoformat(),'category':'ZACI','meal':'all',
            'content':'collection','collection':'uncollected','mode':'yesterday','days':'2',
            'output':'email','recipients':'test@example.invalid','time':'08:00','enabled':False,'cooking':True}
    config_path = tmp_path / 'config.json'
    result = legacy_bridge.save_task(str(config_path), data)
    task = load_tasks(task_file(tmp_path))[0]
    profile = load_profiles(profile_file(tmp_path))[0]
    assert not task.enabled and task.profile_id == profile.id
    assert task.day_offset == -1 and task.only_cooking_days
    assert profile.categories == ('ZACI',) and profile.collection_status == 'uncollected'
    assert result['status'] == 'Pozastaveno'
    assert legacy_bridge.tasks(str(config_path))[0]['name'] == data['name']
    calls = []
    monkeypatch.setattr('services.web_mail_worker.dispatch', lambda *args: calls.append(args))
    tick(config_path, datetime.now().replace(hour=23, minute=59))
    assert not calls


def test_wizard_rejects_invalid_values_before_writing(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge
    import pytest
    monkeypatch.setattr(legacy_bridge, 'configuration', lambda path: SimpleNamespace())
    monkeypatch.setattr(legacy_bridge, 'info', lambda path: {'categories':[{'code':'ZACI'}]})
    data = {'name':'Test','date':date.today().isoformat(),'category':'HOST','meal':'all',
            'content':'names','mode':'today','output':'email','recipients':'test@example.invalid','time':'08:00','enabled':False,'cooking':False}
    with pytest.raises(ValueError, match='povolenou kategorii'):
        legacy_bridge.save_task(str(tmp_path / 'config.json'), data)
    assert not list(tmp_path.iterdir())
    data['category'] = 'ZACI'
    data['mode'] = 'yesterday'
    with pytest.raises(ValueError, match='Dny zpět'):
        legacy_bridge.save_task(str(tmp_path / 'config.json'), data)
    assert not list(tmp_path.iterdir())


def test_wizard_enabling_task_does_not_trigger_catchup(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from datetime import datetime
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge
    from services.web_mail_task_store import load_tasks, task_file
    monkeypatch.setattr(legacy_bridge, 'configuration', lambda path: SimpleNamespace())
    monkeypatch.setattr(legacy_bridge, 'info', lambda path: {'categories':[{'code':'ZACI'}]})
    data={'name':'Test','date':date.today().isoformat(),'category':'all','meal':'all',
          'content':'names','mode':'today','output':'email','recipients':'test@example.invalid',
          'time':'00:00','enabled':False,'cooking':False}
    path=str(tmp_path / 'config.json')
    task_id=legacy_bridge.save_task(path, data)['task']['id']
    assert legacy_bridge.set_task_enabled(path,task_id,True)['enabled']
    task=load_tasks(task_file(tmp_path))[0]
    assert task.enabled and date.fromisoformat(task.first_send_date)>date.today()
    assert legacy_bridge.set_task_enabled(path,task_id,False)['enabled'] is False


def test_saved_enabled_task_is_seen_once_per_day_by_legacy_worker(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from datetime import datetime, timedelta
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge
    from services.web_mail_worker import tick
    monkeypatch.setattr(legacy_bridge, 'configuration', lambda path: SimpleNamespace())
    monkeypatch.setattr(legacy_bridge, 'info', lambda path: {'categories':[{'code':'ZACI'}]})
    data={'name':'Test','date':date.today().isoformat(),'category':'all','meal':'all',
          'content':'names','mode':'tomorrow','output':'pdf','directory':str(tmp_path),
          'filename':'Prehled_{date}.pdf','time':'00:00','enabled':True,'cooking':False}
    path=tmp_path / 'config.json'
    task=legacy_bridge.save_task(str(path),data)['task']
    calls=[]
    monkeypatch.setattr('services.web_mail_worker.dispatch', lambda *args: calls.append(args))
    next_day=datetime.combine(date.today()+timedelta(days=1),datetime.min.time()).replace(hour=8)
    tick(path,next_day)
    tick(path,next_day)
    assert len(calls)==1 and calls[0][1].id==task['id']
    assert calls[0][1].output_mode=='pdf'


def test_saved_pdf_task_produces_pdf_through_legacy_worker(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from dataclasses import replace
    from datetime import datetime, timedelta
    from pypdf import PdfReader
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge
    from services import web_mail_worker as worker
    from stravovaci_sestava import AppConfig
    monkeypatch.setattr(legacy_bridge, 'configuration', lambda path: SimpleNamespace())
    monkeypatch.setattr(legacy_bridge, 'info', lambda path: {'categories':[{'code':'ZACI'}]})
    data={'name':'Test PDF','date':date.today().isoformat(),'category':'all','meal':'all',
          'content':'collection','collection':'both','mode':'tomorrow','output':'pdf',
          'directory':str(tmp_path),'filename':'Prehled_{date}.pdf','time':'00:00','enabled':True,'cooking':False}
    path=tmp_path / 'config.json'
    legacy_bridge.save_task(str(path),data)
    cfg=AppConfig(database={}, report_date=date.today(), categories=('ZACI',), language='česky', menu_list_number=1)
    monkeypatch.setattr(worker,'load_config',lambda *args,**kwargs:cfg)
    monkeypatch.setattr(worker,'read_saved_settings',lambda path:{'povolene_kategorie':['ZACI']})
    report=engine.fetch_collection_period(engine.FixtureCursor(),replace(cfg,collection_status='both'),('ZACI',),'Test')
    def fetch(actual):
        assert actual.categories==('ZACI',) and actual.collection_status=='both'
        return report
    monkeypatch.setattr(worker,'fetch_report',fetch)
    sent_on=date.today()+timedelta(days=1)
    worker.tick(path, datetime.combine(sent_on,datetime.min.time()).replace(hour=8))
    pdf=tmp_path / f'Prehled_{(sent_on+timedelta(days=1)).isoformat()}.pdf'
    text='\n'.join(page.extract_text() for page in PdfReader(pdf).pages)
    assert 'Anna Nováková' in text and 'Jan Dvořák' in text
