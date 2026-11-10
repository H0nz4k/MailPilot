"""Shared rules for the special meal collection report and its history."""
from datetime import date

COLLECTION_OPTIONS = {
    "both": "Odebraná i neodebraná",
    "collected": "Pouze odebraná",
    "uncollected": "Pouze neodebraná",
}
COLLECTION_TITLES = {
    "both": "Odebraná / neodebraná strava",
    "collected": "Odebraná strava",
    "uncollected": "Neodebraná strava",
}


def normalize_collection_status(value):
    if value is not None and (not isinstance(value, str) or value not in COLLECTION_OPTIONS):
        raise ValueError("Vyberte odebranou, neodebranou nebo obě možnosti stravy.")
    return value


def validate_report_history(day, collection_status, *, today=None):
    normalize_collection_status(collection_status)
    if day < (today or date.today()) and collection_status is None:
        raise ValueError("Datum do minulosti je možné pouze pro sestavu Odebraná / neodebraná strava.")


def validate_task_history(task, collection_status, *, today=None):
    reference = today or date.today()
    if task.date_mode == "offset" and task.day_offset < 0 and collection_status is None:
        raise ValueError("Dny zpět lze zvolit pouze pro sestavu Odebraná / neodebraná strava.")
    if task.date_mode == "fixed":
        validate_report_history(date.fromisoformat(task.fixed_date), collection_status, today=reference)
