"""Individual ordered meals matched to JídelnaSQL's monthly collection marks.

Source: Jcode/src/Qneodebr.pas and src/Pomoc.pas (ZnakOdebral = 'O').
An absent mark/row is uncollected, but only an existing order is listed.
Bulk orders have no per-person collection evidence and are not mixed in.
"""
from collections import Counter
from dataclasses import replace
from datetime import timedelta

from services.web_meal_types import meal_filter_values
from stravovaci_sestava import (
    CategorySummary, DinerOrder, MenuSummary, NormMenuSummary, ReportData,
    filter_delivery_orders,
)

COLLECTION_QUERY = """
    WITH orders AS (
        SELECT NULLIF(BTRIM(s.jmeno), ''), BTRIM(k.oznaceni),
               NULLIF(BTRIM(k.nazev), ''), BTRIM(p.typsluzby),
               p.{day_column}::integer, NULLIF(UPPER(BTRIM(k.norma)), ''),
               s.evidcislo, NULLIF(BTRIM(s.trida), ''),
               EXISTS (
                   SELECT 1 FROM public.odebral o
                   WHERE o.stravnik = p.stravnik
                     AND o.rok = p.rok AND o.mesic = p.mesic
                     AND LOWER(BTRIM(o.typstravy)) = LOWER(BTRIM(p.typsluzby))
                     AND o.poradiprihl = p.poradiprihl
                     AND SUBSTRING(o.odebral FROM {day} FOR 1) = 'O'
               ) AS collected
        FROM public.prihlas p
        JOIN public.stravnik s ON s.evidcislo = p.stravnik
        JOIN public.kategor k ON BTRIM(k.oznaceni) =
            COALESCE(NULLIF(BTRIM(p.kategorie), ''), BTRIM(s.kategorie))
        WHERE p.rok = %s AND p.mesic = %s
          AND BTRIM(k.oznaceni) = ANY(%s::varchar[])
          AND COALESCE(s.deleted, false) = false
          AND p.{day_column} ~ '^[1-9]$'
          AND (%s::text[] IS NULL OR LOWER(BTRIM(p.typsluzby)) = ANY(%s::text[]))
    )
    SELECT * FROM orders WHERE (%s::boolean IS NULL OR collected = %s::boolean)
    ORDER BY 1, 7, 4, 5
"""


def fetch_collection_report(cursor, config, active_categories, subject_name):
    from psycopg import sql
    meals = list(meal_filter_values(config.meal_type)) or None
    wanted = {"both": None, "collected": True, "uncollected": False}[config.collection_status]
    query = sql.SQL(COLLECTION_QUERY).format(
        day_column=sql.Identifier(f"d{config.report_date.day:02d}"),
        day=sql.Literal(config.report_date.day),
    )
    cursor.execute(query, (config.report_date.year, config.report_date.month,
                          list(active_categories), meals, meals, wanted, wanted))
    diners = tuple(DinerOrder(
        name=row[0], category_code=row[1], category_name=row[2],
        meal_type=row[3], menu=row[4], norm=row[5], meal_name=None,
        diner_number=row[6], classroom=row[7], collected=row[8],
    ) for row in cursor.fetchall())
    counts = Counter(row.category_code for row in diners)
    details = {row.category_code: row for row in diners}
    menus = Counter((row.meal_type, row.menu) for row in diners)
    norms = Counter((row.meal_type, row.norm, row.menu) for row in diners)
    report = ReportData(
        menus=tuple(MenuSummary(meal, menu, count, None) for (meal, menu), count in menus.items()),
        categories=tuple(CategorySummary(code, details[code].category_name,
                                         details[code].norm, counts[code])
                         for code in active_categories if code in details),
        norms=tuple(NormMenuSummary(meal, norm, menu, count)
                    for (meal, norm, menu), count in norms.items()),
        diners=diners, subject_name=subject_name, active_categories=active_categories,
    )
    if config.delivery_types:
        cursor.execute("""
            SELECT DISTINCT BTRIM(s.kategorie), LOWER(BTRIM(s.typstravy)),
                   NULLIF(BTRIM(s.typvydej), ''),
                   EXISTS (SELECT 1 FROM public.typvydej t
                           WHERE BTRIM(t.typvydeje) = BTRIM(s.typvydej))
            FROM public.sazby s
            WHERE BTRIM(s.kategorie) = ANY(%s::varchar[])
              AND (s.platnostod IS NULL OR s.platnostod <= %s)
              AND (s.platnostdo IS NULL OR s.platnostdo >= %s)
        """, (list(active_categories), config.report_date, config.report_date))
        report, _, _ = filter_delivery_orders(report, diners, (), cursor.fetchall(), config.delivery_types)
    return report


