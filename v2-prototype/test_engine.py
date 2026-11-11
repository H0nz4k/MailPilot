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


def test_wizard_saves_multiple_actual_filters_and_rejects_stale_values(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    import pytest
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge
    from services.web_daily_profiles import load_profiles, profile_file
    monkeypatch.setattr(legacy_bridge, 'configuration', lambda path: SimpleNamespace())
    monkeypatch.setattr(legacy_bridge, 'info', lambda path: {'categories':[{'code':'ZACI'},{'code':'HOST'},{'code':'ZAM'}]})
    monkeypatch.setattr(legacy_bridge, 'filter_options', lambda path, day: {'meals':['Oběd','Večeře'], 'deliveries':['Rozvoz','Jídelna']})
    data={'name':'Filtry','date':date.today().isoformat(),'categories':['ZACI','HOST'],
          'meals':['Oběd','Večeře'],'deliveries':['Rozvoz'],'content':'names','mode':'today',
          'output':'email','recipients':'test@example.invalid','time':'08:00','enabled':False,'cooking':False}
    path=str(tmp_path / 'config.json')
    legacy_bridge.save_task(path,data)
    profile=load_profiles(profile_file(tmp_path))[0]
    assert profile.categories == ('ZACI','HOST')
    assert profile.meal_type == ('oběd','večeře') and profile.delivery_types == ('Rozvoz',)
    with pytest.raises(ValueError,match='dostupnou možnost'):
        legacy_bridge.save_task(path,{**data,'meals':['Smyšlený typ']})
    with pytest.raises(ValueError,match='povolenou kategorii'):
        legacy_bridge.save_task(path,{**data,'categories':['ZACI','NEPOVOLENA']})
    with pytest.raises(ValueError,match='povolenou kategorii'):
        legacy_bridge.save_task(path,{**data,'categories':[]})
    assert len(load_profiles(profile_file(tmp_path))) == 1


def test_wizard_persists_pdf_options_in_profile(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge
    from services.web_daily_profiles import load_profiles, profile_file
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace())
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    data={'name':'PDF','date':date.today().isoformat(),'category':'all','meal':'all','content':'names',
          'mode':'today','output':'email','recipients':'test@example.invalid','time':'08:00',
          'enabled':False,'cooking':False,'category_separation':True,'show_by_categories':False,
          'show_delivery_summary':True,'delivery_page_per_type':True,'pdf_orientation':'na_vysku','pdf_bold':True}
    legacy_bridge.save_task(str(tmp_path/'config.json'),data)
    profile=load_profiles(profile_file(tmp_path))[0]
    assert profile.category_separation and not profile.show_by_categories
    assert profile.show_delivery_summary and profile.delivery_page_per_type
    assert profile.pdf_orientation=='na_vysku' and profile.pdf_bold is True


def test_scheduler_status_reports_observed_worker_and_service_without_control(tmp_path,monkeypatch):
    import sys
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    calls=[]
    monkeypatch.setattr('services.web_worker_status.observed_status',lambda path:'Běh plánovače není potvrzen')
    monkeypatch.setattr('services.web_mail_nssm.scheduler_installation_notice',lambda path:'Chybí služba')
    def command(path,action):
        calls.append(action)
        raise ValueError('NSSM chybí')
    monkeypatch.setattr('services.web_mail_nssm.service_command',command)
    status=legacy_bridge.scheduler_status(str(tmp_path/'config.json'))
    assert calls==['status']
    assert status['worker']=='Běh plánovače není potvrzen'
    assert status['notice']=='Chybí služba' and 'NSSM chybí' in status['service']


def test_edit_task_preserves_profile_and_revalidates_changes(tmp_path,monkeypatch):
    import sys
    import pytest
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    from services.web_mail_task_store import load_tasks,task_file
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace())
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    data={'name':'Původní','date':date.today().isoformat(),'category':'all','meal':'all','content':'names',
          'mode':'today','output':'email','recipients':'a@example.invalid','time':'08:00','enabled':False,'cooking':True}
    path=str(tmp_path/'config.json')
    before=legacy_bridge.save_task(path,data)['task']
    legacy_bridge.update_task(path,before['id'],{'name':'Nový název','send_time':'09:15','recipients':['b@example.invalid']})
    after=load_tasks(task_file(tmp_path))[0]
    assert after.name=='Nový název' and after.send_time=='09:15' and after.recipients==('b@example.invalid',)
    assert after.id==before['id'] and after.profile_id==before['profile_id']
    assert not after.enabled and after.only_cooking_days
    with pytest.raises(ValueError):
        legacy_bridge.update_task(path,before['id'],{'recipients':['invalid']})
    with pytest.raises(ValueError):
        legacy_bridge.update_task(path,before['id'],{'date_mode':'offset','day_offset':-1})
    assert load_tasks(task_file(tmp_path))[0] == after


def test_scheduler_control_checks_worker_and_config_before_action(tmp_path, monkeypatch):
    import sys
    import pytest
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    import services.web_mail_nssm as nssm
    from services.web_branding import WORKER_EXE_NAME
    path=tmp_path/'config.json'
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace())
    monkeypatch.setattr(nssm,'_service_setup',lambda directory:(tmp_path/'nssm.exe','DataShipWorker'))
    commands=[]
    def call(args):
        commands.append(args)
        if args[-1]=='Application': return str(tmp_path/WORKER_EXE_NAME)
        if args[-1]=='AppParameters': return f'--config "{path}"'
        raise AssertionError(args)
    monkeypatch.setattr(nssm,'_run_nssm',call)
    monkeypatch.setattr(nssm,'require_service_rights',lambda action:None)
    changes=[]
    monkeypatch.setattr(nssm,'service_command',lambda directory,action:changes.append(action) or 'OK')
    assert legacy_bridge.control_scheduler(str(path),'start')['message']=='OK'
    assert changes==['start']
    monkeypatch.setattr(nssm,'_run_nssm',lambda args: 'other.exe')
    with pytest.raises(ValueError,match='zůstala beze změny'):
        legacy_bridge.control_scheduler(str(path),'stop')
    assert changes==['start']
    with pytest.raises(ValueError,match='Neznámá'):
        legacy_bridge.control_scheduler(str(path),'install')


def test_wizard_preview_generates_pdf_without_saving_task(tmp_path,monkeypatch):
    import sys
    from dataclasses import replace
    from pypdf import PdfReader
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    import automaticky_export
    from stravovaci_sestava import AppConfig
    from services.web_mail_task_store import task_file
    from services.web_daily_profiles import profile_file
    config=AppConfig(database={},report_date=date.today(),categories=('ZACI',),language='česky',menu_list_number=1)
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:config)
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    monkeypatch.setattr(automaticky_export,'read_saved_settings',lambda path:{'povolene_kategorie':['ZACI']})
    sample=engine.fetch_collection_period(engine.FixtureCursor(),replace(config,collection_status='both'),('ZACI',),'Test')
    seen=[]
    monkeypatch.setattr(legacy_bridge,'fetch_report',lambda c:seen.append(c) or sample)
    data={'name':'Náhled','date':date.today().isoformat(),'category':'all','content':'collection','collection':'both','show_by_categories':False}
    result=legacy_bridge.preview_wizard(str(tmp_path/'config.json'),data,tmp_path/'output')
    assert result['portions']==2 and seen[0].collection_status=='both' and not seen[0].show_by_categories
    text='\n'.join(page.extract_text() for page in PdfReader(result['pdf']).pages)
    assert 'Anna Nováková' in text and 'Jan Dvořák' in text
    assert not task_file(tmp_path).exists() and not profile_file(tmp_path).exists()


def test_concurrent_v2_task_creation_keeps_all_tasks(tmp_path, monkeypatch):
    import sys
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    from services.web_mail_task_store import load_tasks,task_file
    from services.web_daily_profiles import load_profiles,profile_file
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace())
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    data={'date':date.today().isoformat(),'category':'all','content':'names', 'mode':'today',
          'output':'email','recipients':'a@example.invalid','time':'08:00','enabled':False,'cooking':False}
    path=str(tmp_path/'config.json')
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda i:legacy_bridge.save_task(path,{**data,'name':f'Úloha {i}'}),range(12)))
    tasks=load_tasks(task_file(tmp_path))
    profiles=load_profiles(profile_file(tmp_path))
    assert len(tasks)==len(profiles)==12
    assert {t.name for t in tasks} == {f'Úloha {i}' for i in range(12)}
    assert {t.profile_id for t in tasks} == {p.id for p in profiles}


