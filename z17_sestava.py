"""Podklad k výkazu Z 17-01: stav k 31. 10. a počty jídel za školní rok."""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from stravovaci_sestava import AppConfig
from uzaverka_pdf import (
    SubjectHeader,
    cell_markup,
    fetch_subject_header,
    fit_column_widths,
    measure_text_width,
    prihlaska_expression,
    register_report_fonts,
    report_progress,
    require_pdf_path,
)
from z17_nastaveni import (
    MEAL_ROW_LABELS,
    OTHER_ROW,
    PUPIL_ROWS,
    ROW_LABELS,
    Z17Settings,
    period_keys,
    reverse_category_map,
    school_year_periods,
)


MEAL_LUNCH = "obed"
MEAL_DINNER = "vecere"
MEAL_BREAKFAST = "snidane"
MEAL_MORNING = "presnidavka"
MEAL_AFTERNOON = "svacina"
MEAL_SECOND_DINNER = "druha_vecere"
MEAL_OTHER = "jine"
SUPPLEMENTS = frozenset(
    {MEAL_BREAKFAST, MEAL_MORNING, MEAL_AFTERNOON, MEAL_SECOND_DINNER}
)
MEAL_TO_ROW = {
    MEAL_LUNCH: "0301",
    MEAL_DINNER: "0302",
    MEAL_BREAKFAST: "0303",
    MEAL_MORNING: "0304",
    MEAL_AFTERNOON: "0305",
    MEAL_SECOND_DINNER: "0306",
    MEAL_OTHER: "0309",
}

_KATEGORIE = "COALESCE(NULLIF(BTRIM(p.kategorie), ''), s.kategorie)"
_PRIHLASKA = prihlaska_expression("p")

PERIOD_QUERY = f"""
        SELECT
            p.rok,
            p.mesic,
            s.evidcislo,
            BTRIM({_KATEGORIE}) AS kategorie,
            NULLIF(BTRIM(k.nazev), '') AS nazev,
            BTRIM(p.typsluzby) AS typsluzby,
            COALESCE(p.pocet, public.getpocetprihlasek({_PRIHLASKA}, 0), 0) AS pocet,
            COALESCE(s.deleted, false) AS deleted,
            COALESCE(s.hromadny, false) AS hromadny
        FROM public.prihlas AS p
        JOIN public.stravnik AS s
          ON s.evidcislo = p.stravnik
        LEFT JOIN public.kategor AS k
          ON BTRIM(k.oznaceni) = BTRIM({_KATEGORIE})
        WHERE (p.rok * 100 + p.mesic) = ANY(%s::int[])
"""

BULK_PERIOD_QUERY = """
        SELECT
            p.rok,
            p.mesic,
            s.evidcislo,
            BTRIM(COALESCE(NULLIF(BTRIM(p.kategorie), ''), s.kategorie)) AS kategorie,
            NULLIF(BTRIM(k.nazev), '') AS nazev,
            BTRIM(p.typsluzby) AS typsluzby,
            COALESCE(public.pocetprihlashromadnehostr(p.id, 1, 31), 0) AS pocet,
            COALESCE(s.deleted, false) AS deleted,
            TRUE AS hromadny
        FROM public.prihlasn AS p
        JOIN public.stravnik AS s
          ON s.evidcislo = p.stravnik
        LEFT JOIN public.kategor AS k
          ON BTRIM(k.oznaceni) = BTRIM(
                COALESCE(NULLIF(BTRIM(p.kategorie), ''), s.kategorie)
             )
        WHERE (p.rok * 100 + p.mesic) = ANY(%s::int[])
          AND public.pocetprihlashromadnehostr(p.id, 1, 31) > 0
"""


def fold_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    stripped = "".join(char for char in text if not unicodedata.combining(char))
    return stripped.lower()


def classify_meal(typsluzby: object) -> str:
    blob = fold_text(typsluzby)
    if "druha" in blob and "vecer" in blob:
        return MEAL_SECOND_DINNER
    if "vecer" in blob:
        return MEAL_DINNER
    if "snidan" in blob:
        return MEAL_BREAKFAST
    if "presnid" in blob:
        return MEAL_MORNING
    if "svacin" in blob:
        return MEAL_AFTERNOON
    if "obed" in blob:
        return MEAL_LUNCH
    return MEAL_OTHER


