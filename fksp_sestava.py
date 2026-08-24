"""Měsíční sestava FKSP podle šablony FKSPnew a funkcí Jídelny."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from stravovaci_sestava import AppConfig, ConfigError
from uzaverka_nastaveni import ClosingSettings, czech_month_name


HEADER_QUERY = """
        SELECT LOWER(BTRIM(parametr)) AS parametr, NULLIF(BTRIM(hodnota), '')
        FROM public.parametry
        WHERE LOWER(BTRIM(sekce)) = LOWER('BACKUP')
          AND LOWER(BTRIM(parametr)) = ANY(%s::varchar[])
"""

HEADER_KEYS = (
    "namesubject",
    "adrsubject",
    "pscsubject",
    "mestosubject",
    "ico",
    "dic",
)


@dataclass(frozen=True)
class FkspRow:
    name: str | None
    category_code: str
    category_name: str | None
    meal_type: str
    portions: int
    total_amount: float
    other_overhead: float

    @property
    def unit_amount(self) -> float:
        if self.portions <= 0:
            return 0.0
        return self.total_amount / self.portions


@dataclass(frozen=True)
class FkspCategoryTotal:
    category_code: str
    category_name: str | None
    meal_type: str
    portions: int
    total_amount: float
    other_overhead: float


@dataclass(frozen=True)
class FkspHeader:
    subject_name: str | None
    address: str | None
    zip_code: str | None
    city: str | None
    company_id: str | None
    vat_id: str | None


@dataclass(frozen=True)
class FkspReport:
    header: FkspHeader
    individuals: tuple[FkspRow, ...]
    bulk: tuple[FkspRow, ...]
    period: date


def format_money(value: float) -> str:
    """Částka ve tvaru 4.560,00 Kč."""
    sign = "-" if value < 0 else ""
    number = abs(float(value))
    whole, fraction = f"{number:.2f}".split(".")
    groups: list[str] = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    grouped = ".".join(reversed(groups))
    return f"{sign}{grouped},{fraction}\u00a0Kč"


def _aggregate_categories(rows: Sequence[FkspRow]) -> tuple[FkspCategoryTotal, ...]:
    grouped: dict[tuple[str, str], list[FkspRow]] = {}
    for row in rows:
        grouped.setdefault((row.category_code, row.meal_type), []).append(row)
    totals = []
    for (category_code, meal_type), items in grouped.items():
        totals.append(
            FkspCategoryTotal(
                category_code=category_code,
                category_name=items[0].category_name,
                meal_type=meal_type,
                portions=sum(item.portions for item in items),
                total_amount=sum(item.total_amount for item in items),
                other_overhead=sum(item.other_overhead for item in items),
            )
        )
    totals.sort(key=lambda item: (item.category_code.lower(), item.meal_type.lower()))
    return tuple(totals)


def _row_from_podklad(row: Any, *, diner_category: bool) -> FkspRow:
    return FkspRow(
        name=row.name,
        category_code=row.diner_category if diner_category else row.category_code,
        category_name=row.diner_category_name if diner_category else row.category_name,
        meal_type=row.meal_type,
        portions=row.portions_live if diner_category else row.portions,
        total_amount=row.fksp_diner if diner_category else row.fksp,
        other_overhead=row.other_overhead_diner if diner_category else row.other_overhead,
    )


def _has_nonzero_fksp(value: float, *, epsilon: float = 0.0001) -> bool:
    """FKSP sazba 0.00 je mimo sestavu; bereme jen nenulové hodnoty."""
    return abs(float(value)) > epsilon


def fksp_report_from_podklady(podklady: Any, *, categories: Sequence[str]) -> FkspReport:
    """Složí sestavu FKSP ze sdílených podkladů uzávěrky."""
    from uzaverka_podklady import in_categories

    individuals = tuple(
        sorted(
            (
                _row_from_podklad(row, diner_category=True)
                for row in podklady.individuals
                if not row.deleted
                and row.portions_live > 0
                and in_categories(row.diner_category, categories)
                and _has_nonzero_fksp(row.fksp_diner)
            ),
            key=lambda item: (
                (item.name or "").lower(),
                item.name or "",
                item.meal_type.lower(),
            ),
        )
    )
    bulk = tuple(
        sorted(
            (
                _row_from_podklad(row, diner_category=False)
                for row in podklady.bulk
                if not row.deleted
                and row.portions > 0
                and in_categories(row.category_code, categories)
                and _has_nonzero_fksp(row.fksp)
            ),
            key=lambda item: (
                (item.name or "").lower(),
                item.name or "",
                item.meal_type.lower(),
            ),
        )
    )
    header = podklady.header
    return FkspReport(
        header=FkspHeader(
            subject_name=header.subject_name,
            address=header.address,
            zip_code=header.zip_code,
            city=header.city,
            company_id=header.company_id,
            vat_id=header.vat_id,
        ),
        individuals=individuals,
        bulk=bulk,
        period=podklady.period,
    )


def fetch_fksp_report(
    config: AppConfig,
    on_progress: Any = None,
    podklady: Any = None,
) -> FkspReport:
    """Načte řádky FKSP z funkcí a tabulek Jídelny."""
    from uzaverka_podklady import fetch_closing_podklady

    if podklady is None:
        podklady = fetch_closing_podklady(config, on_progress=on_progress)
    return fksp_report_from_podklady(podklady, categories=config.categories)


def create_fksp_pdf(
    config: AppConfig,
    report: FkspReport,
    output_path: Path,
) -> Path:
    """Vytvoří tiskové PDF FKSP a vrátí jeho absolutní cestu."""
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

    from uzaverka_pdf import cell_markup, fit_column_widths, measure_text_width, register_report_fonts

    target = output_path.resolve()
    if target.suffix.lower() != ".pdf":
        raise ConfigError("Výstupní soubor FKSP musí mít příponu .pdf.")
    target.parent.mkdir(parents=True, exist_ok=True)

    regular, bold = register_report_fonts()
    data_font = bold if config.pdf_bold else regular

    page_width, page_height = portrait(A4)
    left_margin = 10 * mm
    right_margin = 10 * mm
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

    body = ParagraphStyle(
        "FkspBody",
        fontName=data_font,
        fontSize=data_size,
        leading=max(data_size + 1.6, data_size * 1.18),
        textColor=text_color,
        alignment=TA_LEFT,
        splitLongWords=0,
    )
    right = ParagraphStyle("FkspRight", parent=body, alignment=TA_RIGHT)
    total = ParagraphStyle("FkspTotal", parent=body, fontName=bold, textColor=total_red)
    total_right = ParagraphStyle("FkspTotalRight", parent=right, fontName=bold, textColor=total_red)
    header_cell = ParagraphStyle(
        "FkspHeaderCell",
        parent=body,
        fontName=bold,
        fontSize=max(6.8, label_size * 0.88),
        leading=max(8.6, label_size * 1.08),
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    title = ParagraphStyle(
        "FkspTitle",
        parent=body,
        fontName=bold,
        fontSize=max(16, label_size * 2.2),
        leading=max(20, label_size * 2.6),
        textColor=navy,
    )
    section = ParagraphStyle(
        "FkspSection",
        parent=body,
        fontName=bold,
        fontSize=max(10, label_size * 1.4),
        textColor=navy,
        spaceBefore=4 * mm,
        spaceAfter=2 * mm,
    )
    small = ParagraphStyle(
        "FkspSmall",
        parent=body,
        fontSize=max(7, data_size * 0.95),
        textColor=muted,
    )

    def para(value: object, style: ParagraphStyle = body, *, nowrap: bool = False) -> Paragraph:
        return Paragraph(cell_markup(value, nowrap=nowrap), style)

    def header_para(markup: str) -> Paragraph:
        return Paragraph(markup, header_cell)

    all_rows = tuple(report.individuals) + tuple(report.bulk)
    cell_pad = 2.0 * mm
    header_size = header_cell.fontSize
    money_sample = format_money(
        max(
            99_999.99,
            *(abs(row.total_amount) for row in all_rows),
            *(abs(row.other_overhead) for row in all_rows),
            *(abs(row.unit_amount) for row in all_rows),
            abs(sum(row.total_amount for row in report.individuals)),
            abs(sum(row.total_amount for row in report.bulk)),
        )
    )
    type_sample = max(
        ["Typ služby", "Oběd", *(row.meal_type for row in all_rows)],
        key=len,
    )
    portion_sample = str(
        max(
            999,
            *(row.portions for row in all_rows),
            sum(row.portions for row in report.individuals),
            sum(row.portions for row in report.bulk),
        )
    )

    def content_w(*samples: object, font: str = data_font, size: float = data_size) -> float:
        return max(measure_text_width(str(sample), font, size) for sample in samples) + cell_pad

    def header_w(*lines: str) -> float:
        return content_w(*lines, font=bold, size=header_size)

    widths = fit_column_widths(
        usable_width,
        (
            (header_w("Jméno"), 1.0),
            (max(header_w("Kategorie"), content_w("99")), 0.04),
            (max(header_w("Počet"), content_w(portion_sample, font=bold)), 0.0),
            (max(header_w("Typ", "služby"), content_w(type_sample)), 0.08),
            (max(header_w("FKSP"), content_w(money_sample, font=bold)), 0.10),
            (max(header_w("Ostatní", "režie"), content_w(money_sample, font=bold)), 0.12),
            (max(header_w("Celkem", "FKSP"), content_w(money_sample, font=bold)), 0.14),
        ),
    )
    headers = (
        "Jméno",
        "Kategorie",
        "Počet",
        "Typ<br/>služby",
        "FKSP",
        "Ostatní<br/>režie",
        "Celkem<br/>FKSP",
    )

    def table_from_rows(rows: Sequence[FkspRow], *, totals_label: str) -> LongTable:
        data: list[list[object]] = [[header_para(item) for item in headers]]
        for row in rows:
            data.append(
                [
                    para(row.name or ""),
                    para(row.category_code, nowrap=True),
                    para(row.portions, right, nowrap=True),
                    para(row.meal_type),
                    para(format_money(row.unit_amount), right, nowrap=True),
                    para(format_money(row.other_overhead), right, nowrap=True),
                    para(format_money(row.total_amount), right, nowrap=True),
                ]
            )
        data.append(
            [
                para(totals_label, total),
                para(""),
                para(sum(row.portions for row in rows), total_right, nowrap=True),
                para(""),
                para(""),
                para(format_money(sum(row.other_overhead for row in rows)), total_right, nowrap=True),
                para(format_money(sum(row.total_amount for row in rows)), total_right, nowrap=True),
            ]
        )
        table = LongTable(data, colWidths=widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), navy),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), bold),
                    ("FONTNAME", (0, 1), (-1, -1), data_font),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.35, medium_gray),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, pale_gray]),
                    ("BACKGROUND", (0, -1), (-1, -1), pale_blue),
                    ("FONTNAME", (0, -1), (-1, -1), bold),
                    ("TEXTCOLOR", (0, -1), (-1, -1), total_red),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0.9 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0.9 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 0.9 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0.9 * mm),
                ]
            )
        )
        return table

    story: list[object] = [
        para("FKSP", title),
        para(
            f"za měsíc: {czech_month_name(report.period.month)} {report.period.year}",
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
        para(
            "   ".join(
                part
                for part in (
                    f"IČO: {report.header.company_id}" if report.header.company_id else "",
                    f"DIČ: {report.header.vat_id}" if report.header.vat_id else "",
                )
                if part
            ),
            small,
        ),
        Spacer(1, 3 * mm),
        para("FKSP strávníků", section),
    ]
    if report.individuals:
        story.append(table_from_rows(report.individuals, totals_label="Celkem"))
    else:
        story.append(para("Za zvolený měsíc nejsou žádné přihlášky s FKSP.", small))

    category_totals = _aggregate_categories(report.individuals)
    if category_totals:
        story.append(para("FKSP podle kategorií", section))
        category_data: list[list[object]] = [
            [
                header_para(item)
                for item in (
                    "Kategorie",
                    "Počet",
                    "Typ<br/>služby",
                    "Ostatní<br/>režie",
                    "Celkem<br/>FKSP",
                )
            ]
        ]
        category_widths = fit_column_widths(
            usable_width,
            (
                (header_w("Kategorie"), 1.0),
                (max(header_w("Počet"), content_w(portion_sample)), 0.0),
                (max(header_w("Typ", "služby"), content_w(type_sample)), 0.10),
                (max(header_w("Ostatní", "režie"), content_w(money_sample)), 0.16),
                (max(header_w("Celkem", "FKSP"), content_w(money_sample)), 0.18),
            ),
        )
        for item in category_totals:
            label = item.category_name or item.category_code
            category_data.append(
                [
                    para(f"{item.category_code}  {label}"),
                    para(item.portions, right, nowrap=True),
                    para(item.meal_type),
                    para(format_money(item.other_overhead), right, nowrap=True),
                    para(format_money(item.total_amount), right, nowrap=True),
                ]
            )
        category_table = LongTable(category_data, colWidths=category_widths, repeatRows=1)
        category_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), navy),
                    ("GRID", (0, 0), (-1, -1), 0.35, medium_gray),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, pale_gray]),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0.9 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0.9 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 0.9 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0.9 * mm),
                ]
            )
        )
        story.append(category_table)

    story.append(para("FKSP hromadných strávníků", section))
    if report.bulk:
        story.append(
            table_from_rows(report.bulk, totals_label="Celkové součty hromadného strávníka")
        )
    else:
        story.append(para("Hromadní strávníci v tomto měsíci nemají přihlášky.", small))

    def draw_page(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(muted)
        canvas.setFont(regular, 8)
        canvas.drawString(
            left_margin,
            10 * mm,
            f"FKSP {czech_month_name(report.period.month)} {report.period.year}",
        )
        canvas.drawRightString(
            page_width - right_margin,
            10 * mm,
            f"Strana {document.page}",
        )
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(target),
        pagesize=portrait(A4),
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"FKSP {czech_month_name(report.period.month)} {report.period.year}",
        author="MailPilot",
    )
    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return target


def export_fksp_pdf(
    config: AppConfig,
    settings: ClosingSettings,
    on_progress: Any = None,
    podklady: Any = None,
) -> Path:
    """Načte data a uloží PDF do složky uzávěrky."""
    report = fetch_fksp_report(config, on_progress=on_progress, podklady=podklady)
    if on_progress is not None:
        on_progress(0.08 if podklady is not None else 0.90, "FKSP: skládám PDF…")
    output = settings.output_directory / f"FKSP_{settings.period_stamp}.pdf"
    created = create_fksp_pdf(config, report, output)
    if on_progress is not None:
        on_progress(1.0, f"FKSP: uloženo {created.name}")
    return created