def test_stale_task_revision_is_rejected(tmp_path, monkeypatch):
    import sys
    import pytest
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace())
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    data={'name':'Původní','date':date.today().isoformat(),'category':'all','content':'names','mode':'today',
          'output':'email','recipients':'a@example.invalid','time':'08:00','enabled':False,'cooking':False}
    path=str(tmp_path/'config.json')
    task_id=legacy_bridge.save_task(path,data)['task']['id']
    revision=legacy_bridge.tasks(path)[0]['revision']
    legacy_bridge.update_task(path,task_id,{'name':'Změněno'},revision)
    with pytest.raises(ValueError,match='mezitím změnila'):
        legacy_bridge.update_task(path,task_id,{'name':'Zastaralý návrh'},revision)
    with pytest.raises(ValueError,match='mezitím změnila'):
        legacy_bridge.set_task_enabled(path,task_id,True,revision)
    assert legacy_bridge.tasks(path)[0]['name']=='Změněno'


def test_edit_wizard_preserves_other_tasks_and_unexposed_profile_settings(tmp_path, monkeypatch):
    import sys
    from dataclasses import replace
    from types import SimpleNamespace
    import pytest
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    from services.web_daily_profiles import load_profiles, profile_file, save_profile
    from services.web_mail_task_store import load_tasks, save_tasks, task_file
    from services.web_mail_tasks import MailTask
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace())
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'},{'code':'HOST'}]})
    monkeypatch.setattr(legacy_bridge,'filter_options',lambda path,day:{'meals':['Oběd'],'deliveries':['Rozvoz']})
    data={'name':'Původní','date':date.today().isoformat(),'categories':['ZACI'],'meals':['Oběd'],
          'deliveries':['Rozvoz'],'content':'names','mode':'today','output':'email',
          'recipients':'a@example.invalid','time':'08:00','enabled':False,'cooking':False}
    path=str(tmp_path/'config.json')
    task=legacy_bridge.save_task(path,data)['task']
    old=load_profiles(profile_file(tmp_path))[0]
    save_profile(profile_file(tmp_path),replace(old,pdf_data_font_size=11,pdf_label_font_size=10,language='česky'))
    other=MailTask.from_dict({**task,'id':'shared-other','name':'Druhá úloha'})
    save_tasks(task_file(tmp_path),load_tasks(task_file(tmp_path))+[other])
    edit=legacy_bridge.wizard_edit_data(path,task['id'])
    update={**edit['data'],'name':'Upravený','categories':['HOST'],'edit_id':edit['id'],
            'revision':edit['revision'],'profile_revision':edit['profile_revision']}
    legacy_bridge.save_task(path,update)
    tasks=load_tasks(task_file(tmp_path))
    changed=next(t for t in tasks if t.id==task['id'])
    assert changed.name=='Upravený' and changed.profile_id!=old.id
    assert next(t for t in tasks if t.id==other.id).profile_id==old.id
    new=next(p for p in load_profiles(profile_file(tmp_path)) if p.id==changed.profile_id)
    assert new.categories==('HOST',) and new.pdf_data_font_size==11 and new.pdf_label_font_size==10
    assert new.language=='česky' and new.delivery_types==('Rozvoz',)
    with pytest.raises(ValueError,match='mezitím změnila'):
        legacy_bridge.save_task(path,update)


def test_edit_wizard_rejects_profile_changed_since_load(tmp_path, monkeypatch):
    import sys
    import pytest
    from dataclasses import replace
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    from services.web_daily_profiles import load_profiles,profile_file,save_profile
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace())
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    monkeypatch.setattr(legacy_bridge,'filter_options',lambda path,day:{'meals':[], 'deliveries':[]})
    data={'name':'Test','date':date.today().isoformat(),'category':'all','content':'names','mode':'today',
          'output':'email','recipients':'a@example.invalid','time':'08:00','enabled':False,'cooking':False}
    path=str(tmp_path/'config.json')
    task=legacy_bridge.save_task(path,data)['task']
    edit=legacy_bridge.wizard_edit_data(path,task['id'])
    profile=load_profiles(profile_file(tmp_path))[0]
    save_profile(profile_file(tmp_path),replace(profile,pdf_data_font_size=12))
    with pytest.raises(ValueError,match='Profil úlohy se mezitím změnil'):
        legacy_bridge.save_task(path,{**edit['data'],'edit_id':edit['id'],'revision':edit['revision'], 'profile_revision':edit['profile_revision']})


def test_edit_preview_preserves_unexposed_pdf_options(tmp_path, monkeypatch):
    import sys
    from dataclasses import replace
    import automaticky_export
    from stravovaci_sestava import AppConfig
    from services.web_daily_profiles import load_profiles,profile_file,save_profile
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    cfg=AppConfig(database={},report_date=date.today(),categories=('ZACI',),language='česky',menu_list_number=1)
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:cfg)
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    monkeypatch.setattr(legacy_bridge,'filter_options',lambda path,day:{'meals':[],'deliveries':[]})
    monkeypatch.setattr(automaticky_export,'read_saved_settings',lambda path:{'povolene_kategorie':['ZACI']})
    data={'name':'Test','date':date.today().isoformat(),'category':'all','content':'collection','collection':'both',
          'mode':'today','output':'email','recipients':'a@example.invalid','time':'08:00','enabled':False,'cooking':False}
    path=str(tmp_path/'config.json')
    task=legacy_bridge.save_task(path,data)['task']
    profile=load_profiles(profile_file(tmp_path))[0]
    save_profile(profile_file(tmp_path),replace(profile,pdf_data_font_size=11))
    edit=legacy_bridge.wizard_edit_data(path,task['id'])
    sample=engine.fetch_collection_period(engine.FixtureCursor(),replace(cfg,collection_status='both'),('ZACI',),'Test')
    seen=[]
    monkeypatch.setattr(legacy_bridge,'fetch_report',lambda actual:seen.append(actual) or sample)
    request={**edit['data'],'edit_id':edit['id'],'revision':edit['revision'],'profile_revision':edit['profile_revision']}
    legacy_bridge.preview_wizard(path,request,tmp_path/'output')
    assert seen[0].pdf_data_font_size==11
    assert len(load_profiles(profile_file(tmp_path)))==1


def test_delete_task_rejects_stale_revision_and_keeps_shared_profile(tmp_path, monkeypatch):
    import sys
    import pytest
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    from services.web_daily_profiles import load_profiles, profile_file
    from services.web_mail_task_store import load_tasks, task_file, save_tasks
    from services.web_mail_tasks import MailTask
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace())
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    data={'name':'První','date':date.today().isoformat(),'category':'all','content':'names','mode':'today',
          'output':'email','recipients':'a@example.invalid','time':'08:00','enabled':False,'cooking':False}
    path=str(tmp_path/'config.json')
    first=legacy_bridge.save_task(path,data)['task']
    other=MailTask.from_dict({**first,'id':'other','name':'Druhá'})
    save_tasks(task_file(tmp_path),load_tasks(task_file(tmp_path))+[other])
    first_row=next(t for t in legacy_bridge.tasks(path) if t['id']==first['id'])
    with pytest.raises(ValueError,match='mezitím změnila'):
        legacy_bridge.delete_task(path,first['id'],'stale')
    legacy_bridge.delete_task(path,first['id'],first_row['revision'])
    assert [t.id for t in load_tasks(task_file(tmp_path))]==['other']
    assert load_profiles(profile_file(tmp_path))[0].id==other.profile_id


def test_workspace_import_preserves_source_and_pauses_all_tasks(tmp_path, monkeypatch):
    import sys
    import json
    from types import SimpleNamespace
    from services.web_mail_task_store import load_tasks,task_file
    from services.web_daily_profiles import load_profiles,profile_file
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    import workspace_import
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace())
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    source=tmp_path/'original'
    source.mkdir()
    config=source/'config.json'
    config.write_text(json.dumps({'databaze':{'host':'localhost','password':'not-real'},'resend_api_key':'not-real'}),encoding='utf-8')
    data={'name':'Test','date':date.today().isoformat(),'category':'all','content':'names','mode':'today',
          'output':'email','recipients':'a@example.invalid','time':'08:00','enabled':True,'cooking':False}
    legacy_bridge.save_task(str(config),data)
    original_config=config.read_bytes()
    original_tasks=task_file(source).read_bytes()
    target=tmp_path/'new'/'workspace'
    result=workspace_import.import_workspace(str(config),target)
    assert result['tasks']==1 and result['profiles']==1
    assert load_tasks(task_file(target))[0].enabled is False
    assert load_profiles(profile_file(target))[0].id==load_tasks(task_file(target))[0].profile_id
    assert config.read_bytes()==original_config and task_file(source).read_bytes()==original_tasks
    migrated=json.loads((target/'config.json').read_text(encoding='utf-8'))
    assert 'password' not in migrated['databaze'] and 'resend_api_key' not in migrated
    settings=json.loads((target/'web_mail_settings.json').read_text(encoding='utf-8'))
    assert settings['service_name']=='DataShip2Scheduler'
    import pytest
    with pytest.raises(ValueError,match='nepřepíše'):
        workspace_import.import_workspace(str(config),target)
    assert task_file(source).read_bytes()==original_tasks


