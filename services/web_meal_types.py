"""Shared, backwards-compatible single/all/multiple meal filters."""
from __future__ import annotations


def normalize_meal_filter(value):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value.strip().casefold() or None
    if not isinstance(value, (list, tuple)):
        raise ValueError("Typy stravy musí být text, seznam textů nebo null.")
    if any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError("Vybrané typy stravy musí být neprázdné texty.")
    values = tuple(sorted(set(v.strip().casefold() for v in value)))
    return None if not values else values[0] if len(values) == 1 else values


def meal_filter_values(value):
    value = normalize_meal_filter(value)
    return () if value is None else (value,) if isinstance(value, str) else value


def meal_filter_caption(value):
    return ", ".join(meal_filter_values(value)) or "Všechny typy stravy"
