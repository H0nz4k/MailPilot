"""Měsíční stravovací arch podle šablony StravovaciArch a funkcí Jídelny."""

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

from uzaverka_podklady import PAYMENT_QUERY, ClosingPodklady, PrihlasPodklad, in_categories


@dataclass(frozen=True)
class ArchMealRow:
    meal_type: str
    days: tuple[str, ...]
    portions: int
    monthly_amount: float

    @property
    def daily_rate(self) -> float:
        if self.portions <= 0:
            return 0.0
        return self.monthly_amount / self.portions


@dataclass(frozen=True)
class ArchPerson:
    name: str | None
    evidence_no: int
    var_symbol: str | None
    class_name: str | None
    category_code: str
    category_name: str | None
    payment_method: str
    payment: float
    credit_prev: float
    credit_now: float
    meals: tuple[ArchMealRow, ...]

    @property
    def portions(self) -> int:
        return sum(item.portions for item in self.meals)

    @property
    def prescription(self) -> float:
        return sum(item.monthly_amount for item in self.meals)


@dataclass(frozen=True)
class ArchReport:
    header: SubjectHeader
    individuals: tuple[ArchPerson, ...]
    bulk: tuple[ArchPerson, ...]
    period: date


def day_mark(value: object) -> str:
    text = str(value or "").strip()
    return text


def _meal_from_podklad(row: PrihlasPodklad) -> ArchMealRow:
    return ArchMealRow(
        meal_type=row.meal_type,
        days=tuple(day_mark(mark) for mark in row.days),
        portions=row.portions,
        monthly_amount=row.prescription,
    )


def _group_people(
    rows: Sequence[PrihlasPodklad],
    payments: dict[str, str],
    categories: Sequence[str],
) -> tuple[ArchPerson, ...]:
    grouped: dict[int, list[PrihlasPodklad]] = {}
    order: list[int] = []
    for row in rows:
        if row.portions <= 0 or not in_categories(row.category_code, categories):
            continue
        grouped.setdefault(row.evidence_no, []).append(row)
        if row.evidence_no not in order:
            order.append(row.evidence_no)
    people: list[ArchPerson] = []
    for evidence_no in order:
        items = grouped[evidence_no]
        first = items[0]
        code = first.payment_method_code
        people.append(
            ArchPerson(
                name=first.name,
                evidence_no=first.evidence_no,
                var_symbol=first.var_symbol,
                class_name=first.class_name,
                category_code=first.category_code,
                category_name=first.category_name,
                payment_method=payments.get(code, "Z běžného účtu" if code == "4" else code),
                payment=first.payment,
                credit_prev=first.credit_prev,
                credit_now=first.credit_now,
                meals=tuple(_meal_from_podklad(item) for item in items),
            )
        )
    return tuple(people)


def arch_report_from_podklady(
    podklady: ClosingPodklady,
    *,
    categories: Sequence[str],
    include_bulk: bool,
) -> ArchReport:
    """Složí stravovací arch ze sdílených podkladů uzávěrky."""
    individuals = _group_people(podklady.individuals, podklady.payments, categories)
    bulk = (
        _group_people(podklady.bulk, podklady.payments, categories)
        if include_bulk
        else ()
    )
    return ArchReport(
        header=podklady.header,
        individuals=individuals,
        bulk=bulk,
        period=podklady.period,
    )


def fetch_arch_report(
    config: AppConfig,
    *,
    include_bulk: bool,
    on_progress: Any = None,
    podklady: ClosingPodklady | None = None,
) -> ArchReport:
    """Načte řádky stravovacího archu z přihlášek a funkcí Jídelny."""
    from uzaverka_podklady import fetch_closing_podklady

    if podklady is None:
        podklady = fetch_closing_podklady(config, on_progress=on_progress)
    return arch_report_from_podklady(
        podklady,
        categories=config.categories,
        include_bulk=include_bulk,
    )