def test_workspace_import_refuses_missing_profile_without_creating_destination(tmp_path):
    import json
    import pytest
    import sys
    from services.web_mail_tasks import MailTask
    from services.web_mail_task_store import save_tasks,task_file
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import workspace_import
    source=tmp_path/'original'
    source.mkdir()
    config=source/'config.json'
    config.write_text(json.dumps({'databaze':{}}),encoding='utf-8')
    task=MailTask.from_dict({'name':'Test','recipients':['a@example.invalid'],'send_time':'08:00',
                            'date_mode':'today','profile_id':'missing'})
    save_tasks(task_file(source),[task])
    target=tmp_path/'new'/'workspace'
    with pytest.raises(ValueError,match='chybějící profil'):
        workspace_import.import_workspace(str(config),target)
    assert not target.exists()


def test_install_v2_scheduler_is_stopped_and_restricted_to_workspace(tmp_path,monkeypatch):
    import sys
    import pytest
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    import services.web_mail_nssm as nssm
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    config=workspace/'config.json'
    config.touch()
    worker=tmp_path/'dataship-v2-engine.exe'
    worker.touch()
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace())
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'executable',str(worker))
    monkeypatch.setattr(nssm,'_service_setup',lambda path:(tmp_path/'nssm.exe','DataShip2Scheduler'))
    monkeypatch.setattr(nssm,'require_service_rights',lambda action:None)
    commands=[]
    monkeypatch.setattr(nssm,'_run_nssm',lambda command:commands.append(command) or '')
    result=legacy_bridge.install_scheduler(str(config),str(workspace))
    assert 'zůstává zastavená' in result['message']
    assert commands[0]==[str(tmp_path/'nssm.exe'),'install','DataShip2Scheduler',str(worker),'--worker','--config',str(config)]
    assert not any(c[1]=='start' for c in commands)
    with pytest.raises(ValueError,match='oddělený prostor'):
        legacy_bridge.install_scheduler(str(tmp_path/'other'/'config.json'),str(workspace))


def test_v2_worker_lock_blocks_second_worker_process(tmp_path):
    import sys, subprocess, os
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    from task_lock import task_store_lock
    script=Path(__file__).parent/'backend'/'engine.py'
    with task_store_lock(tmp_path, name='.dataship-v2-worker.lock'):
        result=subprocess.run([sys.executable,str(script),'--worker','--config',str(tmp_path/'config.json')],
                              capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,
                              env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    assert result.returncode != 0 and 'již běží jiný worker' in result.stderr


def test_remove_scheduler_only_verified_v2_and_preserves_files(tmp_path,monkeypatch):
    import sys
    import pytest
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    import services.web_mail_nssm as nssm
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    config=workspace/'config.json'
    config.touch()
    monkeypatch.setattr(legacy_bridge,'registered_scheduler',lambda path:(tmp_path/'nssm.exe','DataShip2Scheduler','dataship-v2-engine.exe'))
    monkeypatch.setattr(nssm,'require_service_rights',lambda action:None)
    commands=[]
    monkeypatch.setattr(nssm,'_run_nssm',lambda cmd:commands.append(cmd) or ('SERVICE_STOPPED' if cmd[1]=='status' else ''))
    assert 'úlohy a nastavení zůstaly' in legacy_bridge.remove_scheduler(str(config),str(workspace))['message']
    assert [c[1] for c in commands]==['status','remove'] and config.exists()
    monkeypatch.setattr(legacy_bridge,'registered_scheduler',lambda path:(tmp_path/'nssm.exe','DataShip2Scheduler','dataship-worker.exe'))
    with pytest.raises(ValueError,match='nebyla změněna'):
        legacy_bridge.remove_scheduler(str(config),str(workspace))
    assert len(commands)==2


def test_repair_scheduler_requires_stopped_v2_and_does_not_start(tmp_path,monkeypatch):
    import sys
    import pytest
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    import services.web_mail_nssm as nssm
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    config=workspace/'config.json'
    config.touch()
    worker=tmp_path/'dataship-v2-engine.exe'
    worker.touch()
    monkeypatch.setattr(sys,'executable',str(worker))
    monkeypatch.setattr(legacy_bridge,'registered_scheduler',lambda path,allow_moved:(tmp_path/'nssm.exe','DataShip2Scheduler','dataship-v2-engine.exe'))
    monkeypatch.setattr(nssm,'require_service_rights',lambda action:None)
    commands=[]
    monkeypatch.setattr(nssm,'_run_nssm',lambda cmd:commands.append(cmd) or ('SERVICE_STOPPED' if cmd[1]=='status' else ''))
    assert 'zůstává zastavená' in legacy_bridge.repair_scheduler(str(config),str(workspace))['message']
    assert [c[1] for c in commands]==['status','config','set','set','set']
    assert all(c[1] not in ('start','stop','remove','install') for c in commands)
    commands.clear()
    monkeypatch.setattr(nssm,'_run_nssm',lambda cmd:commands.append(cmd) or 'SERVICE_RUNNING')
    with pytest.raises(ValueError,match='zastavte'):
        legacy_bridge.repair_scheduler(str(config),str(workspace))
    assert [c[1] for c in commands]==['status']


def test_one_off_collection_email_uses_selected_dates_without_scheduling(tmp_path,monkeypatch):
    import sys
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    import automaticky_export
    import services.web_mail_settings as settings
    import services.web_mail_smtp as smtp
    config=tmp_path/'config.json'
    config.touch()
    pdf=tmp_path/'report.pdf'
    pdf.write_bytes(b'%PDF-test')
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace())
    monkeypatch.setattr(automaticky_export,'read_saved_settings',lambda path:{})
    monkeypatch.setattr(settings,'load_settings',lambda path:{'transport':'smtp',
        'subject_template':'{report}: {date}','body_template':'{report} {date}'})
    requests=[]
    monkeypatch.setattr(legacy_bridge,'collection',lambda req,out:requests.append(req) or {'pdf':str(pdf),'collected':2,'uncollected':1,'rows':[]})
    sent=[]
    monkeypatch.setattr(smtp,'smtp_send',lambda *args:sent.append(args))
    request={'config_path':str(config),'start':'2026-11-01','end':'2026-11-03',
             'status':'both','category':'ZACI','recipients':['a@example.invalid','a@example.invalid']}
    result=legacy_bridge.send_collection(request,tmp_path)
    assert result['sent']==1 and len(sent)==1
    assert sent[0][1]==('a@example.invalid',) and '01.11.2026 – 03.11.2026' in sent[0][2]
    assert requests[0]['action']=='legacy_pdf' and requests[0]['category']=='ZACI'
    assert not (tmp_path/'web_mail_tasks.json').exists()


def test_one_off_collection_email_rejects_invalid_recipient_before_pdf(tmp_path,monkeypatch):
    import sys, pytest
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    monkeypatch.setattr(legacy_bridge,'collection',lambda *args:pytest.fail('PDF should not be generated'))
    with pytest.raises(ValueError):
        legacy_bridge.send_collection({'config_path':str(tmp_path/'config.json'),'recipients':['invalid']},tmp_path)


def test_save_pdf_never_overwrites_and_only_copies_generated_files(tmp_path):
    import sys
    import pytest
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    output=tmp_path/'generated'
    output.mkdir()
    source=output/'report.pdf'
    source.write_bytes(b'%PDF-example')
    target=tmp_path/'saved.pdf'
    result=legacy_bridge.save_pdf(str(source),str(target),str(output))
    assert Path(result['path']).read_bytes()==b'%PDF-example'
    with pytest.raises(ValueError,match='již existuje'):
        legacy_bridge.save_pdf(str(source),str(target),str(output))
    assert target.read_bytes()==b'%PDF-example'
    with pytest.raises(ValueError,match='vytvořené'):
        legacy_bridge.save_pdf(str(target),str(tmp_path/'second.pdf'),str(output))
    with pytest.raises(ValueError,match='úplnou cestu'):
        legacy_bridge.save_pdf(str(source),'relative.pdf',str(output))