def guess_z17_row(code: str, name: str | None) -> str | None:
    blob = fold_text(f"{code} {name or ''}")
    if any(token in blob for token in ("cizi", "duchod", "host", "obec", "firma")):
        return OTHER_ROW
    if any(
        token in blob
        for token in ("ucitel", "zamest", "kuchyn", "kuchar", "provoz", "pedagog")
    ):
        return "0114"
    if "nizs" in blob and "gymn" in blob:
        return "0106"
    if any(token in blob for token in ("stredn", "gymn")):
        return "0108"
    if any(token in blob for token in ("mater", "skolka", "predskol")):
        return "0102"
    if "priprav" in blob:
        return "0103"
    if any(token in blob for token in ("1. stup", "1 stup", "7-10", "7 az 10")):
        return "0104"
    if any(token in blob for token in ("2. stup", "2 stup", "11-14", "11 az 14")):
        return "0105"
    if "konzerv" in blob:
        return "0110"
    if "vos" in blob:
        return "0111"
    return None


def format_thousands(portions: int) -> str:
    value = round(float(portions) / 1000.0, 1)
    whole, fraction = f"{value:.1f}".split(".")
    return f"{whole},{fraction}"


@dataclass
class MealColumns:
    lunch_only: int = 0
    lunch_and_supplement: int = 0
    supplement_only: int = 0
    all_day: int = 0
    all_day_without_lunch: int = 0

    @property
    def total(self) -> int:
        return (
            self.lunch_only
            + self.lunch_and_supplement
            + self.supplement_only
            + self.all_day
        )

    def add(self, other: "MealColumns") -> None:
        self.lunch_only += other.lunch_only
        self.lunch_and_supplement += other.lunch_and_supplement
        self.supplement_only += other.supplement_only
        self.all_day += other.all_day
        self.all_day_without_lunch += other.all_day_without_lunch


def columns_for_kinds(kinds: Sequence[str], *, supplements_in_scope: bool) -> MealColumns:
    unique = set(kinds)
    has_lunch = MEAL_LUNCH in unique
    has_dinner = MEAL_DINNER in unique
    has_supplement = bool(unique & SUPPLEMENTS)
    if not unique:
        return MealColumns()
    if has_dinner:
        return MealColumns(all_day=1, all_day_without_lunch=0 if has_lunch else 1)
    if supplements_in_scope:
        if has_lunch and has_supplement:
            return MealColumns(lunch_and_supplement=1)
        if has_lunch:
            return MealColumns(lunch_only=1)
        if has_supplement:
            return MealColumns(supplement_only=1)
        return MealColumns(lunch_only=1)
    if has_lunch:
        return MealColumns(lunch_only=1)
    if has_supplement:
        return MealColumns(supplement_only=1)
    return MealColumns(lunch_only=1)


@dataclass
class CategoryBreakdown:
    code: str
    name: str | None
    assigned_rows: tuple[str, ...]
    guessed: bool
    october_diners: int = 0
    october_meals: dict[str, int] = field(default_factory=dict)
    school_year_meals: dict[str, int] = field(default_factory=dict)


@dataclass
class Z17Row:
    code: str
    label: str
    columns: MealColumns


@dataclass
class Z17MealRow:
    code: str
    label: str
    school_year: int
    october: int
    school_year_school: int
    october_school: int


@dataclass
class Z17Report:
    header: SubjectHeader
    year: int
    school_year_label: str
    section_i: tuple[Z17Row, ...]
    section_iii: tuple[Z17MealRow, ...]
    breakdown: tuple[CategoryBreakdown, ...]
    unmapped: tuple[str, ...]


def assigned_rows_for(
    code: str,
    name: str | None,
    reverse_map: dict[str, tuple[str, ...]],
) -> tuple[tuple[str, ...], bool]:
    mapped = reverse_map.get(code)
    if mapped:
        return mapped, False
    guessed = guess_z17_row(code, name)
    if guessed == "0114":
        return ("0114", "0114a"), True
    if guessed:
        return (guessed,), True
    return (), True


def primary_row(rows: Sequence[str]) -> str | None:
    for code in PUPIL_ROWS:
        if code in rows:
            return code
    if "0114" in rows or "0114a" in rows:
        return "0114"
    if OTHER_ROW in rows:
        return OTHER_ROW
    return None