def fetch_collection_period(cursor, config, active_categories, subject_name):
    """Collect daily orders in one connection; range is inclusive and bounded."""
    end = config.report_end_date or config.report_date
    days = (end - config.report_date).days
    if days < 0 or days > 365:
        raise ValueError("Období musí být od nejvýše 366 dnů a datum do nesmí předcházet datu od.")
    if config.report_end_date is None:
        return fetch_collection_report(cursor, config, active_categories, subject_name)
    reports = []
    for offset in range(days + 1):
        day = config.report_date + timedelta(days=offset)
        report = fetch_collection_report(cursor, replace(config, report_date=day, report_end_date=None),
                                         active_categories, subject_name)
        reports.append(replace(report, diners=tuple(replace(row, order_date=day) for row in report.diners)))
    diners = tuple(row for report in reports for row in report.diners)
    menus = Counter((row.meal_type, row.menu) for row in diners)
    norms = Counter((row.meal_type, row.norm, row.menu) for row in diners)
    categories = Counter(row.category_code for row in diners)
    details = {row.category_code: row for row in diners}
    return ReportData(
        menus=tuple(MenuSummary(meal, menu, count, None) for (meal, menu), count in menus.items()),
        categories=tuple(CategorySummary(code, details[code].category_name, details[code].norm, categories[code])
                         for code in active_categories if code in details),
        norms=tuple(NormMenuSummary(meal, norm, menu, count) for (meal, norm, menu), count in norms.items()),
        diners=diners, subject_name=subject_name, active_categories=active_categories,
    )