def test_collection_period_multiple_filters_are_applied_and_validated(tmp_path,monkeypatch):
    import sys, pytest
    from dataclasses import replace
    from stravovaci_sestava import AppConfig
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    cfg=AppConfig(database={},report_date=date(2026,12,31),categories=('ZACI','HOST'),language='česky',menu_list_number=1)
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:cfg)
    monkeypatch.setattr(legacy_bridge,'period_filter_options',lambda *args:{'meals':['Oběd','Večeře'],'deliveries':['Rozvoz']})
    sample=engine.fetch_collection_period(engine.FixtureCursor(),replace(cfg,report_end_date=date(2027,1,1),collection_status='both'),cfg.categories,'Test')
    seen=[]
    monkeypatch.setattr(legacy_bridge,'fetch_report',lambda actual:seen.append(actual) or sample)
    req={'config_path':'config.json','start':'2026-12-31','end':'2027-01-01','status':'both',
         'categories':['ZACI','HOST'],'meals':['Oběd','Večeře'],'deliveries':['Rozvoz'],'show_by_categories':False}
    legacy_bridge.collection(req,tmp_path)
    actual=seen[0]
    assert actual.categories==('ZACI','HOST') and actual.meal_type==['Oběd','Večeře']
    assert actual.delivery_types==('Rozvoz',) and not actual.show_by_categories
    with pytest.raises(ValueError,match='není povolená'):
        legacy_bridge.collection({**req,'categories':['ZACI','NEPOVOLENA']},tmp_path)
    with pytest.raises(ValueError,match='dostupnou možnost'):
        legacy_bridge.collection({**req,'meals':['neexistuje']},tmp_path)
    assert len(seen)==1


def test_period_filter_options_includes_both_years(monkeypatch):
    import sys
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    import stravovaci_sestava as reports
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace(database={}))
    years=[]
    monkeypatch.setattr(reports,'available_meal_types',lambda db,day:years.append(day.year) or (f'Jídlo {day.year}',))
    monkeypatch.setattr(reports,'available_delivery_types',lambda db:('Rozvoz',))
    result=legacy_bridge.period_filter_options('config.json','2026-12-31','2027-01-01')
    assert years==[2026,2027] and result['meals']==['Jídlo 2026','Jídlo 2027']
    assert result['deliveries']==['Rozvoz']


def test_schedule_preview_uses_real_calendar_lookup_without_saving(tmp_path,monkeypatch):
    import sys
    from contextlib import contextmanager
    from types import SimpleNamespace
    from datetime import datetime, timedelta
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    import services.web_mail_cooking_days as calendar
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace(database={'mock':True}))
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    lookups=[]
    @contextmanager
    def fake(db):
        lookups.append(db)
        yield lambda day: day.weekday()<5
    monkeypatch.setattr(calendar,'any_cooking_day_lookup',fake)
    data={'name':'Test','date':date.today().isoformat(),'category':'all','content':'names',
          'mode':'next_cooking_day','time':'08:00','enabled':False,'cooking':True}
    result=legacy_bridge.preview_schedule(str(tmp_path/'config.json'),data)
    scheduled=datetime.fromisoformat(result['next_run']).date()
    report=date.fromisoformat(result['next_report'])
    expected=scheduled+timedelta(days=1)
    while expected.weekday()>=5: expected+=timedelta(days=1)
    assert report==expected and result['only_cooking_days'] is True
    assert lookups==[{'mock':True}] and not list(tmp_path.iterdir())


def test_schedule_preview_negative_days_require_collection(tmp_path,monkeypatch):
    import sys, pytest
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace(database={}))
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    data={'name':'Test','date':date.today().isoformat(),'category':'all','content':'names',
          'mode':'history','days':'2','time':'08:00','enabled':False,'cooking':False}
    with pytest.raises(ValueError,match='Dny zpět'):
        legacy_bridge.preview_schedule(str(tmp_path/'config.json'),data)


def test_workspace_import_preserves_pdf_templates_and_recipient_history(tmp_path):
    import sys, json
    from services.pdf_templates import PdfTemplate, save_template, template_file, load_templates
    from services.web_recipient_history import save_recipient_history, load_recipient_history
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import workspace_import
    source=tmp_path/'old'
    source.mkdir()
    (source/'config.json').write_text(json.dumps({'databaze':{}}),encoding='utf-8')
    template=PdfTemplate.from_dict({'name':'Tisk kuchyně','settings':{}})
    save_template(template_file(source),template)
    save_recipient_history(source,['a@example.invalid'])
    target=tmp_path/'new'/'workspace'
    result=workspace_import.import_workspace(str(source/'config.json'),target)
    assert result['templates']==1
    assert load_templates(template_file(target))[0] == template
    assert load_recipient_history(target)==['a@example.invalid']


def test_wizard_applies_template_and_preserves_hidden_pdf_settings(tmp_path,monkeypatch):
    import sys, pytest
    from types import SimpleNamespace
    from services.pdf_templates import PdfTemplate,save_template,template_file
    from services.web_daily_profiles import load_profiles,profile_file
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace())
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    template=PdfTemplate.from_dict({'name':'Tisk kuchyně','settings':{'pdf_data_font_size':12,'pdf_label_font_size':11,'pdf_orientation':'na_sirku','pdf_bold':True}})
    save_template(template_file(tmp_path),template)
    data={'name':'Podle šablony','date':date.today().isoformat(),'category':'all','content':'names','mode':'today',
          'output':'email','recipients':'a@example.invalid','time':'08:00','enabled':False,'cooking':False,
          'pdf_template_id':template.id,'pdf_orientation':'na_sirku','pdf_bold':True}
    path=str(tmp_path/'config.json')
    assert legacy_bridge.pdf_templates(path)[0]['id']==template.id
    legacy_bridge.save_task(path,data)
    profile=load_profiles(profile_file(tmp_path))[0]
    assert profile.pdf_data_font_size==12 and profile.pdf_label_font_size==11
    assert profile.pdf_orientation=='na_sirku' and profile.pdf_bold is True
    with pytest.raises(ValueError,match='Šablona PDF již neexistuje'):
        legacy_bridge.save_task(path,{**data,'pdf_template_id':'missing'})


def test_settings_requires_admin_and_never_returns_secret_values(tmp_path,monkeypatch):
    import sys,json,pytest
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import settings_bridge, credential_store, env_store
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    config=workspace/'config.json'
    config.write_text(json.dumps({'databaze':{'host':'localhost','port':5432,'dbname':'db','user':'user'}}),encoding='utf-8')
    (workspace/'web_mail_settings.json').write_text(json.dumps({'smtp_password':'not-real-secret'}),encoding='utf-8')
    monkeypatch.setattr(credential_store,'get_admin_password',lambda:'heslo')
    monkeypatch.setattr(env_store,'get_resend_api_key',lambda:'not-real-key')
    with pytest.raises(ValueError,match='Nesprávné heslo'):
        settings_bridge.read_settings(str(config),str(workspace),'bad')
    result=settings_bridge.read_settings(str(config),str(workspace),'heslo')
    assert result['resend_key_present'] is True
    assert 'not-real-secret' not in str(result) and 'not-real-key' not in str(result)
    with pytest.raises(ValueError,match='odděleném prostoru'):
        settings_bridge.read_settings(str(config),str(tmp_path/'other'),'heslo')


def test_mail_settings_validates_and_never_serializes_api_key(tmp_path,monkeypatch):
    import sys,json,pytest
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import settings_bridge, credential_store, env_store
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    config=workspace/'config.json'
    config.write_text('{}',encoding='utf-8')
    monkeypatch.setattr(credential_store,'get_admin_password',lambda:'heslo')
    keys=[]
    monkeypatch.setattr(env_store,'set_resend_api_key',lambda key:keys.append(key))
    changes={'transport':'resend','from_email':'test@example.invalid','smtp_port':587,'smtp_security':'starttls'}
    settings_bridge.save_mail(str(config),str(workspace),'heslo',changes,'not-real-key')
    raw=(workspace/'web_mail_settings.json').read_text(encoding='utf-8')
    assert 'not-real-key' not in raw and keys==['not-real-key']
    assert json.loads(raw)['service_name']=='DataShip2Scheduler'
    with pytest.raises(ValueError,match='STARTTLS'):
        settings_bridge.save_mail(str(config),str(workspace),'heslo',{**changes,'transport':'smtp','smtp_security':'none'})
    with pytest.raises(ValueError,match='Neplatné nastavení'):
        settings_bridge.save_mail(str(config),str(workspace),'heslo',{'service_name':'Other'})


def test_settings_unset_admin_and_key_failure_are_explicit(tmp_path,monkeypatch):
    import sys,pytest
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import settings_bridge,credential_store,env_store
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    config=workspace/'config.json'
    config.write_text('{}',encoding='utf-8')
    monkeypatch.setattr(credential_store,'get_admin_password',lambda:None)
    with pytest.raises(ValueError,match='nastavené'):
        settings_bridge.read_settings(str(config),str(workspace),'anything')
    monkeypatch.setattr(credential_store,'get_admin_password',lambda:'heslo')
    def fail_key(value): raise env_store.EnvStoreError('detail')
    monkeypatch.setattr(env_store,'set_resend_api_key',fail_key)
    with pytest.raises(ValueError,match='uloženo, ale API klíč'):
        settings_bridge.save_mail(str(config),str(workspace),'heslo',{'transport':'resend'},'not-real-key')
    assert (workspace/'web_mail_settings.json').exists()