def build_z17_report(
    *,
    header: SubjectHeader,
    settings: Z17Settings,
    records: Sequence[Sequence[Any]],
) -> Z17Report:
    reverse_map = reverse_category_map(settings.category_rows)
    october_key = settings.year * 100 + 10
    school_keys = set(period_keys(school_year_periods(settings.year)))
    diners: dict[int, dict[str, Any]] = {}
    breakdown: dict[str, CategoryBreakdown] = {}
    school_year_meals: dict[str, int] = defaultdict(int)
    october_meals: dict[str, int] = defaultdict(int)
    school_year_school: dict[str, int] = defaultdict(int)
    october_school: dict[str, int] = defaultdict(int)

    def category_item(code: str, name: str | None) -> CategoryBreakdown:
        item = breakdown.get(code)
        if item is None:
            rows, guessed = assigned_rows_for(code, name, reverse_map)
            item = CategoryBreakdown(
                code=code,
                name=name,
                assigned_rows=rows,
                guessed=guessed and code not in reverse_map,
            )
            breakdown[code] = item
        elif name and not item.name:
            item.name = name
        return item

    for record in records:
        year = int(record[0] or 0)
        month = int(record[1] or 0)
        evid = int(record[2] or 0)
        category = str(record[3] or "").strip()
        name = record[4]
        kind = classify_meal(record[5])
        portions = int(record[6] or 0)
        deleted = bool(record[7])
        bulk = bool(record[8])
        key = year * 100 + month
        if portions <= 0:
            continue
        if (
            not settings.use_all_categories
            and category not in settings.allowed_categories
        ):
            continue
        item = category_item(category, name)
        rows, _guessed = assigned_rows_for(category, name, reverse_map)
        primary = primary_row(rows)
        school_catering = primary in PUPIL_ROWS or "0114a" in rows
        if key in school_keys:
            school_year_meals[kind] += portions
            item.school_year_meals[kind] = item.school_year_meals.get(kind, 0) + portions
            if school_catering:
                school_year_school[kind] += portions
        if key != october_key:
            continue
        october_meals[kind] += portions
        item.october_meals[kind] = item.october_meals.get(kind, 0) + portions
        if school_catering:
            october_school[kind] += portions
        if deleted or bulk:
            continue
        diner = diners.setdefault(
            evid,
            {"category": category, "name": name, "kinds": set(), "rows": rows},
        )
        diner["kinds"].add(kind)
        if kind == MEAL_LUNCH or not diner["category"]:
            diner["category"] = category
            diner["name"] = name
            diner["rows"] = rows

    section_i = {code: MealColumns() for code in ROW_LABELS}
    for diner in diners.values():
        rows = tuple(diner["rows"])
        primary = primary_row(rows)
        kinds = tuple(diner["kinds"])
        in_scope = bool(primary and primary in settings.supplement_in_scope)
        pupil_cols = columns_for_kinds(kinds, supplements_in_scope=in_scope)
        staff_cols = columns_for_kinds(kinds, supplements_in_scope=True)
        if primary in PUPIL_ROWS:
            section_i[primary].add(pupil_cols)
            if (not in_scope) and set(kinds) & SUPPLEMENTS:
                section_i[OTHER_ROW].add(MealColumns(supplement_only=1))
        if primary == OTHER_ROW:
            section_i[OTHER_ROW].add(staff_cols)
        if primary == "0114" or "0114" in rows:
            section_i["0114"].add(staff_cols)
            if primary == "0114":
                section_i[OTHER_ROW].add(staff_cols)
        if "0114a" in rows:
            section_i["0114a"].add(staff_cols)

        category = str(diner["category"] or "")
        if category in breakdown:
            breakdown[category].october_diners += 1

    pupil_total = MealColumns()
    for code in PUPIL_ROWS:
        pupil_total.add(section_i[code])
    section_i["0101"] = pupil_total
    grand = MealColumns()
    grand.add(section_i["0101"])
    grand.add(section_i[OTHER_ROW])
    section_i["0115"] = grand

    unmapped = tuple(
        sorted(
            f"{item.code}  {item.name or ''}".strip()
            for item in breakdown.values()
            if not item.assigned_rows
        )
    )
    section_i_rows = tuple(
        Z17Row(code=code, label=label, columns=section_i[code])
        for code, label in ROW_LABELS.items()
        if code != "0101a"
    )
    meal_rows = [
        Z17MealRow(
            code=code,
            label=MEAL_ROW_LABELS[code],
            school_year=int(school_year_meals.get(kind, 0)),
            october=int(october_meals.get(kind, 0)),
            school_year_school=int(school_year_school.get(kind, 0)),
            october_school=int(october_school.get(kind, 0)),
        )
        for kind, code in MEAL_TO_ROW.items()
    ]
    meal_rows.sort(key=lambda item: item.code)
    ordered_breakdown = tuple(
        sorted(breakdown.values(), key=lambda item: (item.code.lower(), item.code))
    )
    return Z17Report(
        header=header,
        year=settings.year,
        school_year_label=settings.school_year_label,
        section_i=section_i_rows,
        section_iii=tuple(meal_rows),
        breakdown=ordered_breakdown,
        unmapped=unmapped,
    )


