#!/usr/bin/env python3
"""Souhrn objednaných menu pro zvolené datum a kategorie strávníků."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence
from xml.sax.saxutils import escape

from credential_store import CredentialStoreError, get_password
from runtime_paths import application_directory, bundled_path


DATE_FORMAT = "%d.%m.%Y"
DEFAULT_NORMS = ("A", "B", "C", "D")


SUMMARY_QUERY = """
        WITH objednavky AS (
            SELECT
                p.typsluzby,
                CASE
                    WHEN p.{day_column} ~ '^[1-9]$'
                    THEN p.{day_column}::integer
                END AS menu,
                COUNT(*)::integer AS pocet
            FROM public.prihlas AS p
            JOIN public.stravnik AS s
              ON s.evidcislo = p.stravnik
            JOIN public.kategor AS k
              ON BTRIM(k.oznaceni) = BTRIM(s.kategorie)
            WHERE p.rok = %s
              AND p.mesic = %s
              AND BTRIM(s.kategorie) = ANY(%s::varchar[])
              AND COALESCE(s.deleted, false) = false
              AND p.{day_column} ~ '^[1-9]$'
              AND (%s::text IS NULL OR LOWER(BTRIM(p.typsluzby)) = %s::text)
            GROUP BY p.typsluzby, p.{day_column}
        ),
        jidla AS (
            SELECT
                j.typstravy,
                t.oznaceni::integer AS menu,
                string_agg(
                    NULLIF(BTRIM(j.nazev), ''),
                    ', ' ORDER BY m.caststravy, m.id
                ) AS nazev
            FROM public.jidelnicek AS j
            JOIN public.menustravy AS m
              ON m.id = j.idmenustravy
            JOIN public.typstrj AS t
              ON t.id = m.idtypstrj
            WHERE j.datum = %s
              -- V DB se vyskytuje např. "česky", zatímco starší configy
              -- používaly "Česky". Velikost písmen nesmí zrušit celý jídelníček.
              AND LOWER(BTRIM(j.jazyk)) = LOWER(BTRIM(%s))
              AND j.cislojidelnicku = %s
              -- Přihláška obsahuje označení menu 1–9. idtypstrj je interní
              -- ID skupiny (např. 1 = Polévka, 2 = Menu 1), nikoli číslo menu.
              AND BTRIM(t.oznaceni) ~ '^[1-9]$'
            GROUP BY j.typstravy, t.oznaceni
        )
        SELECT
            o.typsluzby AS typ_stravy,
            o.menu,
            o.pocet,
            NULLIF(j.nazev, '') AS nazev
        FROM objednavky AS o
        LEFT JOIN jidla AS j
          ON LOWER(BTRIM(o.typsluzby)) = LOWER(BTRIM(j.typstravy))
         AND o.menu = j.menu
        ORDER BY typ_stravy, menu
"""


CATEGORY_SUMMARY_QUERY = """
        WITH vybrane_kategorie AS (
            SELECT BTRIM(u.oznaceni) AS oznaceni, u.poradi
            FROM unnest(%s::varchar[]) WITH ORDINALITY
                 AS u(oznaceni, poradi)
        )
        SELECT
            BTRIM(k.oznaceni) AS oznaceni,
            NULLIF(BTRIM(k.nazev), '') AS nazev,
            NULLIF(UPPER(BTRIM(k.norma)), '') AS norma,
            COUNT(p.id)::integer AS pocet_prihlasek
        FROM vybrane_kategorie AS v
        JOIN public.kategor AS k
          ON BTRIM(k.oznaceni) = v.oznaceni
        LEFT JOIN public.stravnik AS s
          ON BTRIM(s.kategorie) = BTRIM(k.oznaceni)
         AND COALESCE(s.deleted, false) = false
        LEFT JOIN public.prihlas AS p
          ON p.stravnik = s.evidcislo
         AND p.rok = %s
         AND p.mesic = %s
         AND p.{day_column} ~ '^[1-9]$'
         AND (%s::text IS NULL OR LOWER(BTRIM(p.typsluzby)) = %s::text)
        GROUP BY v.poradi, k.oznaceni, k.nazev, k.norma
        ORDER BY v.poradi
"""


NORM_MENU_QUERY = """
        SELECT
            p.typsluzby AS typ_stravy,
            NULLIF(UPPER(BTRIM(k.norma)), '') AS norma,
            p.{day_column}::integer AS menu,
            COUNT(*)::integer AS pocet
        FROM public.prihlas AS p
        JOIN public.stravnik AS s
          ON s.evidcislo = p.stravnik
        JOIN public.kategor AS k
          ON BTRIM(k.oznaceni) = BTRIM(s.kategorie)
        WHERE p.rok = %s
          AND p.mesic = %s
          AND BTRIM(s.kategorie) = ANY(%s::varchar[])
          AND COALESCE(s.deleted, false) = false
          AND p.{day_column} ~ '^[1-9]$'
          AND (%s::text IS NULL OR LOWER(BTRIM(p.typsluzby)) = %s::text)
        GROUP BY p.typsluzby, k.norma, p.{day_column}
        ORDER BY typ_stravy, norma NULLS LAST, menu
"""


SUBJECT_NAME_QUERY = """
        SELECT NULLIF(BTRIM(hodnota), '') AS nazev_subjektu
        FROM public.parametry
        WHERE LOWER(BTRIM(sekce)) = LOWER('BACKUP')
          AND LOWER(BTRIM(parametr)) = LOWER('NameSubject')
          AND NULLIF(BTRIM(hodnota), '') IS NOT NULL
        LIMIT 1
"""

JIDELNA_PERIOD_QUERY = """
        SELECT LOWER(BTRIM(parametr)) AS klic, NULLIF(BTRIM(hodnota), '') AS hodnota
        FROM public.parametry
        WHERE LOWER(BTRIM(sekce)) = LOWER('BACKUP')
          AND LOWER(BTRIM(parametr)) IN (LOWER('TentoMesic'), LOWER('TentoRok'))
