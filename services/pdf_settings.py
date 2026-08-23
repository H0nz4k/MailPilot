"""Nastavení vzhledu a výstupu PDF sdílené mezi obrazovkami.

Denní stav i Administrace → PDF pracují se stejnými klíči config.json,
proto obě míří na tuhle vrstvu a nemohou se rozejít.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from services.daily import (
    DEFAULT_PDF_OUTPUT,
    FONT_SIZE_MAX,
    FONT_SIZE_MIN,
    ORIENTATIONS,
    apply_daily_settings,
    peek_daily_settings,
)


__all__ = [
    "DEFAULT_PDF_OUTPUT",
    "FONT_SIZE_MAX",
    "FONT_SIZE_MIN",
    "ORIENTATIONS",
    "PdfSettings",
    "apply_pdf_settings",
    "peek_pdf_settings",
]


@dataclass(frozen=True)
class PdfSettings:
    """Vzhled a cíl výstupu; datum ani kategorie sem nepatří."""

    language: str = "česky"
    menu_list_number: int = 1
    output: str = DEFAULT_PDF_OUTPUT
    orientation: str = "na_vysku"
    data_font_size: float = 7.4
    label_font_size: float = 7.4
    bold: bool = False
    category_separation: bool = False
    show_by_categories: bool = True
    show_by_norms: bool = True


def peek_pdf_settings(raw: dict[str, Any] | None) -> PdfSettings:
    """Vytáhne PDF část z nastavení denní sestavy."""
    daily = peek_daily_settings(raw)
    return PdfSettings(
        language=daily.language,
        menu_list_number=daily.menu_list_number,
        output=daily.pdf_output,
        orientation=daily.pdf_orientation,
        data_font_size=daily.pdf_data_font_size,
        label_font_size=daily.pdf_label_font_size,
        bold=daily.pdf_bold,
        category_separation=daily.category_separation,
        show_by_categories=daily.show_by_categories,
        show_by_norms=daily.show_by_norms,
    )


def apply_pdf_settings(raw: dict[str, Any], settings: PdfSettings) -> dict[str, Any]:
    """Zapíše PDF část a datum i kategorie ponechá beze změny."""
    merged = replace(
        peek_daily_settings(raw),
        language=settings.language,
        menu_list_number=settings.menu_list_number,
        pdf_output=settings.output,
        pdf_orientation=settings.orientation,
        pdf_data_font_size=settings.data_font_size,
        pdf_label_font_size=settings.label_font_size,
        pdf_bold=settings.bold,
        category_separation=settings.category_separation,
        show_by_categories=settings.show_by_categories,
        show_by_norms=settings.show_by_norms,
    )
    return apply_daily_settings(raw, merged)