def fetch_z17_report(
    config: AppConfig,
    settings: Z17Settings,
    on_progress: Any = None,
) -> Z17Report:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "Chybí balíček psycopg. Nainstalujte závislosti z requirements.txt."
        ) from exc

    keys = list(period_keys(school_year_periods(settings.year)))
    october_key = settings.year * 100 + 10
    if october_key not in keys:
        keys.append(october_key)
    report_progress(on_progress, 0.05, "Z 17-01: připojuji se k databázi…")
    with psycopg.connect(**config.database) as connection:
        with connection.cursor() as cursor:
            header = fetch_subject_header(cursor)
            report_progress(
                on_progress,
                0.12,
                "Z 17-01: sčítám přihlášky za školní rok a říjen…",
            )
            cursor.execute(PERIOD_QUERY, (keys,))
            records = list(cursor.fetchall())
            report_progress(
                on_progress,
                0.72,
                f"Z 17-01: {len(records)} individuálních řádků, načítám hromadné…",
            )
            cursor.execute(BULK_PERIOD_QUERY, (keys,))
            records.extend(cursor.fetchall())
            report_progress(on_progress, 0.88, "Z 17-01: skládám řádky výkazu…")
    return build_z17_report(header=header, settings=settings, records=records)


def create_z17_pdf(config: AppConfig, report: Z17Report, output_path: Path) -> Path:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib.pagesizes import A4, portrait
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            LongTable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Chybí knihovna pro PDF. Nainstalujte závislosti z requirements.txt."
        ) from exc

    target = require_pdf_path(output_path, label="podklad Z 17-01")
    regular, bold = register_report_fonts()
    page_width, _page_height = portrait(A4)
    left_margin = 8 * mm
    right_margin = 8 * mm
    usable_width = page_width - left_margin - right_margin
    navy = colors.HexColor("#213B57")
    pale_gray = colors.HexColor("#F5F7F9")
    medium_gray = colors.HexColor("#D3DBE2")
    pale_blue = colors.HexColor("#EAF2F8")
    total_red = colors.HexColor("#C40000")
    text_color = colors.HexColor("#1F2933")
    muted = colors.HexColor("#5D6B78")
    data_size = config.pdf_data_font_size
    label_size = config.pdf_label_font_size
    data_font = bold if config.pdf_bold else regular

    body = ParagraphStyle(
        "Z17Body",
        fontName=data_font,
        fontSize=data_size,
        leading=max(data_size + 1.6, data_size * 1.18),
        textColor=text_color,
        alignment=TA_LEFT,
        splitLongWords=0,
    )
    right = ParagraphStyle("Z17Right", parent=body, alignment=TA_RIGHT)
    total = ParagraphStyle("Z17Total", parent=body, fontName=bold, textColor=total_red)
    total_right = ParagraphStyle("Z17TotalRight", parent=right, fontName=bold, textColor=total_red)
    header_cell = ParagraphStyle(
        "Z17HeaderCell",
        parent=body,
        fontName=bold,
        fontSize=max(6.4, label_size * 0.82),
        leading=max(8.2, label_size * 1.05),
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    title = ParagraphStyle(
        "Z17Title",
        parent=body,
        fontName=bold,
        fontSize=max(13, label_size * 1.7),
        leading=max(16, label_size * 2.1),
        textColor=navy,
    )
    section = ParagraphStyle(
        "Z17Section",
        parent=body,
        fontName=bold,
        fontSize=max(9, label_size * 1.2),
        textColor=navy,
        spaceBefore=3 * mm,
        spaceAfter=1.5 * mm,
    )
    small = ParagraphStyle(
        "Z17Small",
        parent=body,
        fontSize=max(7, data_size * 0.95),
        textColor=muted,
    )

    def para(value: object, style: ParagraphStyle = body, *, nowrap: bool = False) -> Paragraph:
        return Paragraph(cell_markup(value, nowrap=nowrap), style)

    def header_para(markup: str) -> Paragraph:
        return Paragraph(markup, header_cell)

    cell_pad = 1.6 * mm
    header_size = header_cell.fontSize

    def content_w(*samples: object, font: str = data_font, size: float = data_size) -> float:
        return max(measure_text_width(str(sample), font, size) for sample in samples) + cell_pad

    def header_w(*lines: str) -> float:
        return content_w(*lines, font=bold, size=header_size)

    def style_table(table: LongTable) -> LongTable:
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), navy),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), bold),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.35, medium_gray),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, pale_gray]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0.7 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0.7 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 0.8 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0.8 * mm),
                ]
            )
        )
        return table

    diner_headers = (
        "Řádek",
        "Kategorie strávníků",
        "Celkem<br/>sl. 2",
        "Jen oběd<br/>sl. 3",
        "Oběd + dopl.<br/>sl. 4",
        "Jen dopl.<br/>sl. 5",
        "Celodenní<br/>sl. 6",
        "Celod. bez oběda<br/>sl. 7",
    )
    diner_widths = fit_column_widths(
        usable_width,
        (
            (max(header_w("Řádek"), content_w("0114a")), 0.0),
            (header_w("Kategorie strávníků"), 1.0),
            *[(max(header_w("Celkem"), content_w("9999")), 0.0)] * 6,
        ),
    )
    diner_data: list[list[object]] = [[header_para(item) for item in diner_headers]]
    summary_codes = {"0101", "0115"}
    for row in report.section_i:
        style = total if row.code in summary_codes else body
        num_style = total_right if row.code in summary_codes else right
        diner_data.append(
            [
                para(row.code, style, nowrap=True),
                para(row.label, style),
                para(row.columns.total, num_style, nowrap=True),
                para(row.columns.lunch_only, num_style, nowrap=True),
                para(row.columns.lunch_and_supplement, num_style, nowrap=True),
                para(row.columns.supplement_only, num_style, nowrap=True),
                para(row.columns.all_day, num_style, nowrap=True),
                para(row.columns.all_day_without_lunch, num_style, nowrap=True),
            ]
        )
    diner_table = style_table(LongTable(diner_data, colWidths=diner_widths, repeatRows=1))

    meal_headers = (
        "Řádek",
        "Druh jídla",
        "Školní rok<br/>tis. sl. 2",
        "Říjen<br/>sl. 3",
        "Šk. rok školní<br/>+ závodní sl. 4≈5a",
        "Říjen školní<br/>+ závodní sl. 3a",
    )
    meal_widths = fit_column_widths(
        usable_width,
        (
            (max(header_w("Řádek"), content_w("0309")), 0.0),
            (header_w("Druh jídla"), 1.0),
            (max(header_w("Školní rok"), content_w("000,0")), 0.08),
            (max(header_w("Říjen"), content_w("99999")), 0.08),
            (max(header_w("Šk. rok školní"), content_w("000,0")), 0.10),
            (max(header_w("Říjen školní"), content_w("99999")), 0.10),
        ),
    )
    meal_data: list[list[object]] = [[header_para(item) for item in meal_headers]]
    for row in report.section_iii:
        meal_data.append(
            [
                para(row.code, nowrap=True),
                para(row.label),
                para(format_thousands(row.school_year), right, nowrap=True),
                para(row.october, right, nowrap=True),
                para(format_thousands(row.school_year_school), right, nowrap=True),
                para(row.october_school, right, nowrap=True),
            ]
        )
    meal_table = style_table(LongTable(meal_data, colWidths=meal_widths, repeatRows=1))

    source_headers = (
        "Kat.",
        "Název / mapování",
        "Říjen<br/>osob",
        "Šk. rok<br/>porcí",
        "Říjen<br/>porcí",
    )
    source_widths = fit_column_widths(
        usable_width,
        (
            (max(header_w("Kat."), content_w("ZZZZZZ")), 0.08),
            (header_w("Název / mapování"), 1.0),
            (max(header_w("Říjen"), content_w("9999")), 0.0),
            (max(header_w("Šk. rok"), content_w("999999")), 0.0),
            (max(header_w("Říjen"), content_w("99999")), 0.0),
        ),
    )
    source_data: list[list[object]] = [[header_para(item) for item in source_headers]]
    for item in report.breakdown:
        mapping = ", ".join(item.assigned_rows) if item.assigned_rows else "nenamapováno"
        guessed = " (odhad)" if item.guessed and item.assigned_rows else ""
        source_data.append(
            [
                para(item.code, nowrap=True),
                para(f"{item.name or ''} → {mapping}{guessed}".strip()),
                para(item.october_diners, right, nowrap=True),
                para(sum(item.school_year_meals.values()), right, nowrap=True),
                para(sum(item.october_meals.values()), right, nowrap=True),
            ]
        )
    source_table = style_table(LongTable(source_data, colWidths=source_widths, repeatRows=1))

    story: list[object] = [
        para("Podklad k výkazu Z 17-01", title),
        para(
            f"Stav k 31. 10. {report.year} · školní rok {report.school_year_label} "
            f"(1. 9. {report.year - 1} – 31. 8. {report.year})",
            section,
        ),
        para(report.header.subject_name or "", body),
        para(report.header.address or "", small),
        para(
            " ".join(part for part in (report.header.zip_code, report.header.city) if part),
            small,
        ),
        para(
            "Toto není oficiální formulář MŠMT. Čísla jsou z přihlášek Jídelny, "
            "aby je nebylo nutné sčítat z měsíčních rekapitulací.",
            small,
        ),
        Spacer(1, 2 * mm),
        para("Oddíl I – zapsaní strávníci k 31. 10.", section),
        diner_table,
        Spacer(1, 3 * mm),
        para("Oddíl III – vydaná jídla (uvařená = vydaná, pokud neodvážíte stravu)", section),
        para(
            "Sloupce školního roku jsou v tisících na 1 desetinné místo, říjen v kusech. "
            "Školní + závodní odpovídá sl. 3a / 5a (děti/žáci a vlastní zaměstnanci).",
            small,
        ),
        meal_table,
        Spacer(1, 3 * mm),
        para("Rozpad podle kategorií Jídelny", section),
        source_table,
        Spacer(1, 2 * mm),
        para(
            "Oddíly II, IV, V a VII (odvozy, úvazky, IZO škol) a dietní řádky "
            "0101a / 3b / 5b tato sestava nesestavuje — v Jídelně k tomu nejsou "
            "spolehlivé podklady. Mapování kategorií upravte v config.json, blok z17.",
            small,
        ),
    ]
    if report.unmapped:
        story.append(
            para(
                "Bez přiřazeného řádku: " + "; ".join(report.unmapped),
                small,
            )
        )

    def draw_page(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(muted)
        canvas.setFont(regular, 8)
        canvas.drawString(left_margin, 8 * mm, f"Podklad Z 17-01 · {report.year}")
        canvas.drawRightString(
            page_width - right_margin,
            8 * mm,
            f"Strana {document.page}",
        )
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(target),
        pagesize=portrait(A4),
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=f"Podklad Z 17-01 {report.year}",
        author="AutoReport",
    )
    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return target


def export_z17_pdf(
    config: AppConfig,
    settings: Z17Settings,
    on_progress: Any = None,
) -> Path:
    report = fetch_z17_report(config, settings, on_progress=on_progress)
    report_progress(on_progress, 0.92, "Z 17-01: skládám PDF…")
    output = settings.output_directory / f"Z17-01_podklad_{settings.year}.pdf"
    created = create_z17_pdf(config, report, output)
    report_progress(on_progress, 1.0, f"Z 17-01: uloženo {created.name}")
    return created
