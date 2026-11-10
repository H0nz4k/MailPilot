"""Individual ordered meals matched to JídelnaSQL's monthly collection marks.

Source: Jcode/src/Qneodebr.pas and src/Pomoc.pas (ZnakOdebral = 'O').
An absent mark/row is uncollected, but only an existing order is listed.
Bulk orders have no per-person collection evidence and are not mixed in.
"""
from collections import Counter

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


def collection_pdf_story(config, report, *, table, body_style, section_style, width):
    """Use the shared PDF styles/header; one row is one specific meal order."""
    from reportlab.platypus import Paragraph, Spacer
    from reportlab.lib.units import mm
    from xml.sax.saxutils import escape
    collected = sum(row.collected is True for row in report.diners)
    missing = sum(row.collected is False for row in report.diners)
    story = [Paragraph(f"Odebraná: {collected} · Neodebraná: {missing}", body_style),
             Paragraph("Seznam strávníků a odběrů", section_style)]
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
                story.append(Paragraph(escape(code + " – " + (diners[0].category_name or code)), section_style))
            rows = [(row.diner_number, row.name or "[bez jména]", row.classroom or "",
                     row.category_code, row.meal_type, f"Menu {row.menu}",
                     "Odebraná" if row.collected else "Neodebraná")
                    for row in sorted(diners, key=lambda r: ((r.name or "").casefold(), r.diner_number or 0, r.meal_type, r.menu))]
            story.append(table(("Číslo", "Jméno", "Třída", "Kategorie", "Typ stravy", "Menu", "Odběr"),
                               rows, [width * ratio for ratio in (.09, .25, .08, .12, .17, .1, .19)],
                               centered_columns={0, 2, 3, 5}))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Zahrnuty jsou jednotlivé objednávky stravy. Hromadné přihlášky se zde nevykazují.", body_style))
    return story