"""


DINER_LIST_QUERY = """
        WITH jidla AS (
            SELECT
                j.typstravy,
                t.oznaceni::integer AS menu,
                string_agg(
                    NULLIF(BTRIM(j.nazev), ''),
                    ', ' ORDER BY m.caststravy, m.id
                ) AS nazev
            FROM public.jidelnicek AS j
            JOIN public.menustravy AS m
              ON m.id = j.idmenustravy
            JOIN public.typstrj AS t
              ON t.id = m.idtypstrj
            WHERE j.datum = %s
              AND LOWER(BTRIM(j.jazyk)) = LOWER(BTRIM(%s))
              AND j.cislojidelnicku = %s
              AND BTRIM(t.oznaceni) ~ '^[1-9]$'
            GROUP BY j.typstravy, t.oznaceni
        )
        SELECT
            NULLIF(BTRIM(s.jmeno), '') AS jmeno,
            BTRIM(k.oznaceni) AS kategorie_oznaceni,
            NULLIF(BTRIM(k.nazev), '') AS kategorie_nazev,
            p.typsluzby AS typ_stravy,
            p.{day_column}::integer AS menu,
            NULLIF(UPPER(BTRIM(k.norma)), '') AS norma,
            NULLIF(j.nazev, '') AS nazev_jidla
        FROM public.prihlas AS p
        JOIN public.stravnik AS s
          ON s.evidcislo = p.stravnik
        JOIN public.kategor AS k
          ON BTRIM(k.oznaceni) = BTRIM(s.kategorie)
        LEFT JOIN jidla AS j
          ON LOWER(BTRIM(p.typsluzby)) = LOWER(BTRIM(j.typstravy))
         AND p.{day_column}::integer = j.menu
        WHERE p.rok = %s
          AND p.mesic = %s
          AND BTRIM(s.kategorie) = ANY(%s::varchar[])
          AND COALESCE(s.deleted, false) = false
          AND p.{day_column} ~ '^[1-9]$'
          AND (%s::text IS NULL OR LOWER(BTRIM(p.typsluzby)) = %s::text)
        ORDER BY
            LOWER(BTRIM(s.jmeno)) NULLS LAST,
            BTRIM(s.jmeno) NULLS LAST,
            LOWER(BTRIM(p.typsluzby)),
            p.{day_column}::integer,
            p.id
"""


# Hromadná přihláška má menu ve variantě a skutečný počet porcí v dNN.
# Nelze na ni použít COUNT(*) ani test menu 1–9 nad denním sloupcem.
BULK_DAILY_QUERY = """
        WITH jidla AS (
            SELECT j.typstravy, BTRIM(t.oznaceni) AS menu,
                   string_agg(NULLIF(BTRIM(j.nazev), ''), ', '
                              ORDER BY m.caststravy, m.id) AS nazev
            FROM public.jidelnicek AS j
            JOIN public.menustravy AS m ON m.id = j.idmenustravy
            JOIN public.typstrj AS t ON t.id = m.idtypstrj
            WHERE j.datum = %s
              AND LOWER(BTRIM(j.jazyk)) = LOWER(BTRIM(%s))
              AND j.cislojidelnicku = %s
              AND BTRIM(t.oznaceni) ~ '^[1-9]$'
            GROUP BY j.typstravy, BTRIM(t.oznaceni)
        )
        SELECT CASE WHEN %s::boolean THEN NULLIF(BTRIM(s.jmeno), '') END,
               BTRIM(k.oznaceni), NULLIF(BTRIM(k.nazev), ''),
               BTRIM(p.typsluzby), BTRIM(p.varianta),
               NULLIF(UPPER(BTRIM(k.norma)), ''), NULLIF(j.nazev, ''),
               p.{day_column}::integer
        FROM public.prihlasn AS p
        JOIN public.stravnik AS s ON s.evidcislo = p.stravnik
        JOIN public.kategor AS k
          ON BTRIM(k.oznaceni) = COALESCE(NULLIF(BTRIM(p.kategorie), ''),
                                        BTRIM(s.kategorie))
        LEFT JOIN jidla AS j
          ON LOWER(BTRIM(p.typsluzby)) = LOWER(BTRIM(j.typstravy))
         AND BTRIM(p.varianta) = j.menu
        WHERE p.rok = %s AND p.mesic = %s
          AND BTRIM(k.oznaceni) = ANY(%s::varchar[])
          AND COALESCE(s.deleted, false) = false
          AND p.{day_column} > 0
          AND (%s::text IS NULL OR LOWER(BTRIM(p.typsluzby)) = %s::text)
        ORDER BY p.id
