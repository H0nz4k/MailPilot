from datetime import date
import pytest
from stravovaci_sestava import DinerOrder, build_delivery_rows, ConfigError
from services.web_daily_profiles import DailyProfile, apply_profile

def test_delivery_groups_menus_and_bulk_without_duplicating_rates():
    orders = (DinerOrder('A', '1', 'Děti', 'Oběd-A', 1, None, 'Polévka'), DinerOrder('B', '1', 'Děti', 'Oběd-A', 2, None, 'Řízek'))
    bulk = [(None, '1', 'Děti', 'Oběd-A', '1', None, 'Polévka', 5)]
    rates = [('1', 'oběd-a', 'Rozvoz A', True)] * 2
    rows = build_delivery_rows(orders, bulk, rates)
    assert [(r[3], r[4]) for r in rows] == [(1, 6), (2, 1)]
    assert rows[0][0] == 'Rozvoz A'

def test_conflicting_rates_fail_closed_and_missing_is_visible():
    orders = (DinerOrder('A', '1', 'Děti', 'Oběd-A', 1, None, None),)
    with pytest.raises(ConfigError, match='více typů výdeje'):
        build_delivery_rows(orders, [], [('1', 'oběd-a', 'A', True), ('1', 'oběd-a', 'B', True)])
    assert build_delivery_rows(orders, [], [])[0][0] == '[bez platné sazby]'
    assert 'není v typech' in build_delivery_rows(orders, [], [('1', 'oběd-a', 'Neznámý výdej', False)])[0][0]

def test_saved_profile_roundtrip_keeps_new_preferences():
    p = DailyProfile.from_dict({'name': 'Rozvoz', 'categories': ['1'], 'show_delivery_summary': True, 'delivery_show_names': True})
    assert DailyProfile.from_dict(p.to_dict()) == p
    assert not DailyProfile.from_dict({'name': 'Starý', 'categories': ['1']}).show_delivery_summary

def test_pdf_dispatch_section_and_optional_dish_name(tmp_path):
    from dataclasses import replace
    from pypdf import PdfReader
    from stravovaci_sestava import AppConfig, ReportData, create_pdf
    config = AppConfig(database={}, report_date=date(2026, 11, 9), categories=('1',), language='česky', menu_list_number=1, show_diner_list=False, show_delivery_summary=True, delivery_show_names=True, pdf_output=tmp_path / 'vydej.pdf')
    report = ReportData(menus=(), categories=(), norms=(), diners=(), subject_name='Test', delivery_rows=(('Rozvoz A', '1', 'Děti', 1, 6, 'Hrachová kaše', 'Oběd'),))
    def pdf_text(config):
        path = create_pdf(config, report)
        return '\n'.join(page.extract_text() or '' for page in PdfReader(path).pages)
    text = pdf_text(config)
    assert 'Rozvoz A' in text and 'Menu 1' in text and 'Hrachová kaše' in text
    text = pdf_text(replace(config, delivery_show_names=False))
    assert 'Rozvoz A' in text and 'Hrachová kaše' not in text

def test_delivery_filter_applies_to_entire_report_including_bulk():
    from stravovaci_sestava import ReportData, CategorySummary, MenuSummary, NormMenuSummary, filter_delivery_orders, _include_bulk_orders
    people = (DinerOrder('A', '1', 'Děti', 'Oběd-A', 1, 'A', 'Rýže'), DinerOrder('B', '1', 'Děti', 'Večeře', 2, 'A', 'Polévka'))
    bulk = [(None, '1', 'Děti', 'Oběd-A', '1', 'A', 'Rýže', 5), (None, '1', 'Děti', 'Večeře', '2', 'A', 'Polévka', 7)]
    report = ReportData(menus=(MenuSummary('Oběd-A', 1, 1, 'Rýže'), MenuSummary('Večeře', 2, 1, 'Polévka')), categories=(CategorySummary('1', 'Děti', 'A', 2),), norms=(), diners=people, subject_name='Test')
    rates = [('1', 'oběd-a', 'Rozvoz A', True), ('1', 'večeře', 'Rozvoz B', True)]
    filtered, kept, selected_bulk = filter_delivery_orders(report, people, bulk, rates, ('Rozvoz A',))
    result = _include_bulk_orders(filtered, selected_bulk, show_diner_list=True)
    assert len(kept) == 1 and len(selected_bulk) == 1
    assert result.menus[0].portions == 6
    assert result.categories[0].applications == 6
    assert sum(x.portions for x in result.norms) == 6
    assert {d.meal_type for d in result.diners} == {'Oběd-A'}

def test_delivery_filter_rejects_ambiguous_rates():
    from stravovaci_sestava import ReportData, CategorySummary, filter_delivery_orders
    person = DinerOrder('A', '1', 'Děti', 'Oběd-A', 1, None, None)
    report = ReportData(menus=(), categories=(CategorySummary('1', 'Děti', None, 1),), norms=(), diners=(person,), subject_name=None)
    with pytest.raises(ConfigError, match='více typů výdeje'):
        filter_delivery_orders(report, (person,), (), [('1', 'oběd-a', 'A', True), ('1', 'oběd-a', 'B', True)], ('A',))

