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
