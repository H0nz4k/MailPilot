"""Společné záhlaví, formát částek a fonty uzávěrkových PDF."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from runtime_paths import bundled_path
from stravovaci_sestava import ConfigError
from uzaverka_nastaveni import czech_month_name

from fksp_sestava import (
    HEADER_KEYS,
    HEADER_QUERY,
    format_money,
)


@dataclass(frozen=True)
class SubjectHeader:
    subject_name: str | None
    address: str | None
    zip_code: str | None
    city: str | None
    company_id: str | None
    vat_id: str | None


def header_from_values(values: dict[str, Any]) -> SubjectHeader:
    return SubjectHeader(
        subject_name=values.get("namesubject"),
        address=values.get("adrsubject"),
        zip_code=values.get("pscsubject"),
        city=values.get("mestosubject"),
        company_id=values.get("ico"),
        vat_id=values.get("dic"),
    )


def fetch_subject_header(cursor: Any) -> SubjectHeader:
    cursor.execute(HEADER_QUERY, (list(HEADER_KEYS),))
    values = {str(key): value for key, value in cursor.fetchall()}
    return header_from_values(values)


def prihlaska_expression(alias: str = "p") -> str:
    parts = [
        (
            f"CASE WHEN BTRIM(COALESCE({alias}.d{day:02d}::text, '')) ~ '^[1-9]$' "
            f"THEN BTRIM({alias}.d{day:02d}::text) ELSE ' ' END"
        )
        for day in range(1, 32)
    ]
    return "(" + " || ".join(parts) + ")"


def previous_period_sql(month_expr: str, year_expr: str) -> tuple[str, str]:
    """SQL výrazy pro předchozí měsíc stejného uzávěrkového období."""
    prev_month = f"CASE WHEN {month_expr} = 1 THEN 12 ELSE {month_expr} - 1 END"
    prev_year = f"CASE WHEN {month_expr} = 1 THEN {year_expr} - 1 ELSE {year_expr} END"
    return prev_month, prev_year


def month_payments_sql(evid_expr: str, month_expr: str, year_expr: str) -> str:
    """Součet plateb (penden typ P) za zvolený měsíc."""
    return (
        "COALESCE((SELECT SUM(d.castka) FROM public.penden AS d "
        f"WHERE d.evidcislo = {evid_expr} AND d.rok = {year_expr} "
        f"AND d.mesic = {month_expr} AND d.typ = 'P'), 0)"
    )


def bulk_rezie_sql(func_name: str) -> str:
    """Hromadná režie: denní sazba krát počet strávníků v daném dni."""
    parts: list[str] = []
    for day in range(1, 32):
        col = f"p.d{day:02d}"
        parts.append(
            "("
            f"CASE WHEN BTRIM(COALESCE({col}::text, '')) ~ '^[1-9]$' THEN "
            f"COALESCE({col}::integer, 0) * COALESCE("
            "(SELECT CASE WHEN g.ok THEN g.cena ELSE 0 END "
            f"FROM public.{func_name}("
            "p.typsluzby, "
            "COALESCE(NULLIF(BTRIM(p.kategorie), ''), s.kategorie), "
            f"p.rok::integer, p.mesic::integer, {day}, {col}::integer) AS g), 0) "
            "ELSE 0 END"
            ")"
        )
    return " + ".join(parts)


def register_report_fonts() -> tuple[str, str]:
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError as exc:
        raise RuntimeError(
            "Chybí knihovna pro PDF. Nainstalujte závislosti z requirements.txt."
        ) from exc

    assets = bundled_path("assets")
    regular_font = assets / "DejaVuSans.ttf"
    bold_font = assets / "DejaVuSans-Bold.ttf"
    if not regular_font.is_file() or not bold_font.is_file():
        raise RuntimeError(
            "Chybí přibalené fonty assets/DejaVuSans.ttf a "
            "assets/DejaVuSans-Bold.ttf."
        )
    if "StravovaciSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("StravovaciSans", str(regular_font)))
    if "StravovaciSans-Bold" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("StravovaciSans-Bold", str(bold_font)))
    return "StravovaciSans", "StravovaciSans-Bold"


def require_pdf_path(path: Any, *, label: str) -> Any:
    target = path.resolve()
    if target.suffix.lower() != ".pdf":
        raise ConfigError(f"Výstupní soubor {label} musí mít příponu .pdf.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def period_title(month: int, year: int) -> str:
    return f"{czech_month_name(month)} {year}"


def cell_markup(value: object, *, nowrap: bool = False) -> str:
    """Text buňky pro ReportLab; nowrap drží částku a Kč na jednom řádku."""
    text = xml_escape(str(value if value not in (None, "") else ""))
    text = text.replace("\u00a0", "&nbsp;")
    if nowrap and text:
        return f"<nobr>{text}</nobr>"
    return text


def fit_column_widths(
    usable_width: float,
    specs: Sequence[tuple[float, float]],
) -> list[float]:
    """Rozdělí šířku tabulky: nejdřív minima, zbytek podle flex váhy."""
    if usable_width <= 0:
        raise ValueError("usable_width must be positive")
    if not specs:
        return []
    mins = [max(0.0, float(minimum)) for minimum, _weight in specs]
    weights = [max(0.0, float(weight)) for _minimum, weight in specs]
    total_min = sum(mins)
    leftover = usable_width - total_min
    if leftover <= 0:
        if total_min <= 0:
            even = usable_width / len(specs)
            return [even] * len(specs)
        scale = usable_width / total_min
        return [minimum * scale for minimum in mins]
    total_weight = sum(weights)
    if total_weight <= 0:
        extra = leftover / len(specs)
        return [minimum + extra for minimum in mins]
    return [
        minimum + leftover * (weight / total_weight)
        for minimum, weight in zip(mins, weights)
    ]


def measure_text_width(text: str, font_name: str, font_size: float) -> float:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    return float(stringWidth(text.replace("\u00a0", " "), font_name, font_size))


ProgressCallback = Callable[[float, str], None]


def report_progress(
    on_progress: ProgressCallback | None,
    fraction: float,
    message: str,
) -> None:
    """Ohlásí dílčí postup v rozsahu 0.0–1.0 v rámci jedné sestavy."""
    if on_progress is None:
        return
    clamped = max(0.0, min(1.0, fraction))
    on_progress(clamped, message)


__all__ = [
    "SubjectHeader",
    "fetch_subject_header",
    "cell_markup",
    "fit_column_widths",
    "format_money",
    "measure_text_width",
    "header_from_values",
    "period_title",
    "previous_period_sql",
    "prihlaska_expression",
    "month_payments_sql",
    "bulk_rezie_sql",
    "register_report_fonts",
    "require_pdf_path",
    "report_progress",
    "ProgressCallback",
]
