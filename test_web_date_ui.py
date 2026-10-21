"""Date form defaults must not reuse a saved historical report date."""
from datetime import date
from services.web_date_ui import CZECH_DATE_LOCALE, initial_report_date


def test_report_form_initial_date_is_today():
    assert initial_report_date(date(2026, 10, 21)) == date(2026, 10, 21)


def test_czech_calendar_locale():
    assert CZECH_DATE_LOCALE["firstDayOfWeek"] == 1
    assert CZECH_DATE_LOCALE["months"][9] == "říjen"
    assert CZECH_DATE_LOCALE["days"][3] == "středa"
    assert len(CZECH_DATE_LOCALE["months"]) == 12
    assert len(CZECH_DATE_LOCALE["days"]) == 7