def test_database_settings_test_connection_before_saving_without_secrets(tmp_path,monkeypatch):
    import sys,json
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import settings_bridge,credential_store
    import services.database as database_service
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    config=workspace/'config.json'
    config.write_text(json.dumps({'databaze':{'host':'old','port':5432,'dbname':'old','user':'old'},'other':123}),encoding='utf-8')
    monkeypatch.setattr(credential_store,'get_admin_password',lambda:'admin')
    stored=[]
    monkeypatch.setattr(credential_store,'set_password',lambda db,pwd:stored.append((db,pwd)))
    calls=[]
    monkeypatch.setattr(database_service,'probe_connection',lambda db,pwd,remember: calls.append((db,pwd,remember)) or SimpleNamespace(subject_name='Jídelna',database_name='new'))
    values={'host':'db-host','port':'5433','dbname':'new','user':'reader','sslmode':'prefer'}
    result=settings_bridge.save_connection(str(config),str(workspace),'admin',values,'not-real-password')
    assert result=={'saved':True,'subject':'Jídelna'}
    assert calls[0][2] is False and stored[0][1]=='not-real-password'
    raw=json.loads(config.read_text(encoding='utf-8'))
    assert raw['databaze']['host']=='db-host' and raw['other']==123
    assert 'not-real-password' not in str(raw)


def test_database_settings_connection_failure_never_writes(tmp_path,monkeypatch):
    import sys,json,pytest
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import settings_bridge,credential_store
    import services.database as database_service
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    config=workspace/'config.json'
    original=json.dumps({'databaze':{'host':'old'}})
    config.write_text(original,encoding='utf-8')
    monkeypatch.setattr(credential_store,'get_admin_password',lambda:'admin')
    monkeypatch.setattr(credential_store,'set_password',lambda *a:pytest.fail('password must not be saved'))
    def fail(*args,**kwargs):raise ValueError('Připojení selhalo')
    monkeypatch.setattr(database_service,'probe_connection',fail)
    with pytest.raises(ValueError,match='Připojení selhalo'):
        settings_bridge.save_connection(str(config),str(workspace),'admin',{'host':'new','port':5432,'dbname':'db','user':'user'},'not-real')
    assert config.read_text(encoding='utf-8')==original


def test_category_permissions_are_saved_and_unknown_codes_rejected(tmp_path,monkeypatch):
    import sys,json,pytest
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import settings_bridge,legacy_bridge,credential_store
    import services.database as database_service
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    config=workspace/'config.json'
    config.write_text(json.dumps({'databaze':{},'poctyemailem':{'untouched':123}}),encoding='utf-8')
    monkeypatch.setattr(credential_store,'get_admin_password',lambda:'admin')
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace(database={'password':'not-real'}))
    monkeypatch.setattr(database_service,'probe_connection',lambda db,pwd,remember:SimpleNamespace(categories=(('ZACI','Žáci'),('HOST','Hosté'))))
    options=settings_bridge.category_settings(str(config),str(workspace),'admin')
    assert options['all'] and len(options['available'])==2
    settings_bridge.save_category_settings(str(config),str(workspace),'admin',False,['ZACI'])
    raw=json.loads(config.read_text(encoding='utf-8'))
    assert raw['poctyemailem']=={'untouched':123,'vsechny_kategorie':False,'povolene_kategorie':['ZACI']}
    with pytest.raises(ValueError,match='dostupnou kategorii'):
        settings_bridge.save_category_settings(str(config),str(workspace),'admin',False,['UNKNOWN'])
    with pytest.raises(ValueError,match='dostupnou kategorii'):
        settings_bridge.save_category_settings(str(config),str(workspace),'admin',False,[])
    assert json.loads(config.read_text(encoding='utf-8'))==raw


def test_initialize_and_change_admin_password_with_existing_password_guard(tmp_path,monkeypatch):
    import sys,pytest
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import settings_bridge,credential_store
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    config=workspace/'config.json'
    config.touch()
    state={'password':None}
    monkeypatch.setattr(credential_store,'get_admin_password',lambda:state['password'])
    monkeypatch.setattr(credential_store,'set_admin_password',lambda value:state.update(password=value))
    assert not settings_bridge.admin_password_status(str(config),str(workspace))['configured']
    with pytest.raises(ValueError,match='shodné'):
        settings_bridge.initialize_admin_password(str(config),str(workspace),'abcd','different')
    settings_bridge.initialize_admin_password(str(config),str(workspace),'abcd','abcd')
    with pytest.raises(ValueError,match='již existuje'):
        settings_bridge.initialize_admin_password(str(config),str(workspace),'other','other')
    with pytest.raises(ValueError,match='Nesprávné'):
        settings_bridge.change_admin_password(str(config),str(workspace),'wrong','novéheslo','novéheslo')
    settings_bridge.change_admin_password(str(config),str(workspace),'abcd','novéheslo','novéheslo')
    assert state['password']=='novéheslo'


def test_create_workspace_validates_before_writing_and_starts_no_tasks(tmp_path,monkeypatch):
    import sys,json,pytest
    from types import SimpleNamespace
    from services.web_mail_task_store import load_tasks,task_file
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import workspace_import,credential_store
    import services.database as database_service
    state={'admin':None,'db':[]}
    monkeypatch.setattr(credential_store,'get_admin_password',lambda:state['admin'])
    monkeypatch.setattr(credential_store,'set_admin_password',lambda value:state.update(admin=value))
    monkeypatch.setattr(credential_store,'set_password',lambda db,pwd:state['db'].append((db,pwd)))
    calls=[]
    monkeypatch.setattr(database_service,'probe_connection',lambda db,pwd,remember:calls.append((db,pwd,remember)) or SimpleNamespace(subject_name='Test',database_name='db'))
    target=tmp_path/'workspace'
    values={'host':'db-host','port':5432,'dbname':'db','user':'reader'}
    with pytest.raises(ValueError,match='shodné'):
        workspace_import.create_workspace(target,values,'not-real','admin','other')
    assert not target.exists() and not state['db'] and state['admin'] is None
    result=workspace_import.create_workspace(target,values,'not-real','admin','admin')
    assert result['subject']=='Test' and state['admin']=='admin' and calls[0][2] is False
    assert load_tasks(task_file(target))==[]
    config=(target/'config.json').read_text(encoding='utf-8')
    assert 'not-real' not in config and json.loads(config)['databaze']['host']=='db-host'
    with pytest.raises(ValueError,match='již existuje'):
        workspace_import.create_workspace(target,values,'another','admin','admin')
    assert len(state['db'])==1


def test_closing_generation_forces_no_mail_and_preserves_source(tmp_path,monkeypatch):
    import sys,json
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import closing_bridge
    source=tmp_path/'config.json'
    source.write_text(json.dumps({'databaze':{},'uzaverka':{'odeslat_mail':True,'vsechny_kategorie':True}}),encoding='utf-8')
    original=source.read_bytes()
    seen=[]
    def fake_run(path,*,year,month):
        raw=json.loads(path.read_text(encoding='utf-8'))
        seen.append(raw)
        dest=Path(raw['uzaverka']['vystup'])
        return SimpleNamespace(status='exported',files=(dest/'report.pdf',),attachments=(),detail='OK')
    monkeypatch.setattr(closing_bridge,'run_closing',fake_run)
    form={'year':2026,'month':10,'reports':['fksp','stravovaci_arch'],
          'arch_variant':'StravovaciArch','include_bulk_arch':True,'recap_variant':'R','pack_zip':False}
    result=closing_bridge.generate_closing(str(source),form,tmp_path/'output')
    assert result['status']=='exported' and len(result['files'])==1
    assert seen[0]['uzaverka']['odeslat_mail'] is False
    assert seen[0]['uzaverka']['vsechny_kategorie'] is False
    assert source.read_bytes()==original


def test_special_report_restricts_categories_and_keeps_mapping_without_writes(tmp_path,monkeypatch):
    import sys,json,pytest
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import special_bridge
    config=tmp_path/'config.json'
    config.write_text(json.dumps({'databaze':{},'z17':{'mapovani_kategorii':{'0102':['ZACI']}}}),encoding='utf-8')
    before=config.read_bytes()
    monkeypatch.setattr(special_bridge,'info',lambda path:{'categories':[{'code':'ZACI','name':'Žáci'}]})
    seen=[]
    def run(path,*,year):
        raw=json.loads(path.read_text(encoding='utf-8'))
        seen.append(raw)
        return SimpleNamespace(year=year,files=(Path(raw['z17']['vystup'])/'report.pdf',),detail='OK')
    monkeypatch.setattr(special_bridge,'run_special',run)
    form=special_bridge.special_defaults(str(config))
    assert form['mapping']['0102']==['ZACI']
    result=special_bridge.generate_special(str(config),form,tmp_path/'output')
    assert result['year']==form['year'] and seen[0]['z17']['vsechny_kategorie'] is False
    assert seen[0]['z17']['povolene_kategorie']==['ZACI'] and config.read_bytes()==before
    with pytest.raises(ValueError,match='nepovolenou kategorii'):
        special_bridge.generate_special(str(config),{**form,'mapping':{'0102':['NEPOVOLENA']}},tmp_path/'output')
    assert len(seen)==1