def create_arch_pdf(
    config: AppConfig,
    report: ArchReport,
    output_path: Path,
) -> Path:
    """Vytvoří tiskové PDF stravovacího archu."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib.pagesizes import A4, landscape
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

    target = require_pdf_path(output_path, label="stravovací arch")
    regular, bold = register_report_fonts()
    page_width, page_height = landscape(A4)
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
    data_size = max(6.4, config.pdf_data_font_size - 1.4)
    label_size = max(7.0, config.pdf_label_font_size - 1.0)
    data_font = bold if config.pdf_bold else regular

    body = ParagraphStyle(
        "ArchBody",
        fontName=data_font,
        fontSize=data_size,
        leading=max(data_size + 1.2, data_size * 1.14),
        textColor=text_color,
        alignment=TA_LEFT,
        splitLongWords=0,
    )
    center = ParagraphStyle("ArchCenter", parent=body, alignment=TA_CENTER)
    right = ParagraphStyle("ArchRight", parent=body, alignment=TA_RIGHT)
    total = ParagraphStyle("ArchTotal", parent=body, fontName=bold, textColor=total_red)
    total_right = ParagraphStyle("ArchTotalRight", parent=right, fontName=bold, textColor=total_red)
    header_cell = ParagraphStyle(
        "ArchHeaderCell",
        parent=body,
        fontName=bold,
        fontSize=max(5.8, label_size * 0.82),
        leading=max(7.2, label_size * 0.98),
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    title = ParagraphStyle(
        "ArchTitle",
        parent=body,
        fontName=bold,
        fontSize=max(13, label_size * 1.8),
        leading=max(16, label_size * 2.1),
        textColor=navy,
    )
    section = ParagraphStyle(
        "ArchSection",
        parent=body,
        fontName=bold,
        fontSize=max(9, label_size * 1.2),
        textColor=navy,
        spaceBefore=2 * mm,
        spaceAfter=1.2 * mm,
        keepWithNext=True,
    )
    small = ParagraphStyle(
        "ArchSmall",
        parent=body,
        fontSize=max(6.5, data_size * 0.95),
        textColor=muted,
    )

    def para(value: object, style: ParagraphStyle = body, *, nowrap: bool = False) -> Paragraph:
        return Paragraph(cell_markup(value, nowrap=nowrap), style)

    def para_lines(*parts: str, style: ParagraphStyle = body) -> Paragraph:
        lines = [cell_markup(part) for part in parts if part]
        return Paragraph("<br/>".join(lines), style)

    def header_para(markup: str) -> Paragraph:
        return Paragraph(markup, header_cell)

    people = tuple(report.individuals) + tuple(report.bulk)
    cell_pad = 1.1 * mm
    day_pad = 0.55 * mm
    header_size = header_cell.fontSize
    money_sample = format_money(
        max(
            9_999.99,
            *(abs(person.payment) for person in people),
            *(abs(person.credit_prev) for person in people),
            *(abs(person.credit_now) for person in people),
            *(abs(person.prescription) for person in people),
            *(abs(meal.monthly_amount) for person in people for meal in person.meals),
            abs(sum(person.prescription for person in people)),
            abs(sum(person.payment for person in people)),
        )
    )
    sazba_sample = format_money(
        max(
            999.99,
            *(abs(meal.daily_rate) for person in people for meal in person.meals),
        )
    )
    portion_sample = str(
        max(
            99,
            *(person.portions for person in people),
            *(meal.portions for person in people for meal in person.meals),
            sum(person.portions for person in people),
        )
    )
    type_sample = max(
        ["Typ", "Oběd", *(meal.meal_type for person in people for meal in person.meals)],
        key=len,
    )

    def content_w(*samples: object, font: str = data_font, size: float = data_size, pad: float = cell_pad) -> float:
        return max(measure_text_width(str(sample), font, size) for sample in samples) + pad

    def header_w(*lines: str, pad: float = cell_pad) -> float:
        return content_w(*lines, font=bold, size=header_size, pad=pad)

    day_width = max(header_w("31", pad=day_pad), content_w("S", pad=day_pad))
    widths = fit_column_widths(
        usable_width,
        (
            (header_w("Třída / jméno"), 1.0),
            (max(header_w("VS"), content_w("9999999999")), 0.04),
            (max(header_w("Typ"), content_w(type_sample)), 0.06),
            *[(day_width, 0.0)] * 31,
            (max(header_w("Počet"), content_w(portion_sample, font=bold)), 0.0),
            (max(header_w("Sazba"), content_w(sazba_sample)), 0.04),
            (max(header_w("Předpis"), content_w(money_sample, font=bold)), 0.10),
            (max(header_w("Platba"), content_w(money_sample, font=bold)), 0.10),
            (max(header_w("Přepl.", "MM"), content_w(money_sample, font=bold)), 0.10),
            (max(header_w("Přepl.", "AM"), content_w(money_sample, font=bold)), 0.10),
        ),
    )
    headers = [
        "Třída / jméno",
        "VS",
        "Typ",
        *[str(day) for day in range(1, 32)],
        "Počet",
        "Sazba",
        "Předpis",
        "Platba",
        "Přepl.<br/>MM",
        "Přepl.<br/>AM",
    ]

    def person_rows(people: Sequence[ArchPerson]) -> list[list[object]]:
        data: list[list[object]] = [[header_para(item) for item in headers]]
        last_category = object()
        last_class = object()
        for person in people:
            class_name = person.class_name or "Bez třídy"
            if person.category_code != last_category:
                category_label = f"{person.category_code}  {person.category_name or ''}".strip()
                data.append(
                    [para(category_label, section)] + [para("") for _ in headers[1:]]
                )
                last_category = person.category_code
                last_class = object()
            if class_name != last_class:
                data.append(
                    [para(class_name, section)] + [para("") for _ in headers[1:]]
                )
                last_class = class_name
            first = True
            for meal in person.meals:
                if first:
                    identity = para_lines(
                        person.name or "",
                        person.payment_method,
                    )
                    symbol = para(person.var_symbol or "", nowrap=True)
                    payment = para(format_money(person.payment), right, nowrap=True)
                    prev_credit = para(format_money(max(person.credit_prev, 0)), right, nowrap=True)
                    now_credit = para(format_money(max(person.credit_now, 0)), right, nowrap=True)
                else:
                    identity = para("")
                    symbol = para("")
                    payment = para("")
                    prev_credit = para("")
                    now_credit = para("")
                data.append(
                    [
                        identity,
                        symbol,
                        para(meal.meal_type, nowrap=True),
                        *[para(mark or "", center) for mark in meal.days],
                        para(meal.portions, right, nowrap=True),
                        para(format_money(meal.daily_rate), right, nowrap=True),
                        para(format_money(meal.monthly_amount), right, nowrap=True),
                        payment,
                        prev_credit,
                        now_credit,
                    ]
                )
                first = False
        data.append(
            [
                para("Celkem", total),
                para(""),
                para(""),
                *[para("") for _ in range(31)],
                para(sum(person.portions for person in people), total_right, nowrap=True),
                para(""),
                para(format_money(sum(person.prescription for person in people)), total_right, nowrap=True),
                para(format_money(sum(person.payment for person in people)), total_right, nowrap=True),
                para(format_money(sum(max(person.credit_prev, 0) for person in people)), total_right, nowrap=True),
                para(format_money(sum(max(person.credit_now, 0) for person in people)), total_right, nowrap=True),
            ]
        )
        return data

    def table_from_people(people: Sequence[ArchPerson]) -> LongTable:
        table = LongTable(person_rows(people), colWidths=widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), navy),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), bold),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.25, medium_gray),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, pale_gray]),
                    ("BACKGROUND", (0, -1), (-1, -1), pale_blue),
                    ("FONTNAME", (0, -1), (-1, -1), bold),
                    ("TEXTCOLOR", (0, -1), (-1, -1), total_red),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0.45 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0.45 * mm),
                    ("LEFTPADDING", (3, 0), (33, -1), 0.15 * mm),
                    ("RIGHTPADDING", (3, 0), (33, -1), 0.15 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 0.55 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0.55 * mm),
                    ("SPAN", (0, 0), (0, 0)),
                ]
            )
        )
        return table

    story: list[object] = [
        para("Stravovací archy", title),
        para(f"za měsíc: {period_title(report.period.month, report.period.year)}", section),
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
    ]
    if report.individuals:
        story.append(table_from_people(report.individuals))
    else:
        story.append(para("Za zvolený měsíc nejsou žádné individuální přihlášky.", small))
    if report.bulk:
        story.append(para("Stravovací archy hromadných strávníků", section))
        story.append(table_from_people(report.bulk))

    def draw_page(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(muted)
        canvas.setFont(regular, 8)
        canvas.drawString(
            left_margin,
            8 * mm,
            f"Stravovací archy {period_title(report.period.month, report.period.year)}",
        )
        canvas.drawRightString(
            page_width - right_margin,
            8 * mm,
            f"Strana {document.page}",
        )
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(target),
        pagesize=landscape(A4),
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=10 * mm,
        bottomMargin=12 * mm,
        title=f"Stravovací archy {period_title(report.period.month, report.period.year)}",
        author="AutoReport",
    )
    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return target


def export_arch_pdf(
    config: AppConfig,
    settings: ClosingSettings,
    on_progress: Any = None,
    podklady: ClosingPodklady | None = None,
) -> Path:
    """Načte data a uloží PDF do složky uzávěrky."""
    report = fetch_arch_report(
        config,
        include_bulk=settings.include_bulk_arch,
        on_progress=on_progress,
        podklady=podklady,
    )
    report_progress(
        on_progress,
        0.08 if podklady is not None else 0.82,
        "Stravovací arch: skládám PDF…",
    )
    output = settings.output_directory / f"StravovaciArch_{settings.period_stamp}.pdf"
    created = create_arch_pdf(config, report, output)
    report_progress(on_progress, 1.0, f"Stravovací arch: uloženo {created.name}")
    return created
