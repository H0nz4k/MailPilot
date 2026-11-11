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