def test_save_special_mapping_preserves_categories_outside_scope(tmp_path,monkeypatch):
    import sys,json,pytest
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import special_bridge,credential_store
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    config=workspace/'config.json'
    config.write_text(json.dumps({'databaze':{},'z17':{'mapovani_kategorii':{'0102':['ZACI','MIMO']}}}),encoding='utf-8')
    monkeypatch.setattr(credential_store,'get_admin_password',lambda:'admin')
    monkeypatch.setattr(special_bridge,'info',lambda path:{'categories':[{'code':'ZACI','name':'Žáci'}]})
    data=special_bridge.special_defaults(str(config))
    data['mapping']['0102']=[]
    data['mapping']['0103']=['ZACI']
    with pytest.raises(ValueError,match='Nesprávné'):
        special_bridge.save_special(str(config),str(workspace),'wrong',data)
    special_bridge.save_special(str(config),str(workspace),'admin',data)
    raw=json.loads(config.read_text(encoding='utf-8'))
    assert raw['z17']['mapovani_kategorii']['0102']==['MIMO']
    assert raw['z17']['mapovani_kategorii']['0103']==['ZACI']


def test_save_report_files_copies_only_one_generated_folder_without_overwrite(tmp_path):
    import sys,pytest
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    root=tmp_path/'generated'
    folder=root/'Uzaverka-2026-10-12345678'
    folder.mkdir(parents=True)
    pdf=folder/'report.pdf'; pdf.write_bytes(b'%PDF-test')
    archive=folder/'report.zip'; archive.write_bytes(b'PK-test')
    target=tmp_path/'saved'
    result=legacy_bridge.save_report_files([str(pdf),str(archive)],str(target),str(root))
    assert len(result['files'])==2 and (target/'report.pdf').read_bytes()==b'%PDF-test'
    with pytest.raises(ValueError,match='již existuje'):
        legacy_bridge.save_report_files([str(pdf)],str(target),str(root))
    outsider=tmp_path/'other.pdf'; outsider.write_bytes(b'%PDF-other')
    with pytest.raises(ValueError,match='jedné vytvořené sestavy'):
        legacy_bridge.save_report_files([str(pdf),str(outsider)],str(tmp_path/'bad'),str(root))
    assert not (tmp_path/'bad').exists()


def test_smtp_multiple_attachments_uses_pdf_and_zip_content_types(tmp_path,monkeypatch):
    import services.web_mail_smtp as smtp
    pdf=tmp_path/'report.pdf';pdf.write_bytes(b'%PDF-test')
    archive=tmp_path/'report.zip';archive.write_bytes(b'PK-test')
    sent=[]
    class Client:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def ehlo(self):pass
        def starttls(self,**kwargs):pass
        def send_message(self,message):sent.append(message)
    monkeypatch.setattr(smtp.smtplib,'SMTP',lambda *args,**kwargs:Client())
    settings={'smtp_host':'example.invalid','smtp_port':587,'smtp_security':'starttls',
              'smtp_username':'','from_email':'sender@example.invalid','from_name':''}
    smtp.smtp_send_files(settings,['a@example.invalid'],'Report','Body',[pdf,archive])
    parts=list(sent[0].iter_attachments())
    assert [part.get_content_type() for part in parts]==['application/pdf','application/zip']
    assert [part.get_filename() for part in parts]==['report.pdf','report.zip']


def test_send_generated_closing_files_never_schedules_or_sends_unknown_files(tmp_path,monkeypatch):
    import sys,pytest
    from types import SimpleNamespace
    import automaticky_export
    import services.web_mail_settings as settings
    import services.web_mail_smtp as smtp
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    root=tmp_path/'generated'
    output=root/'Uzaverka-2026-10-12345678'
    output.mkdir(parents=True)
    pdf=output/'report.pdf';pdf.write_bytes(b'%PDF-test')
    config=tmp_path/'config.json';config.touch()
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace())
    monkeypatch.setattr(automaticky_export,'read_saved_settings',lambda path:{})
    monkeypatch.setattr(settings,'load_settings',lambda path:{'transport':'smtp','subject_template':'{report} {date}','body_template':'{report}'})
    calls=[]
    monkeypatch.setattr(smtp,'smtp_send_files',lambda *args:calls.append(args))
    result=legacy_bridge.send_report_files(str(config),[str(pdf)],['a@example.invalid'],'Uzávěrka','10/2026',str(root))
    assert result['sent']==1 and len(calls)==1 and calls[0][4]==[pdf.resolve()]
    assert not (tmp_path/'web_mail_tasks.json').exists()
    outsider=tmp_path/'other.pdf';outsider.write_bytes(b'%PDF-other')
    with pytest.raises(ValueError,match='jedné vytvořené sestavy'):
        legacy_bridge.send_report_files(str(config),[str(outsider)],['a@example.invalid'],'Uzávěrka','10/2026',str(root))
    assert len(calls)==1


def test_bulk_message_rechecks_preview_and_restricts_categories(tmp_path,monkeypatch):
    import sys,pytest
    from types import SimpleNamespace
    from services.bulk import BulkData, BulkDiner
    import services.web_mail_settings as settings
    import automaticky_export,env_store
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import bulk_bridge
    config=tmp_path/'config.json';config.touch()
    diners=(BulkDiner(1,'Anna','anna@example.invalid','3.A','ZACI'),BulkDiner(2,'Eva','eva@example.invalid','3.A','HOST'),BulkDiner(3,'Jan',None,'3.A','ZACI'))
    monkeypatch.setattr(bulk_bridge,'configuration',lambda p:SimpleNamespace(database={'password':'not-real'},categories=('ZACI',)))
    monkeypatch.setattr(bulk_bridge,'load_bulk_data',lambda db,pwd:BulkData(classes=(('3.A',''),),categories=(('ZACI','Žáci'),('HOST','Hosté')),diners=diners))
    monkeypatch.setattr(automaticky_export,'read_saved_settings',lambda p:{})
    monkeypatch.setattr(settings,'load_settings',lambda p:{'transport':'resend','from_email':'sender@example.invalid'})
    monkeypatch.setattr(env_store,'get_resend_api_key',lambda:'not-real')
    sent=[]
    monkeypatch.setattr(bulk_bridge,'send_bulk',lambda preview,**kwargs:sent.append(preview.recipients) or SimpleNamespace(recipients=preview.recipients))
    request={'filter_type':'trida','values':['3.A'],'subject':'Předmět','body':'Text'}
    preview=bulk_bridge.preview_message(str(config),request)
    assert preview['recipients']==1 and preview['missing']==1
    assert {r['name'] for r in preview['rows']}=={'Anna','Jan'}
    assert bulk_bridge.send_message(str(config),{**request,'revision':preview['revision']})['sent']==1
    assert sent==[('anna@example.invalid',)]
    with pytest.raises(ValueError,match='změnili'):
        bulk_bridge.send_message(str(config),{**request,'body':'Jiný text','revision':preview['revision']})
    assert len(sent)==1


def test_bulk_preview_shows_missing_addresses_without_sending(tmp_path,monkeypatch):
    import sys
    from types import SimpleNamespace
    from services.bulk import BulkData,BulkDiner
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import bulk_bridge
    monkeypatch.setattr(bulk_bridge,'configuration',lambda p:SimpleNamespace(database={'password':'x'},categories=()))
    monkeypatch.setattr(bulk_bridge,'load_bulk_data',lambda db,pwd:BulkData(classes=(('3.A',''),),categories=(),diners=(BulkDiner(1,'Jan',None,'3.A','ZACI'),)))
    preview=bulk_bridge.preview_message(str(tmp_path/'config.json'),{'filter_type':'trida','values':['3.A'],'subject':'','body':''})
    assert preview['missing']==1 and preview['recipients']==0