"""


class ConfigError(ValueError):
    """Chyba uživatelské konfigurace."""


@dataclass(frozen=True)
class AppConfig:
    database: dict[str, Any]
    report_date: date
    categories: tuple[str, ...]
    language: str
    menu_list_number: int
    category_separation: bool = False
    show_by_categories: bool = True
    show_by_norms: bool = True
    pdf_output: Path = Path("vystup/MailPilot.pdf")
    pdf_orientation: str = "na_sirku"
    pdf_data_font_size: float = 7.4
    pdf_label_font_size: float = 7.4
    pdf_bold: bool = False
    meal_type: str | None = None  # None = všechny
    show_diner_list: bool = True


@dataclass(frozen=True)
class MenuSummary:
    meal_type: str
    menu: int
    portions: int
    meal_name: str | None


@dataclass(frozen=True)
class CategorySummary:
    code: str
    name: str | None
    norm: str | None
    applications: int


@dataclass(frozen=True)
class NormMenuSummary:
    meal_type: str
    norm: str | None
    menu: int
    portions: int


@dataclass(frozen=True)
class DinerOrder:
    name: str | None
    category_code: str
    category_name: str | None
    meal_type: str
    menu: int
    norm: str | None
    meal_name: str | None
    portions: int = 1

    @property
    def application_label(self) -> str:
        return f"Menu {self.menu}" + (f" × {self.portions}" if self.portions != 1 else "")


@dataclass(frozen=True)
class ReportData:
    menus: tuple[MenuSummary, ...]
    categories: tuple[CategorySummary, ...]
    norms: tuple[NormMenuSummary, ...]
    diners: tuple[DinerOrder, ...]
    subject_name: str | None
    active_categories: tuple[str, ...] = ()


def existing_categories(
    requested: Sequence[str], database_codes: Sequence[object]
) -> tuple[str, ...]:
    """Vrátí v původním pořadí jen kategorie, které aktuálně existují v DB."""
    available = {
        str(code).strip()
        for code in database_codes
        if code is not None and str(code).strip()
    }
    return tuple(code for code in requested if code.strip() in available)


def parse_jidelna_period(rows: Sequence[Sequence[Any]]) -> tuple[int, int]:
    """Převede TentoMesic / TentoRok z public.parametry na (rok, měsíc)."""
    values: dict[str, str] = {}
    for row in rows:
        if not row:
            continue
        key = str(row[0] or "").strip().casefold()
        value = row[1]
        if not key or value is None:
            continue
        text = str(value).strip()
        if text:
            values[key] = text
    month_raw = values.get("tentomesic")
    year_raw = values.get("tentorok")
    if not month_raw or not year_raw:
        raise ConfigError(
            "V public.parametry (BACKUP) chybí TentoMesic nebo TentoRok."
        )
    try:
        year = int(year_raw)
        month = int(month_raw)
    except ValueError as exc:
        raise ConfigError(
            "TentoMesic a TentoRok v public.parametry musí být čísla."
        ) from exc
    if year < 2000 or year > 2100:
        raise ConfigError("TentoRok v public.parametry musí být v rozsahu 2000–2100.")
    if not 1 <= month <= 12:
        raise ConfigError("TentoMesic v public.parametry musí být v rozsahu 1–12.")
    return year, month


def read_jidelna_period(cursor: Any) -> tuple[int, int]:
    """Načte aktuální měsíc a rok Jídelny z public.parametry."""
    cursor.execute(JIDELNA_PERIOD_QUERY)
    return parse_jidelna_period(cursor.fetchall())


def peek_jidelna_period(cursor: Any) -> tuple[int, int] | None:
    """Stejné údaje pro UI; chybějící hodnoty nehodí chybu."""
    cursor.execute(JIDELNA_PERIOD_QUERY)
    try:
        return parse_jidelna_period(cursor.fetchall())
    except ConfigError:
        return None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Vypíše názvy jídel a počty objednaných porcí pro vybrané "
            "kategorie strávníků."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=application_directory() / "config.json",
        help="cesta ke konfiguraci (výchozí: config.json vedle skriptu)",
    )
    parser.add_argument(
        "--date",
        dest="date_override",
        metavar="DD.MM.RRRR",
        help="volitelně přepíše datum z configu",
    )
    parser.add_argument(
        "--pdf",
        dest="pdf_override",
        type=Path,
        metavar="SOUBOR.PDF",
        help="volitelně přepíše cestu PDF z configu",
    )
    parser.add_argument(
        "--no-console",
        action="store_true",
        help="nevypisuje dlouhou textovou sestavu, pouze vytvoří PDF",
    )
    return parser.parse_args(argv)


def parse_report_date(value: object) -> date:
    if value is None or (isinstance(value, str) and not value.strip()):
        return date.today()
    if not isinstance(value, str):
        raise ConfigError("'datum' musí být text ve formátu DD.MM.RRRR nebo null.")
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT).date()
    except ValueError as exc:
        raise ConfigError(
            f"Neplatné datum {value!r}; očekávám formát DD.MM.RRRR."
        ) from exc


def parse_pdf_font_size(raw: dict[str, Any], key: str, default: float) -> float:
    """Načte bezpečnou velikost písma v typografických bodech."""
    value = raw.get(key, default)
    if isinstance(value, bool):
        raise ConfigError(f"'{key}' musí být číslo v rozsahu 5 až 18.")
    try:
        size = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"'{key}' musí být číslo v rozsahu 5 až 18.") from exc
    if not 5 <= size <= 18:
        raise ConfigError(f"'{key}' musí být v rozsahu 5 až 18 bodů.")
    return size


def load_config(
    path: Path,
    date_override: str | None = None,
    pdf_override: Path | None = None,
) -> AppConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Konfigurační soubor neexistuje: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Neplatný JSON v {path} (řádek {exc.lineno}, sloupec {exc.colno})."
        ) from exc

    if not isinstance(raw, dict):
        raise ConfigError("Kořen configu musí být JSON objekt.")

    database = raw.get("databaze")
    if not isinstance(database, dict):
        raise ConfigError("V configu chybí objekt 'databaze'.")

    required_db = ("host", "port", "dbname", "user")
    missing_db = [key for key in required_db if database.get(key) in (None, "")]
    if missing_db:
        raise ConfigError(
            "V objektu 'databaze' chybí: " + ", ".join(missing_db)
        )

    if "password" in database:
        raise ConfigError(
            "Heslo nesmí být uloženo v config.json. Spusťte UI a uložte "
            "je do systémového úložiště přihlašovacích údajů."
        )

    try:
        port = int(database["port"])
    except (TypeError, ValueError) as exc:
        raise ConfigError("'databaze.port' musí být celé číslo.") from exc
    if not 1 <= port <= 65535:
        raise ConfigError("'databaze.port' musí být v rozsahu 1–65535.")

    from pocty_nastaveni import parse_client_categories

    normalized_categories = parse_client_categories(raw)
    meal_type = raw.get("typ_stravy_denne")
    if meal_type in (None, ""):
        meal_type = None
    elif not isinstance(meal_type, str):
        raise ConfigError("'typ_stravy_denne' musí být text nebo null.")
    else:
        meal_type = meal_type.strip().casefold() or None

    show_diner_list = raw.get("seznam_stravniku", True)
    if not isinstance(show_diner_list, bool):
        raise ConfigError("'seznam_stravniku' musí být true nebo false.")

    language = raw.get("jazyk_jidelnicku", "česky")
    if not isinstance(language, str) or not language.strip():
        raise ConfigError("'jazyk_jidelnicku' musí být neprázdný text.")

    menu_list_number = raw.get("cislo_jidelnicku", 1)
    if isinstance(menu_list_number, bool):
        raise ConfigError("'cislo_jidelnicku' musí být celé kladné číslo.")
    try:
        menu_list_number = int(menu_list_number)
    except (TypeError, ValueError) as exc:
        raise ConfigError("'cislo_jidelnicku' musí být celé kladné číslo.") from exc
    if menu_list_number < 1:
        raise ConfigError("'cislo_jidelnicku' musí být celé kladné číslo.")

    category_separation = raw.get("kategor_separ", False)
    if not isinstance(category_separation, bool):
        raise ConfigError("'kategor_separ' musí být JSON hodnota true nebo false.")

    show_by_categories = raw.get("dle_kategorii", True)
    if not isinstance(show_by_categories, bool):
        raise ConfigError("'dle_kategorii' musí být JSON hodnota true nebo false.")

    show_by_norms = raw.get("dle_norem", True)
    if not isinstance(show_by_norms, bool):
        raise ConfigError("'dle_norem' musí být JSON hodnota true nebo false.")

    pdf_orientation = raw.get("pdf_orientace", "na_sirku")
    if not isinstance(pdf_orientation, str):
        raise ConfigError(
            "'pdf_orientace' musí být 'na_sirku' nebo 'na_vysku'."
        )
    pdf_orientation = pdf_orientation.strip().lower()
    orientation_aliases = {
        "na_sirku": "na_sirku",
        "na šířku": "na_sirku",
        "na sirku": "na_sirku",
        "landscape": "na_sirku",
        "na_vysku": "na_vysku",
        "na výšku": "na_vysku",
        "na vysku": "na_vysku",
        "portrait": "na_vysku",
    }
    if pdf_orientation not in orientation_aliases:
        raise ConfigError(
            "'pdf_orientace' musí být 'na_sirku' nebo 'na_vysku'."
        )
    pdf_orientation = orientation_aliases[pdf_orientation]

    pdf_data_font_size = parse_pdf_font_size(raw, "pdf_velikost_dat", 7.4)
    pdf_label_font_size = parse_pdf_font_size(raw, "pdf_velikost_popisku", 7.4)

    pdf_bold = raw.get("pdf_tucne", False)
    if not isinstance(pdf_bold, bool):
        raise ConfigError("'pdf_tucne' musí být JSON hodnota true nebo false.")

    db_config = dict(database)
    db_config["port"] = port
    db_config.setdefault("connect_timeout", 10)
    db_config.setdefault("sslmode", "prefer")
    try:
        database_password = get_password(db_config)
    except CredentialStoreError as exc:
        raise ConfigError(str(exc)) from exc
    if not database_password:
        raise ConfigError(
            "Pro toto DB připojení není uložené heslo. Spusťte UI, "
            "vyplňte heslo a použijte tlačítko TEST."
        )
    db_config["password"] = database_password

    report_date = parse_report_date(
        date_override if date_override is not None else raw.get("datum")
    )

    configured_pdf = raw.get(
        "pdf_vystup", "vystup/MailPilot_{datum}.pdf"
    )
    if not isinstance(configured_pdf, str) or not configured_pdf.strip():
        raise ConfigError("'pdf_vystup' musí být neprázdná cesta k PDF souboru.")
    try:
        configured_pdf = configured_pdf.strip().format(
            datum=report_date.isoformat(),
            datum_cz=report_date.strftime(DATE_FORMAT),
        )
    except (KeyError, ValueError) as exc:
        raise ConfigError(
            "'pdf_vystup' smí používat pouze zástupné hodnoty "
            "{datum} a {datum_cz}."
        ) from exc

    pdf_output = pdf_override if pdf_override is not None else Path(configured_pdf)
    if not pdf_output.is_absolute():
        pdf_output = path.resolve().parent / pdf_output
    if pdf_output.suffix.lower() != ".pdf":
        raise ConfigError("Výstupní soubor 'pdf_vystup' musí mít příponu .pdf.")

    return AppConfig(
        database=db_config,
        report_date=report_date,
        categories=normalized_categories,
        language=language.strip(),
        menu_list_number=menu_list_number,
        category_separation=category_separation,
        show_by_categories=show_by_categories,
        show_by_norms=show_by_norms,
        pdf_output=pdf_output,
        pdf_orientation=pdf_orientation,
        pdf_data_font_size=pdf_data_font_size,
        pdf_label_font_size=pdf_label_font_size,
        pdf_bold=pdf_bold,
        meal_type=meal_type,
        show_diner_list=show_diner_list,
    )


def _include_bulk_orders(
    report: ReportData, bulk_rows: Sequence[Sequence[Any]], *, show_diner_list: bool
) -> ReportData:
    """Přičte skutečné porce do všech souhrnů, skupinu nevydává za jednu porci."""
    menu_totals: dict[tuple[str, int], MenuSummary] = {}
    norm_totals: dict[tuple[str, str | None, int], NormMenuSummary] = {}
    categories = {row.code: row for row in report.categories}
    diners = list(report.diners)

    def add_menu(row: MenuSummary) -> None:
        key = (row.meal_type.strip().casefold(), row.menu)
        previous = menu_totals.get(key)
        menu_totals[key] = row if previous is None else replace(
            previous, portions=previous.portions + row.portions,
            meal_name=previous.meal_name or row.meal_name,
        )

    def add_norm(row: NormMenuSummary) -> None:
        key = (row.meal_type.strip().casefold(), row.norm, row.menu)
        previous = norm_totals.get(key)
        norm_totals[key] = row if previous is None else replace(
            previous, portions=previous.portions + row.portions,
        )

    for row in report.menus:
        add_menu(row)
    for row in report.norms:
        add_norm(row)
    for name, code, category_name, meal_type, variant, norm, meal_name, portions in bulk_rows:
        variant = str(variant or "").strip()
        if len(variant) != 1 or variant not in "123456789":
            raise ConfigError(
                "Hromadná přihláška s kladným počtem porcí nemá platné menu "
                "1–9 v poli varianta. Opravte přihlášku v JídelnaSQL."
            )
        order = DinerOrder(name, code, category_name, meal_type, int(variant),
                           norm, meal_name, int(portions))
        add_menu(MenuSummary(meal_type, order.menu, order.portions, meal_name))
        add_norm(NormMenuSummary(meal_type, norm, order.menu, order.portions))
        category = categories[code]
        categories[code] = replace(
            category, applications=category.applications + order.portions,
        )
        if show_diner_list:
            diners.append(order)
    return replace(
        report,
        menus=tuple(sorted(menu_totals.values(), key=lambda r: (r.meal_type, r.menu))),
        categories=tuple(categories.values()),
        norms=tuple(sorted(norm_totals.values(),
                           key=lambda r: (r.meal_type, r.norm or "", r.menu))),
        diners=tuple(diners),
    )


def fetch_report(config: AppConfig) -> ReportData:
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:
        raise RuntimeError(
            "Chybí balíček psycopg. Nainstalujte závislosti příkazem "
            "'python -m pip install -r requirements.txt'."
        ) from exc

    day_column = sql.Identifier(f"d{config.report_date.day:02d}")
    summary_query = sql.SQL(SUMMARY_QUERY).format(day_column=day_column)
    category_query = sql.SQL(CATEGORY_SUMMARY_QUERY).format(day_column=day_column)
    norm_query = sql.SQL(NORM_MENU_QUERY).format(day_column=day_column)
    diner_query = sql.SQL(DINER_LIST_QUERY).format(day_column=day_column)
    bulk_query = sql.SQL(BULK_DAILY_QUERY).format(day_column=day_column)

    with psycopg.connect(**config.database) as connection:
        with connection.cursor() as cursor:
            if config.categories:
                cursor.execute(
                    """
                    SELECT BTRIM(oznaceni)
                    FROM public.kategor
                    WHERE BTRIM(oznaceni) = ANY(%s::varchar[])
                    """,
                    (list(config.categories),),
                )
                active_categories = existing_categories(
                    config.categories, [row[0] for row in cursor.fetchall()]
                )
            else:
                # Default ALL: actual category codes from DB, never stale config.
                cursor.execute(
                    "SELECT DISTINCT BTRIM(oznaceni) FROM public.kategor "
                    "WHERE NULLIF(BTRIM(oznaceni), '') IS NOT NULL "
                    "ORDER BY BTRIM(oznaceni)"
                )
                active_categories = tuple(
                    str(row[0]).strip() for row in cursor.fetchall()
                    if row[0] is not None and str(row[0]).strip()
                )
            if not active_categories:
                raise ConfigError(
                    "V public.kategor nebyly nalezeny žádné použitelné kategorie. "
                    "Ověřte připojení a nastavení v Administraci."
                )

            cursor.execute(SUBJECT_NAME_QUERY)
            subject_row = cursor.fetchone()
            subject_name = subject_row[0] if subject_row else None

            cursor.execute(
                summary_query,
                (
                    config.report_date.year,
                    config.report_date.month,
                    list(active_categories),
                    config.meal_type,
                    config.meal_type,
                    config.report_date,
                    config.language,
                    config.menu_list_number,
                ),
            )
            menus = tuple(
                MenuSummary(
                    meal_type=row[0],
                    menu=row[1],
                    portions=row[2],
                    meal_name=row[3],
                )
                for row in cursor.fetchall()
            )

            cursor.execute(
                category_query,
                (
                    list(active_categories),
                    config.report_date.year,
                    config.report_date.month,
                    config.meal_type,
                    config.meal_type,
                ),
            )
            categories = tuple(
                CategorySummary(
                    code=row[0],
                    name=row[1],
                    norm=row[2],
                    applications=row[3],
                )
                for row in cursor.fetchall()
            )

            cursor.execute(
                norm_query,
                (
                    config.report_date.year,
                    config.report_date.month,
                    list(active_categories),
                    config.meal_type,
                    config.meal_type,
                ),
            )
            norms = tuple(
                NormMenuSummary(
                    meal_type=row[0],
                    norm=row[1],
                    menu=row[2],
                    portions=row[3],
                )
                for row in cursor.fetchall()
            )

            # Summary-only PDF does not need to query/hold diners' names.
            diners: tuple[DinerOrder, ...] = ()
            if config.show_diner_list:
                cursor.execute(
                    diner_query,
                    (
                        config.report_date,
                        config.language,
                        config.menu_list_number,
                        config.report_date.year,
                        config.report_date.month,
                        list(active_categories),
                        config.meal_type,
                        config.meal_type,
                    ),
                )
                diners = tuple(
                    DinerOrder(
                        name=row[0],
                        category_code=row[1],
                        category_name=row[2],
                        meal_type=row[3],
                        menu=row[4],
                        norm=row[5],
                        meal_name=row[6],
                    )
                    for row in cursor.fetchall()
                )

            report = ReportData(
                menus=menus,
                categories=categories,
                norms=norms,
                diners=diners,
                subject_name=subject_name,
                active_categories=active_categories,
            )
            cursor.execute(
                bulk_query,
                (
                    config.report_date, config.language, config.menu_list_number,
                    config.show_diner_list,
                    config.report_date.year, config.report_date.month,
                    list(active_categories), config.meal_type, config.meal_type,
                ),
            )
            return _include_bulk_orders(
                report, cursor.fetchall(), show_diner_list=config.show_diner_list,
            )


def available_meal_types(database: dict[str, Any], report_date: date) -> tuple[str, ...]:
    """Typy služby evidované v JídelnaSQL pro daný rok.

    Výběr nesmí zmizet jen proto, že vybraný den/kalendářní měsíc
    nemá objednávky jiného typu. Nevrací vymyšlené typy stravy.
    """
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Chybí balíček psycopg.") from exc

    query = """
        SELECT DISTINCT typ
        FROM (
            SELECT BTRIM(p.typsluzby) AS typ
            FROM public.prihlas AS p
            WHERE p.rok = %s
            UNION
            SELECT BTRIM(p.typsluzby) AS typ
            FROM public.prihlasn AS p
            WHERE p.rok = %s
            UNION
            SELECT BTRIM(v.typsluzby) AS typ
            FROM public.varnedny AS v
            WHERE v.rok = %s
            UNION
            SELECT BTRIM(j.typstravy) AS typ
            FROM public.jidelnicek AS j
            WHERE j.datum >= %s AND j.datum < %s
        ) AS typy
        WHERE NULLIF(typ, '') IS NOT NULL
        ORDER BY typ
    """
    year_begin = date(report_date.year, 1, 1)
    year_end = date(report_date.year + 1, 1, 1)
    with psycopg.connect(**database) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (
                report_date.year,
                report_date.year,
                report_date.year,
                year_begin, year_end,
            ))
            return tuple(row[0] for row in cursor.fetchall())


def fetch_summary(config: AppConfig) -> list[MenuSummary]:
    """Zpětně kompatibilní pomocná funkce vracející původní souhrn menu."""
    return list(fetch_report(config).menus)


def format_table(headers: Sequence[str], values: Sequence[Sequence[str]]) -> str:
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in values))
        for index in range(len(headers))
    ]

    def format_row(row: Sequence[str]) -> str:
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    separator = "-+-".join("-" * width for width in widths)
    return "\n".join(
        [format_row(headers), separator, *(format_row(row) for row in values)]
    )


def render_norm_tables(rows: Sequence[NormMenuSummary]) -> list[str]:
    sections: list[str] = []
    meal_types = sorted({row.meal_type for row in rows}, key=str.casefold)

    for meal_type in meal_types:
        meal_rows = [row for row in rows if row.meal_type == meal_type]
        menus = sorted({row.menu for row in meal_rows})
        extra_norms = sorted(
            {
                row.norm or "[bez normy]"
                for row in meal_rows
                if (row.norm or "[bez normy]") not in DEFAULT_NORMS
            },
            key=str.casefold,
        )
        norms = [*DEFAULT_NORMS, *extra_norms]
        counts = {
            (row.norm or "[bez normy]", row.menu): row.portions
            for row in meal_rows
        }
        values: list[tuple[str, ...]] = []
        for norm in norms:
            menu_counts = [counts.get((norm, menu), 0) for menu in menus]
            values.append(
                (
                    norm,
                    *(str(count) for count in menu_counts),
                    str(sum(menu_counts)),
                )
            )

        headers = ("Norma", *(f"Menu {menu}" for menu in menus), "Celkem")
        sections.append(
            f"Typ stravy: {meal_type}\n" + format_table(headers, values)
        )

    return sections


def render_table(
    config: AppConfig,
    rows: Sequence[MenuSummary],
    category_rows: Sequence[CategorySummary] = (),
    norm_rows: Sequence[NormMenuSummary] = (),
    diner_rows: Sequence[DinerOrder] = (),
    subject_name: str | None = None,
    active_categories: Sequence[str] = (),
) -> str:
    category_codes = tuple(active_categories) or config.categories
    title = f"Objednaná strava pro {config.report_date.strftime(DATE_FORMAT)}"
    categories = "Kategorie: " + ", ".join(category_codes)
    heading = f"{title}\n{categories}"
    if subject_name:
        heading = f"{subject_name}\n{heading}"
    sections = [heading]

    if config.show_by_categories and category_rows:
        category_values = [
            (
                row.code,
                row.name or "[bez názvu]",
                row.norm or "[bez normy]",
                str(row.applications),
            )
            for row in category_rows
        ]
        sections.append(
            "Přihlášky podle kategorií\n"
            + format_table(
                ("Označení", "Název kategorie", "Norma", "Přihlášek"),
                category_values,
            )
            + f"\nCelkem přihlášek: "
            + str(sum(row.applications for row in category_rows))
        )

    if rows:
        menu_values = [
            (
                row.meal_type,
                str(row.menu),
                str(row.portions),
                row.meal_name or "[název v jídelníčku nenalezen]",
            )
            for row in rows
        ]
        sections.append(
            "Objednaná menu\n"
            + format_table(
                ("Typ stravy", "Menu", "Počet", "Název jídla"),
                menu_values,
            )
            + f"\nCelkem porcí: {sum(row.portions for row in rows)}"
        )
    else:
        sections.append("Objednaná menu\nNenalezeny žádné objednávky.")

    if config.show_by_norms and norm_rows:
        sections.append(
            "Objednaná menu podle norem\n"
            + "\n\n".join(render_norm_tables(norm_rows))
        )

    if config.show_diner_list and diner_rows:
        def diner_sort_key(row: DinerOrder) -> tuple[str, str, int]:
            return (
                (row.name or "").casefold(),
                row.meal_type.casefold(),
                row.menu,
            )

        def diner_values(rows: Sequence[DinerOrder]) -> list[tuple[str, ...]]:
            return [
                (
                    row.name or "[bez jména]",
                    row.category_name or row.category_code,
                    row.application_label,
                    row.norm or "[bez normy]",
                    row.meal_name or "[název v jídelníčku nenalezen]",
                )
                for row in rows
            ]

        diner_headers = (
            "Jméno",
            "Kategorie",
            "Přihláška",
            "Norma",
            "Objednané jídlo",
        )

        if config.category_separation:
            category_sections: list[str] = []
            for category_code in category_codes:
                category_diners = sorted(
                    (
                        row
                        for row in diner_rows
                        if row.category_code == category_code
                    ),
                    key=diner_sort_key,
                )
                if not category_diners:
                    continue

                category_name = next(
                    (
                        row.category_name
                        for row in category_diners
                        if row.category_name
                    ),
                    None,
                )
                heading = category_name or category_code
                category_sections.append(
                    f"{heading}\n{'-' * len(heading)}\n"
                    + format_table(diner_headers, diner_values(category_diners))
                )

            sections.append(
                "Seznam strávníků podle kategorií\n\n"
                + "\n\n".join(category_sections)
                + f"\nCelkem strávníků / objednávek: {len(diner_rows)}"
            )
        else:
            sorted_diners = sorted(diner_rows, key=diner_sort_key)
            sections.append(
                "Seznam strávníků\n"
                + format_table(diner_headers, diner_values(sorted_diners))
                + f"\nCelkem strávníků / objednávek: {len(sorted_diners)}"
            )

    return "\n\n".join(sections)


def create_pdf(
    config: AppConfig,
    report: ReportData,
    output_path: Path | None = None,
) -> Path:
    """Vytvoří tiskovou PDF sestavu a vrátí její absolutní cestu."""
    try:
        from pypdf import PdfReader
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4, landscape, portrait
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            CondPageBreak,
            LongTable,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Chybí knihovna pro PDF. Nainstalujte závislosti příkazem "
            "'python -m pip install -r requirements.txt'."
        ) from exc

    target = (output_path or config.pdf_output).resolve()
    active_categories = report.active_categories or config.categories
    if target.suffix.lower() != ".pdf":
        raise ConfigError("Výstupní soubor musí mít příponu .pdf.")
    target.parent.mkdir(parents=True, exist_ok=True)

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

    page_size = (
        portrait(A4)
        if config.pdf_orientation == "na_vysku"
        else landscape(A4)
    )
    page_width, page_height = page_size
    left_margin = 13 * mm
    right_margin = 13 * mm
    top_margin = 20 * mm
    bottom_margin = 15 * mm
    usable_width = page_width - left_margin - right_margin

    navy = colors.HexColor("#213B57")
    blue = colors.HexColor("#2F6F9F")
    pale_blue = colors.HexColor("#EAF2F8")
    pale_gray = colors.HexColor("#F5F7F9")
    medium_gray = colors.HexColor("#D3DBE2")
    text_color = colors.HexColor("#1F2933")
    muted = colors.HexColor("#5D6B78")

    data_font = "StravovaciSans-Bold" if config.pdf_bold else "StravovaciSans"
    label_font = "StravovaciSans-Bold"
    data_size = config.pdf_data_font_size
    label_size = config.pdf_label_font_size

    body_style = ParagraphStyle(
        "Body",
        fontName=data_font,
        fontSize=data_size,
        leading=max(data_size + 2.1, data_size * 1.24),
        textColor=text_color,
        alignment=TA_LEFT,
    )
    cell_style = ParagraphStyle(
        "Cell",
        parent=body_style,
        fontSize=data_size,
        leading=max(data_size + 1.7, data_size * 1.2),
    )
    cell_center_style = ParagraphStyle(
        "CellCenter",
        parent=cell_style,
        alignment=TA_CENTER,
    )
    header_cell_style = ParagraphStyle(
        "HeaderCell",
        parent=cell_style,
        fontName=label_font,
        fontSize=label_size,
        leading=max(label_size + 1.7, label_size * 1.2),
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    title_style = ParagraphStyle(
        "Title",
        parent=body_style,
        fontName=label_font,
        fontSize=max(14, min(28, label_size * 2.4)),
        leading=max(18, min(34, label_size * 2.9)),
        textColor=navy,
        spaceAfter=2 * mm,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=body_style,
        fontSize=max(data_size, min(18, label_size * 1.25)),
        leading=max(data_size + 3, min(22, label_size * 1.6)),
        textColor=muted,
        spaceAfter=4 * mm,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=body_style,
        fontName=label_font,
        fontSize=max(9, min(22, label_size * 1.55)),
        leading=max(12, min(27, label_size * 1.9)),
        textColor=navy,
        spaceBefore=3 * mm,
        spaceAfter=1.5 * mm,
        keepWithNext=True,
    )
    small_style = ParagraphStyle(
        "Small",
        parent=body_style,
        fontSize=max(5, data_size * 0.95),
        leading=max(data_size + 1.5, data_size * 1.18),
        textColor=muted,
    )

    def para(value: object, style: ParagraphStyle = cell_style) -> Paragraph:
        return Paragraph(escape(str(value)), style)

    def make_table(
        headers: Sequence[str],
        rows: Sequence[Sequence[object]],
        widths: Sequence[float],
        *,
        centered_columns: set[int] | None = None,
        total_row: bool = False,
        repeat_header: bool = True,
    ) -> Table:
        centered_columns = centered_columns or set()
        data: list[list[object]] = [
            [para(header, header_cell_style) for header in headers]
        ]
        for row in rows:
            rendered_row = []
            for index, value in enumerate(row):
                style = cell_center_style if index in centered_columns else cell_style
                rendered_row.append(para(value, style))
            data.append(rendered_row)

        style_commands: list[tuple[Any, ...]] = [
            ("BACKGROUND", (0, 0), (-1, 0), navy),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), label_font),
            ("FONTNAME", (0, 1), (-1, -1), data_font),
            ("FONTSIZE", (0, 0), (-1, 0), label_size),
            ("FONTSIZE", (0, 1), (-1, -1), data_size),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.35, medium_gray),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, pale_gray]),
            ("LEFTPADDING", (0, 0), (-1, -1), 2.2 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2.2 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 1.3 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.3 * mm),
        ]
        for column in centered_columns:
            style_commands.append(("ALIGN", (column, 1), (column, -1), "CENTER"))
        if total_row and rows:
            style_commands.extend(
                [
                    ("BACKGROUND", (0, -1), (-1, -1), pale_blue),
                    ("FONTNAME", (0, -1), (-1, -1), label_font),
                ]
            )
        return LongTable(
            data,
            colWidths=list(widths),
            repeatRows=1 if repeat_header else 0,
            hAlign="LEFT",
            splitByRow=1,
            style=TableStyle(style_commands),
        )

    subject = report.subject_name or "Stravovací provoz"
    date_text = config.report_date.strftime(DATE_FORMAT)
    document_title = (
        "Seznam strávníků" if config.show_diner_list
        else "Souhrn objednané stravy"
    )
    total_portions = sum(item.portions for item in report.menus)
    temporary = target.with_name(f".{target.stem}.tmp.pdf")

    def page_header_footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setTitle(f"{document_title} - {date_text}")
        canvas.setAuthor(subject)
        footer_font_size = max(6, min(11, label_size * 0.95))
        canvas.setFont(data_font, footer_font_size)
        canvas.setFillColor(muted)
        canvas.drawString(left_margin, page_height - 10 * mm, subject)
        canvas.drawRightString(
            page_width - right_margin,
            page_height - 10 * mm,
            f"Objednaná strava - {date_text}",
        )
        canvas.setStrokeColor(medium_gray)
        canvas.setLineWidth(0.4)
        canvas.line(
            left_margin,
            page_height - 12 * mm,
            page_width - right_margin,
            page_height - 12 * mm,
        )
        canvas.line(
            left_margin,
            10 * mm,
            page_width - right_margin,
            10 * mm,
        )
        canvas.setFont(data_font, max(6, min(10, data_size * 0.95)))
        canvas.drawCentredString(
            page_width / 2,
            6.2 * mm,
            f"Strana {doc.page}",
        )
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(temporary),
        pagesize=page_size,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        title=f"{document_title} - {date_text}",
        author=subject,
        subject="Objednaná strava",
    )

    story: list[Any] = [
        Paragraph(escape(subject), title_style),
        Paragraph(document_title, subtitle_style),
    ]

    info_data = [
        [
            para("Datum", header_cell_style),
            para(date_text, cell_center_style),
            para("Celkem porcí", header_cell_style),
            para(total_portions, cell_center_style),
            para("Vybraných kategorií", header_cell_style),
            para(len(active_categories), cell_center_style),
        ]
    ]
    info_base_widths = [28 * mm, 29 * mm, 34 * mm, 22 * mm, 43 * mm, 22 * mm]
    info_scale = min(1.0, usable_width / sum(info_base_widths))
    info_widths = [width * info_scale for width in info_base_widths]
    info_table = Table(
        info_data,
        colWidths=info_widths,
        hAlign="LEFT",
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), navy),
                ("BACKGROUND", (2, 0), (2, 0), navy),
                ("BACKGROUND", (4, 0), (4, 0), navy),
                ("BACKGROUND", (1, 0), (1, 0), pale_blue),
                ("BACKGROUND", (3, 0), (3, 0), pale_blue),
                ("BACKGROUND", (5, 0), (5, 0), pale_blue),
                ("GRID", (0, 0), (-1, -1), 0.35, medium_gray),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2.2 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2.2 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 1.6 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6 * mm),
            ]
        ),
    )
    story.extend([info_table, Spacer(1, 2 * mm)])

    story.append(Paragraph("Jídelníček a počty porcí", section_style))
    if report.menus:
        menu_rows: list[tuple[object, ...]] = [
            (
                item.meal_type,
                f"Menu {item.menu}",
                item.portions,
                item.meal_name or "[název v jídelníčku nenalezen]",
            )
            for item in report.menus
        ]
        menu_rows.append(("Celkem", "", total_portions, ""))
        story.append(
            make_table(
                ("Typ stravy", "Přihláška", "Počet", "Název jídla"),
                menu_rows,
                (36 * mm, 24 * mm, 20 * mm, usable_width - 80 * mm),
                centered_columns={1, 2},
                total_row=True,
            )
        )
    else:
        story.append(Paragraph("Nenalezeny žádné objednávky.", body_style))

    if config.show_by_categories and report.categories:
        story.append(Paragraph("Přihlášky podle kategorií", section_style))
        category_rows: list[tuple[object, ...]] = [
            (
                item.code,
                item.name or "[bez názvu]",
                item.norm or "[bez normy]",
                item.applications,
            )
            for item in report.categories
        ]
        category_rows.append(
            (
                "",
                "Celkem",
                "",
                sum(item.applications for item in report.categories),
            )
        )
        story.append(
            make_table(
                ("Označení", "Název kategorie", "Norma", "Přihlášek"),
                category_rows,
                (
                    usable_width * 0.16,
                    usable_width * 0.55,
                    usable_width * 0.13,
                    usable_width * 0.16,
                ),
                centered_columns={0, 2, 3},
                total_row=True,
            )
        )

    if config.show_by_norms and report.norms:
        story.append(Paragraph("Objednaná menu podle norem", section_style))
        norm_meal_types = sorted(
            {row.meal_type for row in report.norms}, key=str.casefold
        )
        for meal_index, meal_type in enumerate(norm_meal_types):
            meal_rows = [row for row in report.norms if row.meal_type == meal_type]
            menus = sorted({row.menu for row in meal_rows})
            extra_norms = sorted(
                {
                    row.norm or "[bez normy]"
                    for row in meal_rows
                    if (row.norm or "[bez normy]") not in DEFAULT_NORMS
                },
                key=str.casefold,
            )
            norms = [*DEFAULT_NORMS, *extra_norms]
            counts = {
                (row.norm or "[bez normy]", row.menu): row.portions
                for row in meal_rows
            }
            norm_rows: list[tuple[object, ...]] = []
            for norm in norms:
                values = [counts.get((norm, menu), 0) for menu in menus]
                norm_rows.append((norm, *values, sum(values)))

            if meal_index:
                story.append(Spacer(1, 1.5 * mm))
            story.append(Paragraph(f"Typ stravy: {escape(meal_type)}", small_style))
            norm_width = 28 * mm
            total_width = 24 * mm
            menu_width = min(
                26 * mm,
                (usable_width - norm_width - total_width) / max(1, len(menus)),
            )
            widths = [norm_width, *([menu_width] * len(menus)), total_width]
            story.append(
                make_table(
                    ("Norma", *(f"Menu {menu}" for menu in menus), "Celkem"),
                    norm_rows,
                    widths,
                    centered_columns=set(range(len(widths))),
                )
            )

    if config.show_diner_list:
        story.extend(
            [
                PageBreak(),
                Paragraph("Seznam strávníků", section_style),
            ]
        )

        diner_headers = (
            "Jméno",
            "Kategorie",
            "Přihláška",
            "Norma",
            "Objednané jídlo",
        )
        diner_widths = (
            usable_width * 0.19,
            usable_width * 0.18,
            usable_width * 0.11,
            usable_width * 0.08,
            usable_width * 0.44,
        )

        def diner_sort_key(row: DinerOrder) -> tuple[str, str, int]:
            return (
                (row.name or "").casefold(),
                row.meal_type.casefold(),
                row.menu,
            )

        def diner_pdf_rows(rows: Sequence[DinerOrder]) -> list[tuple[object, ...]]:
            return [
                (
                    row.name or "[bez jména]",
                    row.category_name or row.category_code,
                    row.application_label,
                    row.norm or "[bez normy]",
                    row.meal_name or "[název v jídelníčku nenalezen]",
                )
                for row in rows
            ]

        if not report.diners:
            story.append(Paragraph("Nenalezeni žádní strávníci s objednávkou.", body_style))
        elif config.category_separation:
            grouped: dict[str, list[DinerOrder]] = defaultdict(list)
            for diner in report.diners:
                grouped[diner.category_code].append(diner)

            for category_code in active_categories:
                category_diners = sorted(grouped.get(category_code, []), key=diner_sort_key)
                if not category_diners:
                    continue
                category_name = next(
                    (row.category_name for row in category_diners if row.category_name),
                    category_code,
                )
                story.append(CondPageBreak(35 * mm))
                category_heading = Table(
                    [[para(category_name, ParagraphStyle(
                        f"Category-{category_code}",
                        parent=body_style,
                        fontName=label_font,
                        fontSize=max(8, min(18, label_size * 1.38)),
                        leading=max(10.5, min(22, label_size * 1.7)),
                        textColor=navy,
                    ))]],
                    colWidths=[usable_width],
                    hAlign="LEFT",
                    style=TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), pale_blue),
                            ("BOX", (0, 0), (-1, -1), 0.45, blue),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
                            ("TOPPADDING", (0, 0), (-1, -1), 1.7 * mm),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.7 * mm),
                        ]
                    ),
                )
                story.extend(
                    [
                        category_heading,
                        Spacer(1, 1.2 * mm),
                        make_table(
                            diner_headers,
                            diner_pdf_rows(category_diners),
                            diner_widths,
                            centered_columns={2, 3},
                        ),
                        Spacer(1, 2.5 * mm),
                    ]
                )
        else:
            sorted_diners = sorted(report.diners, key=diner_sort_key)
            story.append(
                make_table(
                    diner_headers,
                    diner_pdf_rows(sorted_diners),
                    diner_widths,
                    centered_columns={2, 3},
                )
            )

        story.extend(
            [
                Spacer(1, 2 * mm),
                Paragraph(
                    f"Celkem strávníků / objednávek: {len(report.diners)}",
                    small_style,
                ),
            ]
        )

    try:
        document.build(
            story,
            onFirstPage=page_header_footer,
            onLaterPages=page_header_footer,
        )
        reader = PdfReader(str(temporary))
        if not reader.pages:
            raise RuntimeError("Vytvořené PDF nemá žádnou stránku.")
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return target


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config, args.date_override, args.pdf_override)
        report = fetch_report(config)
        if not args.no_console:
            print(
                render_table(
                    config,
                    report.menus,
                    report.categories,
                    report.norms,
                    report.diners,
                    report.subject_name,
                    report.active_categories,
                )
            )
        pdf_path = create_pdf(config, report)
        print(f"\nPDF vytvořeno: {pdf_path}")
        return 0
    except (ConfigError, RuntimeError) as exc:
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nPřerušeno uživatelem.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"CHYBA DB: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

