"""Měsíční rekapitulace podle šablony RekapitulaceR a funkcí Jídelny."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from stravovaci_sestava import AppConfig
from uzaverka_nastaveni import ClosingSettings
from uzaverka_pdf import (
    SubjectHeader,
    cell_markup,
    fit_column_widths,
    format_money,
    measure_text_width,
    period_title,
    register_report_fonts,
    report_progress,
    require_pdf_path,
)
from uzaverka_podklady import ClosingPodklady, in_categories, recap_tuple

RECAP_TITLES = {
    "R": "Rozšířená rekapitulace",
    "S": "Rekapitulace",
    "ST": "Rekapitulace ST",
}


@dataclass(frozen=True)
class RecapRow:
    category_code: str
    category_name: str | None
    meal_type: str
    norm: str | None
    portions: int
    monthly_rate: float
    monthly_limit: float
    fksp: float
    other_overhead: float
    payment: float
    credit_prev: float
    credit_now: float
    registered: int
    dining: int
    underpay_prev: float = 0.0
    underpay_now: float = 0.0

    @property
    def daily_rate(self) -> float:
        if self.portions <= 0:
            return 0.0
        return self.monthly_rate / self.portions

    @property
    def daily_limit(self) -> float:
        if self.portions <= 0:
            return 0.0
        return self.monthly_limit / self.portions

    @property
    def debit_prev(self) -> float:
        return self.underpay_prev

    @property
    def debit_now(self) -> float:
        return self.underpay_now

    @property
    def credit_prev_plus(self) -> float:
        return max(self.credit_prev, 0)

    @property
    def credit_now_plus(self) -> float:
        return max(self.credit_now, 0)


@dataclass(frozen=True)
class RecapCounts:
    dining: int
    registered: int
    enrolled: int
    bulk: int

    @property
    def dining_with_bulk(self) -> int:
        return self.dining + self.bulk

    @property
    def registered_with_bulk(self) -> int:
        return self.registered + self.bulk

    @property
    def enrolled_with_bulk(self) -> int:
        return self.enrolled + self.bulk


@dataclass(frozen=True)
class RecapReport:
    header: SubjectHeader
    rows: tuple[RecapRow, ...]
    counts: RecapCounts
    variant: str
    period: date


def _aggregate_rows(
    records: Sequence[Sequence[Any]],
    counts: dict[str, tuple[int, int]],
) -> tuple[RecapRow, ...]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    people: dict[tuple[str, str], set[int]] = {}
    for record in records:
        category = str(record[0] or "").strip()
        meal_type = str(record[3] or "").strip()
        key = (category, meal_type)
        bucket = grouped.setdefault(
            key,
            {
                "name": record[1],
                "norm": record[2],
                "portions": 0,
                "rate": 0.0,
                "limit": 0.0,
                "fksp": 0.0,
                "other": 0.0,
                "payment": 0.0,
                "credit_prev": 0.0,
                "credit_now": 0.0,
                "underpay_prev": 0.0,
                "underpay_now": 0.0,
            },
        )
        bucket["portions"] += int(record[4] or 0)
        bucket["rate"] += float(record[5] or 0)
        bucket["limit"] += float(record[6] or 0)
        bucket["fksp"] += float(record[7] or 0)
        bucket["other"] += float(record[8] or 0)
        people.setdefault(key, set()).add(int(record[12] or 0))
        # platba / přeplatky jsou za strávníka, ne za řádek přihlášky
    seen_person: dict[str, set[int]] = {}
    for record in records:
        category = str(record[0] or "").strip()
        evid = int(record[12] or 0)
        used = seen_person.setdefault(category, set())
        if evid in used:
            continue
        used.add(evid)
        payment = float(record[9] or 0)
        opening = float(record[10] or 0)
        month_paid = float(record[11] or 0)
        for key, bucket in grouped.items():
            if key[0] != category:
                continue
            bucket["payment"] += max(payment, 0)
            bucket["underpay_now"] += abs(min(payment, 0))
            bucket["credit_prev"] += max(opening, 0)
            bucket["underpay_prev"] += abs(min(opening, 0))
            bucket["credit_now"] += month_paid
            break

    rows: list[RecapRow] = []
    for (category, meal_type), bucket in grouped.items():
        registered, dining = counts.get(category, (0, 0))
        rows.append(
            RecapRow(
                category_code=category,
                category_name=bucket["name"],
                meal_type=meal_type,
                norm=bucket["norm"],
                portions=int(bucket["portions"]),
                monthly_rate=float(bucket["rate"]),
                monthly_limit=float(bucket["limit"]),
                fksp=float(bucket["fksp"]),
                other_overhead=float(bucket["other"]),
                payment=float(bucket["payment"]),
                credit_prev=float(bucket["credit_prev"]),
                credit_now=float(bucket["credit_now"]),
                registered=registered,
                dining=dining,
                underpay_prev=float(bucket["underpay_prev"]),
                underpay_now=float(bucket["underpay_now"]),
            )
        )
    rows.sort(key=lambda item: (item.category_code.lower(), item.meal_type.lower()))
    return tuple(rows)


def recap_report_from_podklady(
    podklady: ClosingPodklady,
    *,
    categories: Sequence[str],
    variant: str,
) -> RecapReport:
    """Složí rekapitulaci ze sdílených podkladů uzávěrky."""
    records = [
        recap_tuple(row)
        for row in podklady.individuals
        if in_categories(row.category_code, categories)
    ]
    records.extend(
        recap_tuple(row)
        for row in podklady.bulk
        if in_categories(row.category_code, categories)
    )
    counts = {
        code: values
        for code, values in podklady.counts.by_category.items()
        if in_categories(code, categories)
    }
    return RecapReport(
        header=podklady.header,
        rows=_aggregate_rows(records, counts),
        counts=RecapCounts(
            dining=podklady.counts.dining,
            registered=podklady.counts.registered,
            enrolled=podklady.counts.enrolled,
            bulk=podklady.counts.bulk,
        ),
        variant=variant,
        period=podklady.period,
    )


def fetch_recap_report(
    config: AppConfig,
    *,
    variant: str,
    on_progress: Any = None,
    podklady: ClosingPodklady | None = None,
) -> RecapReport:
    """Načte řádky rekapitulace z funkcí a tabulek Jídelny."""
    from uzaverka_podklady import fetch_closing_podklady

    if podklady is None:
        podklady = fetch_closing_podklady(config, on_progress=on_progress)
    return recap_report_from_podklady(
        podklady,
        categories=config.categories,
        variant=variant,
    )


def create_recap_pdf(
    config: AppConfig,
    report: RecapReport,
    output_path: Path,
) -> Path:
    """Vytvoří tiskové PDF rekapitulace."""
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

    target = require_pdf_path(output_path, label="rekapitulace")
    regular, bold = register_report_fonts()
    page_width, page_height = portrait(A4)
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
    title_name = RECAP_TITLES.get(report.variant, "Rekapitulace")

    body = ParagraphStyle(
        "RecapBody",
        fontName=data_font,
        fontSize=data_size,
        leading=max(data_size + 1.6, data_size * 1.18),
        textColor=text_color,
        alignment=TA_LEFT,
        splitLongWords=0,
    )
    right = ParagraphStyle("RecapRight", parent=body, alignment=TA_RIGHT)
    total = ParagraphStyle("RecapTotal", parent=body, fontName=bold, textColor=total_red)
    total_right = ParagraphStyle("RecapTotalRight", parent=right, fontName=bold, textColor=total_red)
    header_cell = ParagraphStyle(
        "RecapHeaderCell",
        parent=body,
        fontName=bold,
        fontSize=max(6.6, label_size * 0.82),
        leading=max(8.4, label_size * 1.05),
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    title = ParagraphStyle(
        "RecapTitle",
        parent=body,
        fontName=bold,
        fontSize=max(13, label_size * 1.7),
        leading=max(16, label_size * 2.1),
        textColor=navy,
    )
    section = ParagraphStyle(
        "RecapSection",
        parent=body,
        fontName=bold,
        fontSize=max(9, label_size * 1.2),
        textColor=navy,
        spaceBefore=3 * mm,
        spaceAfter=1.5 * mm,
        keepWithNext=True,
    )
    small = ParagraphStyle(
        "RecapSmall",
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
    money_sample = format_money(
        max(
            999_999.99,
            *(abs(row.monthly_limit) for row in report.rows),
            *(abs(row.monthly_rate) for row in report.rows),
            *(abs(row.credit_prev_plus) for row in report.rows),
            *(abs(row.debit_prev) for row in report.rows),
            *(abs(row.payment) for row in report.rows),
            *(abs(row.fksp) for row in report.rows),
            *(abs(row.credit_now_plus) for row in report.rows),
            *(abs(row.debit_now) for row in report.rows),
            *(abs(row.other_overhead) for row in report.rows),
            abs(sum(row.monthly_limit for row in report.rows)),
            abs(sum(row.monthly_rate for row in report.rows)),
            abs(sum(row.credit_prev_plus for row in report.rows)),
            abs(sum(row.payment for row in report.rows)),
        )
    )
    portion_sample = str(
        max(999, *(row.portions for row in report.rows), sum(row.portions for row in report.rows))
    )
    type_sample = max(
        ["Typ / N", "Oběd C", *(f"{row.meal_type} {row.norm or ''}".strip() for row in report.rows)],
        key=len,
    )
    evid_sample = max(
        ["999/999", *(f"{row.dining}/{row.registered}" for row in report.rows)],
        key=len,
    )

    def content_w(*samples: object, font: str = data_font, size: float = data_size) -> float:
        return max(measure_text_width(str(sample), font, size) for sample in samples) + cell_pad

    def header_w(*lines: str) -> float:
        return content_w(*lines, font=bold, size=header_size)

    # Pořadí sloupců podle šablony RekapitulaceR / tisku Jídelny.
    meal_widths = fit_column_widths(
        usable_width,
        (
            (header_w("Kategorie"), 1.0),
            (max(header_w("Typ / N"), content_w(type_sample)), 0.05),
            (max(header_w("Porcí"), content_w(portion_sample, font=bold)), 0.0),
            (max(header_w("Limit", "den"), content_w("105")), 0.0),
            (max(header_w("Sazba", "den"), content_w("105")), 0.0),
            (max(header_w("Limit"), content_w(money_sample, font=bold)), 0.12),
            (max(header_w("Evid./", "strav."), content_w(evid_sample)), 0.04),
            (max(header_w("Nedo.", "MM"), content_w(money_sample, font=bold)), 0.10),
            (max(header_w("Přepl.", "MM"), content_w(money_sample, font=bold)), 0.14),
            (max(header_w("Předpis"), content_w(money_sample, font=bold)), 0.12),
        ),
    )
    finance_widths = fit_column_widths(
        usable_width,
        (
            (header_w("Kategorie"), 1.0),
            (max(header_w("Typ / N"), content_w(type_sample)), 0.05),
            (max(header_w("Placeno"), content_w(money_sample, font=bold)), 0.12),
            (max(header_w("FKSP"), content_w(money_sample, font=bold)), 0.08),
            (max(header_w("Nedo.", "AM"), content_w(money_sample, font=bold)), 0.08),
            (max(header_w("Přepl.", "AM"), content_w(money_sample, font=bold)), 0.10),
            (max(header_w("Ostatní", "režie"), content_w(money_sample, font=bold)), 0.10),
        ),
    )

    def style_table(table: LongTable, *, bold_totals: bool = False) -> LongTable:
        commands = [
            ("BACKGROUND", (0, 0), (-1, 0), navy),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), bold),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (2, 0), (-1, 0), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.35, medium_gray),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, pale_gray]),
            ("BACKGROUND", (0, -1), (-1, -1), pale_blue),
            ("LEFTPADDING", (0, 0), (-1, -1), 0.7 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0.7 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 0.9 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0.9 * mm),
        ]
        if bold_totals:
            commands.extend(
                [
                    ("FONTNAME", (0, -1), (-1, -1), bold),
                    ("TEXTCOLOR", (0, -1), (-1, -1), total_red),
                ]
            )
        table.setStyle(TableStyle(commands))
        return table

    meal_headers = (
        "Kategorie",
        "Typ / N",
        "Porcí",
        "Limit/<br/>den",
        "Sazba/<br/>den",
        "Limit",
        "Evid./<br/>strav.",
        "Nedo.<br/>MM",
        "Přepl.<br/>MM",
        "Předpis",
    )
    meal_data = [[header_para(item) for item in meal_headers]]
    for row in report.rows:
        label = f"{row.category_code}  {row.category_name or ''}".strip()
        meal_data.append(
            [
                para(label),
                para(f"{row.meal_type} {row.norm or ''}"),
                para(row.portions, right, nowrap=True),
                para(f"{row.daily_limit:.0f}", right, nowrap=True),
                para(f"{row.daily_rate:.0f}", right, nowrap=True),
                para(format_money(row.monthly_limit), right, nowrap=True),
                para(f"{row.dining}/{row.registered}", right, nowrap=True),
                para(format_money(row.debit_prev), right, nowrap=True),
                para(format_money(row.credit_prev_plus), right, nowrap=True),
                para(format_money(row.monthly_rate), right, nowrap=True),
            ]
        )
    meal_data.append(
        [
            para("Celkem", total),
            para(""),
            para(sum(row.portions for row in report.rows), total_right, nowrap=True),
            para(""),
            para(""),
            para(format_money(sum(row.monthly_limit for row in report.rows)), total_right, nowrap=True),
            para(""),
            para(format_money(sum(row.debit_prev for row in report.rows)), total_right, nowrap=True),
            para(format_money(sum(row.credit_prev_plus for row in report.rows)), total_right, nowrap=True),
            para(format_money(sum(row.monthly_rate for row in report.rows)), total_right, nowrap=True),
        ]
    )
    meal_table = style_table(
        LongTable(meal_data, colWidths=meal_widths, repeatRows=1),
        bold_totals=True,
    )

    finance_headers = (
        "Kategorie",
        "Typ / N",
        "Placeno",
        "FKSP",
        "Nedo.<br/>AM",
        "Přepl.<br/>AM",
        "Ostatní<br/>režie",
    )
    finance_data = [[header_para(item) for item in finance_headers]]
    for row in report.rows:
        label = f"{row.category_code}  {row.category_name or ''}".strip()
        finance_data.append(
            [
                para(label),
                para(f"{row.meal_type} {row.norm or ''}"),
                # Jídelna: Placeno AM = platby v měsíci, Přeplatek AM = kladný zůstatek
                para(format_money(row.credit_now_plus), right, nowrap=True),
                para(format_money(row.fksp), right, nowrap=True),
                para(format_money(row.debit_now), right, nowrap=True),
                para(format_money(row.payment), right, nowrap=True),
                para(format_money(row.other_overhead), right, nowrap=True),
            ]
        )
    finance_data.append(
        [
            para("Celkem", total),
            para(""),
            para(format_money(sum(row.credit_now_plus for row in report.rows)), total_right, nowrap=True),
            para(format_money(sum(row.fksp for row in report.rows)), total_right, nowrap=True),
            para(format_money(sum(row.debit_now for row in report.rows)), total_right, nowrap=True),
            para(format_money(sum(row.payment for row in report.rows)), total_right, nowrap=True),
            para(format_money(sum(row.other_overhead for row in report.rows)), total_right, nowrap=True),
        ]
    )
    finance_table = style_table(
        LongTable(finance_data, colWidths=finance_widths, repeatRows=1),
        bold_totals=True,
    )

    counts = report.counts
    count_data = [
        [para("Počty strávníků", header_cell), para("Bez hromadných", header_cell), para("Včetně hromadných", header_cell)],
        [para("stravujících se"), para(counts.dining, right), para(counts.dining_with_bulk, right)],
        [para("evidovaných"), para(counts.registered, right), para(counts.registered_with_bulk, right)],
        [para("zapsaných"), para(counts.enrolled, right), para(counts.enrolled_with_bulk, right)],
        [para("hromadných"), para(counts.bulk, right), para(counts.bulk, right)],
    ]
    count_table = style_table(
        LongTable(count_data, colWidths=[usable_width * 0.40, usable_width * 0.30, usable_width * 0.30])
    )

    story: list[object] = [
        para(title_name, title),
        para(
            f"Rekapitulace stravovaných osob a poplatků za měsíc "
            f"{period_title(report.period.month, report.period.year)}",
            section,
        ),
        para(report.header.subject_name or "", body),
        para(report.header.address or "", small),
        para(
            " ".join(
                part
                for part in (report.header.zip_code, report.header.city)
                if part
            ),
            small,
        ),
        Spacer(1, 2 * mm),
        meal_table,
        Spacer(1, 3 * mm),
        para("Platby, FKSP a režie", section),
        finance_table,
        Spacer(1, 3 * mm),
        count_table,
        para(
            "stravující se = odebrali alespoň 1 stravu; evidovaní = mají vytvořený rozpis; "
            "zapsaní = všichni strávníci v databázi.",
            small,
        ),
    ]

    def draw_page(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(muted)
        canvas.setFont(regular, 8)
        canvas.drawString(
            left_margin,
            8 * mm,
            f"{title_name} {period_title(report.period.month, report.period.year)}",
        )
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
        title=f"{title_name} {period_title(report.period.month, report.period.year)}",
        author="MailPilot",
    )
    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return target


def export_recap_pdf(
    config: AppConfig,
    settings: ClosingSettings,
    on_progress: Any = None,
    podklady: ClosingPodklady | None = None,
) -> Path:
    """Načte data a uloží PDF do složky uzávěrky."""
    report = fetch_recap_report(
        config,
        variant=settings.recap_variant,
        on_progress=on_progress,
        podklady=podklady,
    )
    report_progress(
        on_progress,
        0.08 if podklady is not None else 0.90,
        "Rekapitulace: skládám PDF…",
    )
    output = settings.output_directory / f"Rekapitulace_{settings.period_stamp}.pdf"
    created = create_recap_pdf(config, report, output)
    report_progress(on_progress, 1.0, f"Rekapitulace: uloženo {created.name}")
    return created