def test_wizard_pdf_typography_and_menu_are_saved_and_restored(tmp_path,monkeypatch):
    import sys
    from types import SimpleNamespace
    from services.web_daily_profiles import load_profiles,profile_file
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:SimpleNamespace())
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    monkeypatch.setattr(legacy_bridge,'filter_options',lambda path,day:{'meals':[],'deliveries':[]})
    data={'name':'Tisk','date':date.today().isoformat(),'category':'all','content':'names','mode':'today',
          'output':'email','recipients':'a@example.invalid','time':'08:00','enabled':False,'cooking':False,
          'pdf_data_font_size':9.5,'pdf_label_font_size':10,'language':'česky','menu_list_number':2}
    path=str(tmp_path/'config.json')
    task=legacy_bridge.save_task(path,data)['task']
    profile=load_profiles(profile_file(tmp_path))[0]
    assert (profile.pdf_data_font_size,profile.pdf_label_font_size,profile.language,profile.menu_list_number)==(9.5,10,'česky',2)
    edit=legacy_bridge.wizard_edit_data(path,task['id'])['data']
    assert (edit['pdf_data_font_size'],edit['pdf_label_font_size'],edit['language'],edit['menu_list_number'])==(9.5,10,'česky',2)


def test_save_pdf_template_inherits_global_values_without_copying_filters(tmp_path,monkeypatch):
    import sys
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    from services.pdf_templates import load_templates,template_file
    workspace=tmp_path/'workspace';workspace.mkdir()
    config=workspace/'config.json';config.touch()
    base=SimpleNamespace(pdf_orientation='na_vysku',pdf_data_font_size=8.5,pdf_label_font_size=9,pdf_bold=False)
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:base)
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    data={'name':'Sestava','date':date.today().isoformat(),'category':'all','content':'names',
          'pdf_data_font_size':10,'category_separation':True}
    result=legacy_bridge.save_pdf_template(str(config),str(workspace),data,'Kuchyně')
    saved=load_templates(template_file(workspace))[0]
    assert result['template']['id']==saved.id
    assert saved.settings['pdf_data_font_size']==10 and saved.settings['pdf_label_font_size']==9
    assert saved.settings['category_separation'] and 'categories' not in saved.settings


def test_activity_requires_admin_and_reads_only_workspace(tmp_path,monkeypatch):
    import sys,pytest
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import settings_bridge,credential_store
    from services.web_activity import record_event
    workspace=tmp_path/'workspace';workspace.mkdir()
    config=workspace/'config.json';config.touch()
    monkeypatch.setattr(credential_store,'get_admin_password',lambda:'admin')
    record_event(workspace,'error','Testovací chyba',task_name='Úloha')
    with pytest.raises(ValueError,match='Nesprávné'):
        settings_bridge.read_activity(str(config),str(workspace),'wrong')
    rows=settings_bridge.read_activity(str(config),str(workspace),'admin')
    assert len(rows)==1 and rows[0]['message']=='Testovací chyba'
    with pytest.raises(ValueError,match='odděleném prostoru'):
        settings_bridge.read_activity(str(config),str(tmp_path/'other'),'admin')


def test_wizard_layout_is_saved_and_template_uses_current_layout(tmp_path,monkeypatch):
    import sys,pytest
    from types import SimpleNamespace
    from services.pdf_templates import load_templates,template_file
    from services.web_daily_profiles import load_profiles,profile_file
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    workspace=tmp_path/'workspace';workspace.mkdir()
    path=workspace/'config.json';path.touch()
    cfg=SimpleNamespace(pdf_orientation='na_vysku',pdf_data_font_size=8.5,pdf_label_font_size=9,pdf_bold=False)
    monkeypatch.setattr(legacy_bridge,'configuration',lambda path:cfg)
    monkeypatch.setattr(legacy_bridge,'info',lambda path:{'categories':[{'code':'ZACI'}]})
    layout=[['menus'],['categories','norms'],['delivery'],['diners'],['collection']]
    data={'name':'Test','date':date.today().isoformat(),'category':'all','content':'names','mode':'today',
          'output':'email','recipients':'a@example.invalid','time':'08:00','enabled':False,'cooking':False,
          'pdf_layout':layout,'pdf_page_breaks':['diners']}
    legacy_bridge.save_task(str(path),data)
    profile=load_profiles(profile_file(workspace))[0]
    assert profile.pdf_layout[1]==('categories','norms') and profile.pdf_page_breaks==('diners',)
    legacy_bridge.save_pdf_template(str(path),str(workspace),data,'Rozložení')
    assert load_templates(template_file(workspace))[0].settings['pdf_layout'][1]==('categories','norms')
    invalid={**data,'delivery_page_per_type':True,'pdf_layout':[['menus','delivery']]}
    with pytest.raises(ValueError,match='vlastní řádek'):
        legacy_bridge.save_task(str(path),invalid)


def test_render_generated_pdf_page_and_reject_outside_file(tmp_path):
    import sys,pytest,base64
    sys.path.insert(0,str(Path(__file__).parent/'backend'))
    import legacy_bridge
    result=engine.handle({'start':'2026-11-10','end':'2026-11-12','status':'both','category':'all','action':'pdf','output_dir':str(tmp_path)})
    page=legacy_bridge.render_pdf_page(result['pdf'],0,str(tmp_path))
    assert page['pages']>=1 and page['page']==0 and base64.b64decode(page['image']).startswith(b'\x89PNG')
    with pytest.raises(ValueError,match='Neplatná stránka'):
        legacy_bridge.render_pdf_page(result['pdf'],page['pages'],str(tmp_path))
    with pytest.raises(ValueError,match='vytvořené PDF'):
        legacy_bridge.render_pdf_page(result['pdf'],0,str(tmp_path/'other'))