def test_delivery_filter_saved_profile_roundtrip():
    profile = DailyProfile.from_dict({'name': 'Rozvoz', 'categories': ['1'], 'delivery_types': ['Rozvoz A', 'Rozvoz B']})
    assert DailyProfile.from_dict(profile.to_dict()).delivery_types == ('Rozvoz A', 'Rozvoz B')
    assert DailyProfile.from_dict({'name': 'Starý', 'categories': ['1']}).delivery_types == ()
    with pytest.raises((ValueError, ConfigError)):
        DailyProfile.from_dict({'name': 'Špatný', 'categories': ['1'], 'delivery_types': 'Rozvoz A'})

def test_saved_filter_is_applied_to_planned_configuration():
    from stravovaci_sestava import AppConfig
    profile = DailyProfile.from_dict({'name': 'Rozvoz', 'categories': ['1'], 'delivery_types': ['Rozvoz A']})
    config = AppConfig(database={}, report_date=date(2026, 11, 9), categories=('1',), language='česky', menu_list_number=1)
    result = apply_profile(config, profile, {'poctyemailem': {'vsechny_kategorie': True}})
    assert result.delivery_types == ('Rozvoz A',)


def test_pdf_summary_precedes_delivery_and_stays_together(tmp_path):
    from pypdf import PdfReader
    from stravovaci_sestava import AppConfig, CategorySummary, NormMenuSummary, ReportData, create_pdf
    config = AppConfig(database={}, report_date=date(2026, 11, 9), categories=('1',),
                       language='česky', menu_list_number=1, show_diner_list=False,
                       show_delivery_summary=True, pdf_output=tmp_path / 'souhrn.pdf')
    report = ReportData(menus=(), categories=(CategorySummary('1', 'Děti', 'A', 3),),
                        norms=(NormMenuSummary('Oběd', 'A', 1, 3),), diners=(),
                        subject_name='Test', delivery_rows=(('Rozvoz', '1', 'Děti', 1, 3, None, 'Oběd'),))
    pages = [page.extract_text() for page in PdfReader(create_pdf(config, report)).pages]
    category = next(i for i, text in enumerate(pages) if 'Přihlášky podle kategorií' in text)
    norms = next(i for i, text in enumerate(pages) if 'Objednaná menu podle norem' in text)
    delivery = next(i for i, text in enumerate(pages) if 'Typ výdeje: Rozvoz' in text)
    assert category == norms <= delivery
    if category == delivery:
        assert pages[category].index('Objednaná menu podle norem') < pages[delivery].index('Typ výdeje: Rozvoz')


def test_pdf_delivery_types_never_share_a_page_when_selected(tmp_path):
    from pypdf import PdfReader
    from stravovaci_sestava import AppConfig, ReportData, create_pdf
    config = AppConfig(database={}, report_date=date(2026, 11, 9), categories=('1',),
                       language='česky', menu_list_number=1, show_diner_list=False,
                       show_by_categories=False, show_by_norms=False, show_delivery_summary=True,
                       delivery_page_per_type=True, pdf_output=tmp_path / 'vydeje.pdf')
    first = [('Rozvoz A', 'A', 'ALFA', 1, 1, None, 'Oběd') for _ in range(75)]
    second = [('Rozvoz B', 'B', 'BETA', 1, 1, None, 'Oběd')]
    report = ReportData(menus=(), categories=(), norms=(), diners=(), subject_name='Test',
                        delivery_rows=tuple(first + second))
    pages = [page.extract_text() for page in PdfReader(create_pdf(config, report)).pages]
    assert sum('ALFA' in page for page in pages) > 1
    assert any('BETA' in page for page in pages)
    assert all(not ('ALFA' in page and 'BETA' in page) for page in pages)


def test_delivery_page_option_roundtrips_into_scheduled_report():
    from stravovaci_sestava import AppConfig
    profile = DailyProfile.from_dict({'name': 'Rozvoz', 'categories': ['1'], 'delivery_page_per_type': True})
    assert DailyProfile.from_dict(profile.to_dict()).delivery_page_per_type
    config = AppConfig(database={}, report_date=date(2026, 11, 9), categories=('1',),
                       language='česky', menu_list_number=1)
    assert apply_profile(config, profile, {'poctyemailem': {'vsechny_kategorie': True}}).delivery_page_per_type
    assert not DailyProfile.from_dict({'name': 'Starý', 'categories': ['1']}).delivery_page_per_type


def test_large_summary_can_continue_across_pages(tmp_path):
    from pypdf import PdfReader
    from stravovaci_sestava import AppConfig, CategorySummary, NormMenuSummary, ReportData, create_pdf
    config = AppConfig(database={}, report_date=date(2026, 11, 9), categories=('1',),
                       language='česky', menu_list_number=1, show_diner_list=False,
                       show_delivery_summary=True, pdf_output=tmp_path / 'velky.pdf')
    categories = tuple(CategorySummary(str(i), f'Kategorie {i}', 'A', 1) for i in range(80))
    report = ReportData(menus=(), categories=categories,
                        norms=(NormMenuSummary('Oběd', 'A', 1, 80),), diners=(),
                        subject_name='Test', delivery_rows=(('Rozvoz', '1', 'Děti', 1, 1, None, 'Oběd'),))
    pages = [page.extract_text() for page in PdfReader(create_pdf(config, report)).pages]
    assert len(pages) > 1
    assert all(page.strip() for page in pages)
    assert 'Objednaná menu podle norem' in ''.join(pages)
    assert ''.join(pages).index('Objednaná menu podle norem') < ''.join(pages).index('Typ výdeje: Rozvoz')
