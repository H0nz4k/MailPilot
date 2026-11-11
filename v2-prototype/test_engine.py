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