def test_saved_profiles_are_reusable_without_expanding_permissions(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge
    from services.web_daily_profiles import DailyProfile, save_profile, profile_file
    monkeypatch.setattr(legacy_bridge, 'configuration', lambda path: SimpleNamespace())
    monkeypatch.setattr(legacy_bridge, 'info', lambda path: {'categories': [{'code': 'ZACI'}]})
    profile = DailyProfile.from_dict({'id': 'a', 'name': 'Obědy', 'categories': ['ZACI', 'HOST'],
                                     'meal_type': ['Oběd'], 'delivery_types': ['Rozvoz'],
                                     'collection_status': 'both', 'show_diner_list': True})
    save_profile(profile_file(tmp_path), profile)
    save_profile(profile_file(tmp_path), DailyProfile.from_dict({'id': 'b', 'name': 'Hosté', 'categories': ['HOST']}))
    profiles = legacy_bridge.saved_report_profiles(str(tmp_path / 'config.json'))
    assert len(profiles) == 1
    assert profiles[0]['categories'] == ['ZACI'] and profiles[0]['restricted']
    assert profiles[0]['content'] == 'collection' and profiles[0]['collection'] == 'both'
    assert profiles[0]['meals'] == ['oběd'] and profiles[0]['deliveries'] == ['Rozvoz']
    assert profile.categories == ('ZACI', 'HOST')

def test_edit_legacy_global_task_snapshots_settings_and_rejects_stale_config(tmp_path, monkeypatch):
    import sys
    from dataclasses import replace
    import pytest
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge
    from stravovaci_sestava import AppConfig
    from services.web_mail_tasks import MailTask
    from services.web_mail_task_store import save_tasks, load_tasks, task_file
    from services.web_daily_profiles import load_profiles, profile_file
    config = AppConfig(database={}, report_date=date.today(), categories=('ZACI',), language='česky',
                       menu_list_number=1, show_diner_list=False, pdf_bold=True)
    current = [config]
    monkeypatch.setattr(legacy_bridge, 'configuration', lambda path: current[0])
    monkeypatch.setattr(legacy_bridge, 'info', lambda path: {'categories': [{'code': 'ZACI'}]})
    monkeypatch.setattr(legacy_bridge, 'filter_options', lambda path, day: {'meals': [], 'deliveries': []})
    task = MailTask.from_dict({'id': 'old', 'name': 'Starší', 'report': 'daily', 'recipients': ['a@example.invalid'],
                               'send_time': '08:00', 'date_mode': 'today', 'enabled': False})
    save_tasks(task_file(tmp_path), [task])
    path = str(tmp_path / 'config.json')
    edit = legacy_bridge.wizard_edit_data(path, task.id)
    assert edit['legacy_global'] and edit['data']['content'] == 'counts' and edit['data']['pdf_bold'] is True
    data = {**edit['data'], 'edit_id': task.id, 'revision': edit['revision'], 'profile_revision': edit['profile_revision']}
    import automaticky_export
    import services.web_daily_profiles as daily_profiles
    from types import SimpleNamespace
    monkeypatch.setattr(automaticky_export, 'read_saved_settings', lambda path: {})
    monkeypatch.setattr(daily_profiles, 'apply_profile', lambda cfg, profile, raw: cfg)
    monkeypatch.setattr(legacy_bridge, 'fetch_report', lambda cfg: SimpleNamespace(menus=[]))
    monkeypatch.setattr(legacy_bridge, 'create_pdf', lambda cfg, report, output_path: Path(output_path).write_bytes(b'%PDF-test'))
    assert Path(legacy_bridge.preview_wizard(path, data, str(tmp_path))['pdf']).is_file()
    assert legacy_bridge.preview_schedule(path, data)['today_report'] == date.today().isoformat()
    current[0] = replace(config, pdf_bold=False)
    with pytest.raises(ValueError, match='mezitím změnil'):
        legacy_bridge.save_task(path, data)
    assert load_tasks(task_file(tmp_path))[0].profile_id is None
    current[0] = config
    legacy_bridge.save_task(path, data)
    updated = load_tasks(task_file(tmp_path))[0]
    assert updated.id == task.id and updated.profile_id
    profile = load_profiles(profile_file(tmp_path))[0]
    assert profile.id == updated.profile_id and profile.pdf_bold is True and not profile.show_diner_list

def test_wizard_calendar_choice_is_saved_edited_and_validated(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    import pytest
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge
    from services.web_mail_task_store import load_tasks, task_file
    monkeypatch.setattr(legacy_bridge, 'configuration', lambda path: SimpleNamespace())
    monkeypatch.setattr(legacy_bridge, 'info', lambda path: {'categories': [{'code': 'ZACI'}]})
    monkeypatch.setattr(legacy_bridge, 'filter_options', lambda path, day: {'meals': [], 'deliveries': []})
    monkeypatch.setattr(legacy_bridge, 'cooking_calendars', lambda path: ['Oběd', 'Snídaně'])
    path = str(tmp_path / 'config.json')
    data = {'name': 'Kalendář', 'date': date.today().isoformat(), 'categories': ['ZACI'],
            'content': 'names', 'mode': 'today', 'output': 'email', 'recipients': 'a@example.invalid',
            'time': '08:00', 'enabled': False, 'cooking': True,
            'calendar_mode': 'selected', 'calendars': ['Snídaně']}
    task = legacy_bridge.save_task(path, data)['task']
    assert task['cooking_meal_type'] == ['Snídaně']
    edit = legacy_bridge.wizard_edit_data(path, task['id'])
    assert edit['data']['calendar_mode'] == 'selected' and edit['data']['calendars'] == ['Snídaně']
    update = {**edit['data'], 'edit_id': task['id'], 'revision': edit['revision'], 'profile_revision': edit['profile_revision']}
    update['calendars'] = ['Neznámý']
    with pytest.raises(ValueError, match='kalendář'):
        legacy_bridge.save_task(path, update)
    assert load_tasks(task_file(tmp_path))[0].cooking_meal_type == ('Snídaně',)
    update.update(calendar_mode='all', calendars=[])
    legacy_bridge.save_task(path, update)
    assert load_tasks(task_file(tmp_path))[0].cooking_meal_type == '*'

def test_engine_forbids_task_mutations_in_legacy_workspace(tmp_path, monkeypatch):
    import pytest
    import engine
    import legacy_bridge
    old = tmp_path / 'old'
    isolated = tmp_path / 'isolated'
    old.mkdir(); isolated.mkdir()
    (old / 'config.json').write_text('{}', encoding='utf-8')
    (isolated / 'config.json').write_text('{}', encoding='utf-8')
    calls = []
    for name in ('save_task', 'delete_task', 'update_task', 'set_task_enabled'):
        monkeypatch.setattr(legacy_bridge, name, lambda *args: calls.append(args) or {'ok': True})
    actions = ('legacy_save_task', 'legacy_delete_task', 'legacy_update_task', 'legacy_set_task_enabled')
    for index, action in enumerate(actions):
        request = {'action': action, 'config_path': str(old / 'config.json'), 'workspace_dir': str(isolated)}
        with pytest.raises(ValueError, match='odděleném prostoru'):
            engine.handle(request)
        assert len(calls) == index
        request['config_path'] = str(isolated / 'config.json')
        assert engine.handle(request) == {'ok': True}
    assert len(calls) == 4

def test_workspace_import_copies_nssm_without_old_installation_dependency(tmp_path):
    import json, sys
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import workspace_import
    from services.web_mail_settings import load_settings, settings_path
    old = tmp_path / 'old'
    (old / 'nssm' / 'win64').mkdir(parents=True)
    (old / 'config.json').write_text('{}', encoding='utf-8')
    (old / 'nssm' / 'win64' / 'nssm.exe').write_bytes(b'fixture-nssm')
    target = tmp_path / 'v2' / 'workspace'
    result = workspace_import.import_workspace(str(old / 'config.json'), target)
    copied = target / 'nssm' / 'nssm.exe'
    assert result['nssm_copied'] is True and copied.read_bytes() == b'fixture-nssm'
    assert Path(load_settings(settings_path(target))['nssm_path']) == copied
    (old / 'nssm' / 'win64' / 'nssm.exe').unlink()
    assert Path(load_settings(settings_path(target))['nssm_path']).is_file()

def test_save_standalone_profile_requires_isolated_workspace_and_creates_no_task(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    import pytest
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge
    from services.web_daily_profiles import load_profiles, profile_file
    from services.web_mail_task_store import task_file
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    config = workspace / 'config.json'
    config.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(legacy_bridge, 'configuration', lambda path: SimpleNamespace())
    monkeypatch.setattr(legacy_bridge, 'info', lambda path: {'categories': [{'code': 'ZACI'}]})
    data = {'name': 'Škola', 'date': date.today().isoformat(), 'categories': ['ZACI'], 'content': 'names'}
    result = legacy_bridge.save_report_profile(str(config), str(workspace), data)
    profiles = load_profiles(profile_file(workspace))
    assert len(profiles) == 1 and profiles[0].id == result['id']
    assert not task_file(workspace).exists()
    with pytest.raises(ValueError, match='odděleném prostoru'):
        legacy_bridge.save_report_profile(str(config), str(tmp_path / 'other'), data)

def test_update_report_profile_checks_revision_and_category_permissions(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    import pytest
    from dataclasses import replace
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge
    from services.web_daily_profiles import DailyProfile, load_profiles, profile_file, save_profile
    workspace = tmp_path / 'workspace'; workspace.mkdir()
    config = workspace / 'config.json'; config.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(legacy_bridge, 'configuration', lambda path: SimpleNamespace())
    monkeypatch.setattr(legacy_bridge, 'info', lambda path: {'categories': [{'code': 'ZACI'}]})
    profile = DailyProfile.from_dict({'id':'p', 'name':'Škola', 'categories':['ZACI']})
    save_profile(profile_file(workspace), profile)
    data = {'name':'Změněná škola', 'date':date.today().isoformat(), 'categories':['ZACI'], 'content':'counts'}
    result = legacy_bridge.update_report_profile(str(config), str(workspace), data, 'p', legacy_bridge.task_revision(profile))
    assert result['id'] == 'p' and load_profiles(profile_file(workspace))[0].show_diner_list is False
    with pytest.raises(ValueError, match='mezitím změnil'):
        legacy_bridge.update_report_profile(str(config), str(workspace), data, 'p', legacy_bridge.task_revision(profile))
    restricted = replace(load_profiles(profile_file(workspace))[0], categories=('ZACI', 'HOST'))
    save_profile(profile_file(workspace), restricted)
    with pytest.raises(ValueError, match='nepovolené kategorie'):
        legacy_bridge.update_report_profile(str(config), str(workspace), data, 'p', legacy_bridge.task_revision(restricted))
    assert load_profiles(profile_file(workspace))[0] == restricted

def test_bridge_configuration_uses_actual_legacy_date_format(tmp_path, monkeypatch):
    import json, sys
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import legacy_bridge, stravovaci_sestava
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'databaze': {'host':'localhost','port':5432,'dbname':'test','user':'test'}}), encoding='utf-8')
    monkeypatch.setattr(stravovaci_sestava, 'get_password', lambda database: 'test-password')
    loaded = legacy_bridge.configuration(str(config))
    assert loaded.report_date == date.today()

def test_import_preserves_legacy_scheduler_jobs_as_disabled(tmp_path):
    import json, sys
    from planovac import load_jobs
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))
    import workspace_import
    source = tmp_path / 'old'; source.mkdir()
    (source / 'config.json').write_text('{}', encoding='utf-8')
    original = {'jobs': [{'name':'Uzávěrka', 'action':'uzaverka', 'path':'C:/DataShip/run.bat',
                          'schedule':{'type':'daily','time':'08:30'}, 'enabled':True}]}
    (source / 'planovac.json').write_text(json.dumps(original), encoding='utf-8')
    target = tmp_path / 'v2' / 'workspace'
    result = workspace_import.import_workspace(str(source / 'config.json'), target)
    jobs = load_jobs(target / 'planovac.json', target)
    assert result['legacy_jobs'] == 1 and len(jobs) == 1
    assert jobs[0].name == 'Uzávěrka' and jobs[0].action == 'uzaverka' and not jobs[0].enabled
    assert json.loads((source / 'planovac.json').read_text(encoding='utf-8')) == original