def collection_pdf_story(config, report, *, table, body_style, section_style, width):
    """Use the shared PDF styles/header; one row is one specific meal order."""
    from reportlab.platypus import CondPageBreak, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from xml.sax.saxutils import escape
    collected = sum(row.collected is True for row in report.diners)
    missing = sum(row.collected is False for row in report.diners)
    heading = ParagraphStyle("CollectionHeading", parent=section_style, keepWithNext=False)
    primary = ParagraphStyle("CollectionTotal", parent=section_style, keepWithNext=False,
                             spaceBefore=0, spaceAfter=0, fontSize=max(14, section_style.fontSize),
                             leading=max(18, section_style.leading))
    totals = []
    if config.collection_status in ("both", "collected"):
        totals.append(f"Odebráno: {collected}")
    if config.collection_status in ("both", "uncollected"):
        totals.append(f"Neodebráno: {missing}")
    box = Table([[Paragraph(" · ".join(totals), primary)]], colWidths=[width], hAlign="LEFT")
    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#213B57")),
                             ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EAF2F8")),
                             ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                             ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm)]))
    story = [box, Spacer(1, 2 * mm)]
    if config.show_by_categories:
        status_columns = ([True, False] if config.collection_status == "both"
                          else [config.collection_status == "collected"])
        counts = Counter((row.category_code, row.collected) for row in report.diners)
        labels = {row.category_code: row.category_name or row.category_code for row in report.diners}
        categories = [code for code in report.active_categories if code in labels]
        headers = ("Kategorie",) + tuple("Odebráno" if status else "Neodebráno" for status in status_columns)
        rows = [(f"{code} – {labels[code]}", *(counts[code, status] for status in status_columns))
                for code in categories]
        if rows:
            story.extend([CondPageBreak(35 * mm), Paragraph("Počty podle kategorií", heading),
                          table(headers, rows, [width * .6] + [width * .4 / len(status_columns)] * len(status_columns),
                                centered_columns=set(range(1, len(headers)))), Spacer(1, 2 * mm)])
    if config.report_end_date is not None:
        # One person may have many orders or change categories during the period.
        people = {}
        for row in report.diners:
            key = ("number", row.diner_number) if row.diner_number is not None else ("name", row.name, row.classroom)
            person = people.setdefault(key, {"name": row.name or "[bez jména]", "number": row.diner_number,
                                             "categories": set(), "collected": 0, "uncollected": 0})
            person["categories"].add(row.category_code)
            person["collected" if row.collected else "uncollected"] += 1
        story.extend([CondPageBreak(35 * mm), Paragraph("Součty podle strávníků", heading)])
        status_columns = (["collected", "uncollected"] if config.collection_status == "both"
                          else [config.collection_status])
        headers = ("Číslo", "Jméno", "Kategorie") + tuple(
            "Odebráno" if status == "collected" else "Neodebráno" for status in status_columns)
        rows = [(person["number"], person["name"], ", ".join(sorted(person["categories"])),
                 *(person[status] for status in status_columns))
                for person in sorted(people.values(), key=lambda p: (p["name"].casefold(), str(p["number"] or "")))]
        if rows:
            ratios = [.12, .38, .20] + [.30 / len(status_columns)] * len(status_columns)
            story.append(table(headers, rows, [width * ratio for ratio in ratios],
                               centered_columns={0, *range(3, len(headers))}))
        else:
            story.append(Paragraph("Pro zvolené období a filtry nebyly nalezeny žádné objednávky.", body_style))
        story.extend([Spacer(1, 2 * mm), Paragraph("Zahrnuty jsou jednotlivé objednávky stravy. Hromadné přihlášky se zde nevykazují.", body_style)])
        return story
    story.extend([CondPageBreak(35 * mm), Paragraph("Seznam strávníků a odběrů", heading)])
    if not report.diners:
        story.append(Paragraph("Pro zvolený den a filtry nebyly nalezeny žádné objednávky odpovídající výběru.", body_style))
    else:
        groups = ([(code, [row for row in report.diners if row.category_code == code])
                   for code in report.active_categories] if config.category_separation
                  else [(None, report.diners)])
        for code, diners in groups:
            if not diners:
                continue
            if code is not None:
                story.append(CondPageBreak(25 * mm))
                story.append(Paragraph(escape(code + " – " + (diners[0].category_name or code)), heading))
            rows = [(row.diner_number, row.name or "[bez jména]", row.classroom or "",
                     row.category_code, row.meal_type, f"Menu {row.menu}",
                     "Odebraná" if row.collected else "Neodebraná")
                    for row in sorted(diners, key=lambda r: ((r.name or "").casefold(), r.diner_number or 0, r.meal_type, r.menu))]
            headers = ("Číslo", "Jméno", "Třída", "Kategorie", "Typ stravy", "Menu", "Odběr")
            ratios = (.09, .25, .08, .12, .17, .1, .19)
            if config.report_end_date is not None:
                ordered = sorted(diners, key=lambda r: ((r.name or "").casefold(), r.diner_number or 0, r.meal_type, r.menu))
                rows = [(d.order_date.strftime("%d.%m.%Y") if d.order_date else "", *row)
                        for d, row in zip(ordered, rows)]
                headers = ("Datum", *headers)
                ratios = (.13, .08, .20, .08, .12, .14, .09, .16)
            story.append(table(headers, rows, [width * ratio for ratio in ratios],
                               centered_columns={0, 2, 3, 5} if config.report_end_date is None else {0, 1, 3, 4, 6}))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Zahrnuty jsou jednotlivé objednávky stravy. Hromadné přihlášky se zde nevykazují.", body_style))
    return story
