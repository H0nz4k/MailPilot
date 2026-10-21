"""Date defaults and explicit Quasar QDate Czech localization."""
from __future__ import annotations

from datetime import date


def initial_report_date(today: date | None = None) -> date:
    """Newly opened report form starts today, never at historical config.json datum."""
    return today if today is not None else date.today()


# Quasar requires full Czech locale data for QDate; ui.run(language='cs-CZ')
# alone does not consistently localize the calendar in the packaged web GUI.
CZECH_DATE_LOCALE = {
    "days": ["neděle", "pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota"],
    "daysShort": ["ne", "po", "út", "st", "čt", "pá", "so"],
    "months": [
        "leden", "únor", "březen", "duben", "květen", "červen",
        "červenec", "srpen", "září", "říjen", "listopad", "prosinec",
    ],
    "monthsShort": [
        "led", "úno", "bře", "dub", "kvě", "čer",
        "čvc", "srp", "zář", "říj", "lis", "pro",
    ],
    "firstDayOfWeek": 1,
    "format24h": True,
    "pluralDay": "dní",
}
