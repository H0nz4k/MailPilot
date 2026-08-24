"""Jedno načtení podkladů uzávěrky pro arch, rekapitulaci i FKSP.

Těžké funkce Jídelny (`getcenamesicniprihlasky`, `dej_preplatek`, …) se volají
jen jednou za období. Otisk tabulek rozhodne, zda jdou použít uložené podklady,
nebo se mají spočítat znovu.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from runtime_paths import application_directory
from services.pricing_mode import detect_pricing_mode_info
from stravovaci_sestava import AppConfig
from uzaverka_pdf import (
    SubjectHeader,
    bulk_rezie_sql,
    fetch_subject_header,
    month_payments_sql,
    previous_period_sql,
    prihlaska_expression,
    report_progress,
)


CACHE_VERSION = 1
CACHE_DIRNAME = "cache"
CACHE_SUBDIR = "uzaverka"
PRICING_TABLES = ("public.cenik", "public.cenik_sluzeb", "public.sazby")

PAYMENT_QUERY = """
        SELECT BTRIM(typplatby::text), NULLIF(BTRIM(popis), '')
        FROM public.typplatb
"""

COUNT_QUERY = """
        SELECT
            public.pocet_evidovanych_stravniku(%s, %s),
            public.pocet_stravujicichse_stravniku(%s, %s),
            public.pocet_hromadnych_stravniku(%s, %s)
"""

COUNT_CATEGORY_QUERY = """
        SELECT
            public.pocet_evidovanych_stravniku_k(%s, %s, %s),
            public.pocet_stravujicichse_stravniku_k(%s, %s, %s)
"""

ZAPSANI_QUERY = """
        SELECT COUNT(*)
        FROM public.stravnik
        WHERE COALESCE(deleted, false) = false
          AND COALESCE(hromadny, false) = false
"""

_PREV_MONTH, _PREV_YEAR = previous_period_sql("p.mesic", "p.rok")
_MONTH_PAYMENTS = month_payments_sql("s.evidcislo", "p.mesic", "p.rok")
_PRIHLASKA = prihlaska_expression("p")
_KATEGORIE = "COALESCE(NULLIF(BTRIM(p.kategorie), ''), s.kategorie)"


def _day_select_sql(alias: str = "p") -> str:
    return ", ".join(
        f"NULLIF(BTRIM({alias}.d{day:02d}::text), '') AS d{day:02d}"
        for day in range(1, 32)
    )


def _fingerprint_days_sql(alias: str = "p") -> str:
    return " || '|' || ".join(
        f"COALESCE({alias}.d{day:02d}::text, '')" for day in range(1, 32)
    )


INDIVIDUAL_QUERY = f"""
        SELECT
            NULLIF(BTRIM(s.jmeno), '') AS jmeno,
            s.evidcislo,
            NULLIF(BTRIM(s.varsymb), '') AS varsymb,
            NULLIF(BTRIM(s.trida), '') AS trida,
            BTRIM({_KATEGORIE}) AS kategorie,
            BTRIM(COALESCE(s.kategorie, '')) AS kategorie_stravnik,
            NULLIF(BTRIM(k.nazev), '') AS nazev,
            NULLIF(BTRIM(ks.nazev), '') AS nazev_stravnik,
            NULLIF(BTRIM(k.norma), '') AS norma,
            BTRIM(p.typsluzby) AS typsluzby,
            BTRIM(COALESCE(s.zpusobplatby::text, '')) AS zpusobplatby,
            COALESCE(s.deleted, false) AS deleted,
            {_day_select_sql("p")},
            COALESCE(p.pocet, live.pocet, 0) AS pocet,
            COALESCE(live.pocet, 0) AS pocet_live,
            COALESCE(
                p.cena,
                public.getcenamesicniprihlasky(
                    p.typsluzby,
                    {_KATEGORIE},
                    p.rok,
                    p.mesic,
                    {_PRIHLASKA}
                ),
                0
            ) AS predpis,
            COALESCE(
                public.getlimitmesicniprihlasky(
                    p.typsluzby,
                    {_KATEGORIE},
                    p.rok,
                    p.mesic,
                    {_PRIHLASKA}
                ),
                0
            ) AS limitam,
            COALESCE(
                public.getfkspmesicniprihlasky(
                    p.typsluzby,
                    {_KATEGORIE},
                    p.rok,
                    p.mesic,
                    {_PRIHLASKA}
                ),
                0
            ) AS fksp,
            CASE
                WHEN BTRIM({_KATEGORIE}) IS NOT DISTINCT FROM BTRIM(s.kategorie)
                THEN NULL
                ELSE public.getfkspmesicniprihlasky(
                    p.typsluzby,
                    s.kategorie,
                    p.rok,
                    p.mesic,
                    {_PRIHLASKA}
                )
            END AS fksp_stravnik,
            COALESCE(
                public.getostatrmesicniprihlasky(
                    p.typsluzby,
                    {_KATEGORIE},
                    p.rok,
                    p.mesic,
                    {_PRIHLASKA}
                ),
                0
            ) AS ostatr,
            CASE
                WHEN BTRIM({_KATEGORIE}) IS NOT DISTINCT FROM BTRIM(s.kategorie)
                THEN NULL
                ELSE public.getostatrmesicniprihlasky(
                    p.typsluzby,
                    s.kategorie,
                    p.rok,
                    p.mesic,
                    {_PRIHLASKA}
                )
            END AS ostatr_stravnik,
            COALESCE(public.dej_preplatek(s.evidcislo, p.mesic, p.rok), 0) AS platba,
            COALESCE(public.dej_preplatek(s.evidcislo, {_PREV_MONTH}, {_PREV_YEAR}), 0) AS preplatek_mm,
            {_MONTH_PAYMENTS} AS preplatek_am
        FROM public.prihlas AS p
        JOIN public.stravnik AS s
          ON s.evidcislo = p.stravnik
        LEFT JOIN public.kategor AS k
          ON BTRIM(k.oznaceni) = BTRIM({_KATEGORIE})
        LEFT JOIN public.kategor AS ks
          ON BTRIM(ks.oznaceni) = BTRIM(s.kategorie)
        CROSS JOIN LATERAL (
            SELECT public.getpocetprihlasek({_PRIHLASKA}, 0) AS pocet
        ) AS live
        WHERE p.rok = %s
          AND p.mesic = %s
          AND COALESCE(s.hromadny, false) = false
        ORDER BY
            LOWER(BTRIM({_KATEGORIE})),
            BTRIM({_KATEGORIE}),
            CASE WHEN NULLIF(BTRIM(s.trida), '') IS NULL THEN 1 ELSE 0 END,
            LOWER(BTRIM(COALESCE(s.trida, ''))),
            BTRIM(COALESCE(s.trida, '')),
            LOWER(BTRIM(COALESCE(s.jmeno, ''))),
            s.jmeno,
            p.typsluzby
"""

BULK_QUERY = f"""
        SELECT
            NULLIF(BTRIM(s.jmeno), '') AS jmeno,
            s.evidcislo,
            NULLIF(BTRIM(s.varsymb), '') AS varsymb,
            NULLIF(BTRIM(s.trida), '') AS trida,
            BTRIM({_KATEGORIE}) AS kategorie,
            BTRIM(COALESCE(s.kategorie, '')) AS kategorie_stravnik,
            NULLIF(BTRIM(k.nazev), '') AS nazev,
            NULLIF(BTRIM(k.nazev), '') AS nazev_stravnik,
            NULLIF(BTRIM(k.norma), '') AS norma,
            BTRIM(p.typsluzby) AS typsluzby,
            BTRIM(COALESCE(s.zpusobplatby::text, '')) AS zpusobplatby,
            COALESCE(s.deleted, false) AS deleted,
            {_day_select_sql("p")},
            COALESCE(public.pocetprihlashromadnehostr(p.id, 1, 31), 0) AS pocet,
            COALESCE(public.pocetprihlashromadnehostr(p.id, 1, 31), 0) AS pocet_live,
            COALESCE(public.cenaprihlashromadnehostr(p.id, 1, 31), 0) AS predpis,
            COALESCE(public.limitprihlashromadnehostr(p.id, 1, 31), 0) AS limitam,
            COALESCE({bulk_rezie_sql("getfkspmenuden")}, 0) AS fksp,
            NULL::numeric AS fksp_stravnik,
            COALESCE({bulk_rezie_sql("getostatrmenuden")}, 0) AS ostatr,
            NULL::numeric AS ostatr_stravnik,
            COALESCE(public.dej_preplatek(s.evidcislo, p.mesic, p.rok), 0) AS platba,
            COALESCE(public.dej_preplatek(s.evidcislo, {_PREV_MONTH}, {_PREV_YEAR}), 0) AS preplatek_mm,
            {_MONTH_PAYMENTS} AS preplatek_am
        FROM public.prihlasn AS p
        JOIN public.stravnik AS s
          ON s.evidcislo = p.stravnik
        LEFT JOIN public.kategor AS k
          ON BTRIM(k.oznaceni) = BTRIM({_KATEGORIE})
        WHERE p.rok = %s
          AND p.mesic = %s
          AND public.pocetprihlashromadnehostr(p.id, 1, 31) > 0
        ORDER BY
            LOWER(BTRIM({_KATEGORIE})),
            BTRIM({_KATEGORIE}),
            LOWER(BTRIM(COALESCE(s.jmeno, ''))),
            s.jmeno,
            p.typsluzby
"""

_DINER_SUBQUERY = """
            SELECT stravnik FROM public.prihlas WHERE rok = %s AND mesic = %s
            UNION
            SELECT stravnik FROM public.prihlasn WHERE rok = %s AND mesic = %s
"""

FINGERPRINT_QUERY = f"""
        SELECT
            (SELECT COUNT(*) FROM public.prihlas WHERE rok = %s AND mesic = %s),
            (SELECT COALESCE(md5(string_agg(fp.payload, ',' ORDER BY fp.id)), '')
             FROM (
                SELECT
                    p.id,
                    concat_ws(
                        '|',
                        p.id::text,
                        p.stravnik::text,
                        COALESCE(p.typsluzby::text, ''),
                        COALESCE(p.kategorie, ''),
                        COALESCE(p.pocet::text, ''),
                        COALESCE(p.cena::text, ''),
                        {_fingerprint_days_sql("p")}
                    ) AS payload
                FROM public.prihlas AS p
                WHERE p.rok = %s AND p.mesic = %s
             ) AS fp),
            (SELECT COUNT(*) FROM public.prihlasn WHERE rok = %s AND mesic = %s),
            (SELECT COALESCE(md5(string_agg(fp.payload, ',' ORDER BY fp.id)), '')
             FROM (
                SELECT
                    p.id,
                    concat_ws(
                        '|',
                        p.id::text,
                        p.stravnik::text,
                        COALESCE(p.typsluzby::text, ''),
                        COALESCE(p.kategorie, ''),
                        {_fingerprint_days_sql("p")}
                    ) AS payload
                FROM public.prihlasn AS p
                WHERE p.rok = %s AND p.mesic = %s
             ) AS fp),
            (SELECT COUNT(*) FROM public.penden AS d
             WHERE d.evidcislo IN ({_DINER_SUBQUERY})),
            (SELECT COALESCE(SUM(d.castka), 0) FROM public.penden AS d
             WHERE d.evidcislo IN ({_DINER_SUBQUERY})),
            (SELECT COALESCE(md5(string_agg(
                    concat_ws(
                        '|',
                        d.id::text,
                        d.evidcislo::text,
                        d.rok::text,
                        d.mesic::text,
                        COALESCE(d.typ::text, ''),
                        COALESCE(d.castka::text, '')
                    ),
                    ',' ORDER BY d.id
                )), '')
             FROM public.penden AS d
             WHERE d.evidcislo IN ({_DINER_SUBQUERY})),
            (SELECT COALESCE(md5(string_agg(
                    concat_ws(
                        '|',
                        s.evidcislo::text,
                        COALESCE(s.kategorie, ''),
                        COALESCE(s.deleted::text, ''),
                        COALESCE(s.hromadny::text, ''),
                        COALESCE(s.zpusobplatby::text, ''),
                        COALESCE(s.jmeno, ''),
                        COALESCE(s.trida, ''),
                        COALESCE(s.varsymb, '')
                    ),
                    ',' ORDER BY s.evidcislo
                )), '')
             FROM public.stravnik AS s
             WHERE s.evidcislo IN ({_DINER_SUBQUERY})),
            (SELECT COALESCE(md5(string_agg(
                    concat_ws('|', COALESCE(parametr, ''), COALESCE(hodnota, '')),
                    ',' ORDER BY parametr
                )), '')
             FROM public.parametry
             WHERE LOWER(BTRIM(sekce)) = LOWER('BACKUP'))
"""


@dataclass(frozen=True)
class PrihlasPodklad:
    name: str | None
    evidence_no: int
    var_symbol: str | None
    class_name: str | None
    category_code: str
    diner_category: str
    category_name: str | None
    diner_category_name: str | None
    norm: str | None
    meal_type: str
    payment_method_code: str
    deleted: bool
    days: tuple[str, ...]
    portions: int
    portions_live: int
    prescription: float
    monthly_limit: float
    fksp: float
    fksp_diner: float
    other_overhead: float
    other_overhead_diner: float
    payment: float
    credit_prev: float
    credit_now: float

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "evidence_no": self.evidence_no,
            "var_symbol": self.var_symbol,
            "class_name": self.class_name,
            "category_code": self.category_code,
            "diner_category": self.diner_category,
            "category_name": self.category_name,
            "diner_category_name": self.diner_category_name,
            "norm": self.norm,
            "meal_type": self.meal_type,
            "payment_method_code": self.payment_method_code,
            "deleted": self.deleted,
            "days": list(self.days),
            "portions": self.portions,
            "portions_live": self.portions_live,
            "prescription": self.prescription,
            "monthly_limit": self.monthly_limit,
            "fksp": self.fksp,
            "fksp_diner": self.fksp_diner,
            "other_overhead": self.other_overhead,
            "other_overhead_diner": self.other_overhead_diner,
            "payment": self.payment,
            "credit_prev": self.credit_prev,
            "credit_now": self.credit_now,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "PrihlasPodklad":
        return cls(
            name=raw.get("name"),
            evidence_no=int(raw.get("evidence_no") or 0),
            var_symbol=raw.get("var_symbol"),
            class_name=raw.get("class_name"),
            category_code=str(raw.get("category_code") or "").strip(),
            diner_category=str(raw.get("diner_category") or "").strip(),
            category_name=raw.get("category_name"),
            diner_category_name=raw.get("diner_category_name"),
            norm=raw.get("norm"),
            meal_type=str(raw.get("meal_type") or "").strip(),
            payment_method_code=str(raw.get("payment_method_code") or "").strip(),
            deleted=bool(raw.get("deleted")),
            days=_pad_days(raw.get("days") or ()),
            portions=int(raw.get("portions") or 0),
            portions_live=int(raw.get("portions_live") or 0),
            prescription=float(raw.get("prescription") or 0),
            monthly_limit=float(raw.get("monthly_limit") or 0),
            fksp=float(raw.get("fksp") or 0),
            fksp_diner=float(raw.get("fksp_diner") or 0),
            other_overhead=float(raw.get("other_overhead") or 0),
            other_overhead_diner=float(raw.get("other_overhead_diner") or 0),
            payment=float(raw.get("payment") or 0),
            credit_prev=float(raw.get("credit_prev") or 0),
            credit_now=float(raw.get("credit_now") or 0),
        )


@dataclass(frozen=True)
class ClosingCounts:
    dining: int
    registered: int
    enrolled: int
    bulk: int
    by_category: dict[str, tuple[int, int]]

    def to_json(self) -> dict[str, Any]:
        return {
            "dining": self.dining,
            "registered": self.registered,
            "enrolled": self.enrolled,
            "bulk": self.bulk,
            "by_category": {
                code: [registered, dining]
                for code, (registered, dining) in self.by_category.items()
            },
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "ClosingCounts":
        by_category = {
            str(code): (int(values[0] or 0), int(values[1] or 0))
            for code, values in (raw.get("by_category") or {}).items()
        }
        return cls(
            dining=int(raw.get("dining") or 0),
            registered=int(raw.get("registered") or 0),
            enrolled=int(raw.get("enrolled") or 0),
            bulk=int(raw.get("bulk") or 0),
            by_category=by_category,
        )


@dataclass(frozen=True)
class ClosingPodklady:
    header: SubjectHeader
    payments: dict[str, str]
    individuals: tuple[PrihlasPodklad, ...]
    bulk: tuple[PrihlasPodklad, ...]
    counts: ClosingCounts
    period: date
    fingerprint: str
    from_cache: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "version": CACHE_VERSION,
            "header": {
                "subject_name": self.header.subject_name,
                "address": self.header.address,
                "zip_code": self.header.zip_code,
                "city": self.header.city,
                "company_id": self.header.company_id,
                "vat_id": self.header.vat_id,
            },
            "payments": self.payments,
            "individuals": [row.to_json() for row in self.individuals],
            "bulk": [row.to_json() for row in self.bulk],
            "counts": self.counts.to_json(),
            "period": self.period.isoformat(),
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any], *, from_cache: bool = False) -> "ClosingPodklady":
        header_raw = raw.get("header") or {}
        period_raw = str(raw.get("period") or "")
        year, month, day = (int(part) for part in period_raw.split("-"))
        payments = {
            str(code): str(label)
            for code, label in (raw.get("payments") or {}).items()
        }
        return cls(
            header=SubjectHeader(
                subject_name=header_raw.get("subject_name"),
                address=header_raw.get("address"),
                zip_code=header_raw.get("zip_code"),
                city=header_raw.get("city"),
                company_id=header_raw.get("company_id"),
                vat_id=header_raw.get("vat_id"),
            ),
            payments=payments,
            individuals=tuple(
                PrihlasPodklad.from_json(item) for item in raw.get("individuals") or ()
            ),
            bulk=tuple(PrihlasPodklad.from_json(item) for item in raw.get("bulk") or ()),
            counts=ClosingCounts.from_json(raw.get("counts") or {}),
            period=date(year, month, day),
            fingerprint=str(raw.get("fingerprint") or ""),
            from_cache=from_cache,
        )


def cache_directory(root: Path | None = None) -> Path:
    base = root if root is not None else application_directory()
    return base / CACHE_DIRNAME / CACHE_SUBDIR


def cache_path_for(year: int, month: int, root: Path | None = None) -> Path:
    return cache_directory(root) / f"{year:04d}-{month:02d}.json"


def fingerprint_digest(parts: Sequence[Any]) -> str:
    payload = json.dumps([_json_safe(item) for item in parts], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:
            pass
    if hasattr(value, "__float__") and not isinstance(value, (int, float, bool)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _row_mapping(cursor: Any, record: Sequence[Any]) -> dict[str, Any]:
    return {str(column.name): value for column, value in zip(cursor.description, record)}


def _day_mark(value: object) -> str:
    return str(value or "").strip()


def _pad_days(values: Sequence[Any]) -> tuple[str, ...]:
    days = tuple(_day_mark(item) for item in values)
    if len(days) < 31:
        days = days + ("",) * (31 - len(days))
    return days[:31]


def podklad_from_mapping(data: dict[str, Any]) -> PrihlasPodklad:
    fksp = float(data.get("fksp") or 0)
    ostatr = float(data.get("ostatr") or 0)
    fksp_raw = data.get("fksp_stravnik")
    ostatr_raw = data.get("ostatr_stravnik")
    days = _pad_days(data.get(f"d{day:02d}") for day in range(1, 32))
    return PrihlasPodklad(
        name=data.get("jmeno"),
        evidence_no=int(data.get("evidcislo") or 0),
        var_symbol=data.get("varsymb"),
        class_name=data.get("trida"),
        category_code=str(data.get("kategorie") or "").strip(),
        diner_category=str(data.get("kategorie_stravnik") or "").strip(),
        category_name=data.get("nazev"),
        diner_category_name=data.get("nazev_stravnik"),
        norm=data.get("norma"),
        meal_type=str(data.get("typsluzby") or "").strip(),
        payment_method_code=str(data.get("zpusobplatby") or "").strip(),
        deleted=bool(data.get("deleted")),
        days=days,
        portions=int(data.get("pocet") or 0),
        portions_live=int(data.get("pocet_live") or 0),
        prescription=float(data.get("predpis") or 0),
        monthly_limit=float(data.get("limitam") or 0),
        fksp=fksp,
        fksp_diner=fksp if fksp_raw is None else float(fksp_raw or 0),
        other_overhead=ostatr,
        other_overhead_diner=ostatr if ostatr_raw is None else float(ostatr_raw or 0),
        payment=float(data.get("platba") or 0),
        credit_prev=float(data.get("preplatek_mm") or 0),
        credit_now=float(data.get("preplatek_am") or 0),
    )


def recap_tuple(row: PrihlasPodklad) -> tuple[Any, ...]:
    """Poziční tvar, který už umí `_aggregate_rows` rekapitulace."""
    return (
        row.category_code,
        row.category_name,
        row.norm,
        row.meal_type,
        row.portions,
        row.prescription,
        row.monthly_limit,
        row.fksp,
        row.other_overhead,
        row.payment,
        row.credit_prev,
        row.credit_now,
        row.evidence_no,
    )


def in_categories(code: str, categories: Sequence[str]) -> bool:
    allowed = {str(item).strip() for item in categories}
    return str(code or "").strip() in allowed


def load_cache(path: Path) -> ClosingPodklady | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or int(raw.get("version") or 0) != CACHE_VERSION:
        return None
    try:
        return ClosingPodklady.from_json(raw, from_cache=True)
    except (TypeError, ValueError, KeyError):
        return None


def save_cache(path: Path, podklady: ClosingPodklady) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = podklady.to_json()
    payload["from_cache"] = False
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def fetch_fingerprint(cursor: Any, year: int, month: int) -> str:
    period = (year, month)
    diners = period + period
    params = (
        *period,
        *period,
        *period,
        *period,
        *diners,
        *diners,
        *diners,
        *diners,
    )
    cursor.execute(FINGERPRINT_QUERY, params)
    row = cursor.fetchone() or ()
    pricing = detect_pricing_mode_info(cursor)
    table_parts: list[Any] = []
    for table_name in PRICING_TABLES:
        table_parts.extend(_table_fingerprint(cursor, table_name))
    return fingerprint_digest((row, pricing.mode, pricing.source, table_parts))


def _table_fingerprint(cursor: Any, table_name: str) -> tuple[str, int, str]:
    """Deterministický otisk cenové tabulky bez předpokladu konkrétního schema."""
    try:
        from psycopg import sql
    except ImportError:
        return (table_name, 0, "missing-psycopg")
    schema, table = table_name.split(".", 1)
    cursor.execute("SELECT to_regclass(%s)", (f"{schema}.{table}",))
    exists = cursor.fetchone()
    if not exists or exists[0] is None:
        return (table_name, 0, "missing")
    query = sql.SQL(
        """
        SELECT
            COUNT(*)::integer,
            COALESCE(
                md5(
                    string_agg(
                        row_to_json(t)::text,
                        ',' ORDER BY row_to_json(t)::text
                    )
                ),
                ''
            )
        FROM {schema}.{table} AS t
        """
    ).format(
        schema=sql.Identifier(schema),
        table=sql.Identifier(table),
    )
    cursor.execute(query)
    count, digest = cursor.fetchone() or (0, "")
    return (table_name, int(count or 0), str(digest or ""))


def _load_payment_names(cursor: Any) -> dict[str, str]:
    try:
        cursor.execute(PAYMENT_QUERY)
    except Exception:
        cursor.connection.rollback()
        return {}
    names: dict[str, str] = {}
    for code, label in cursor.fetchall():
        if code:
            names[str(code).strip()] = label or str(code).strip()
    return names


def _fetch_rows(cursor: Any, sql: str, params: tuple[Any, ...]) -> tuple[PrihlasPodklad, ...]:
    cursor.execute(sql, params)
    records = cursor.fetchall()
    return tuple(podklad_from_mapping(_row_mapping(cursor, record)) for record in records)


def _fetch_counts(
    cursor: Any,
    year: int,
    month: int,
    records: Sequence[PrihlasPodklad],
    on_progress: Any,
) -> ClosingCounts:
    cursor.execute(COUNT_QUERY, (year, month, year, month, year, month))
    registered_total, dining_total, bulk = cursor.fetchone()
    cursor.execute(ZAPSANI_QUERY)
    enrolled = int(cursor.fetchone()[0] or 0)
    bulk = int(bulk or 0)
    registered = max(int(registered_total or 0) - bulk, 0)
    dining = max(int(dining_total or 0) - bulk, 0)
    codes = sorted({row.category_code for row in records if row.category_code})
    by_category: dict[str, tuple[int, int]] = {}
    for index, code in enumerate(codes, start=1):
        cursor.execute(COUNT_CATEGORY_QUERY, (year, month, code, year, month, code))
        evid, strav = cursor.fetchone()
        by_category[code] = (int(evid or 0), int(strav or 0))
        if index == 1 or index == len(codes):
            report_progress(
                on_progress,
                0.88 + 0.06 * (index / max(len(codes), 1)),
                f"Podklady: počty podle kategorií ({index}/{len(codes)})…",
            )
    return ClosingCounts(
        dining=int(dining or 0),
        registered=int(registered or 0),
        enrolled=enrolled,
        bulk=int(bulk or 0),
        by_category=by_category,
    )


def fetch_closing_podklady(
    config: AppConfig,
    *,
    on_progress: Any = None,
    use_cache: bool = True,
    cache_dir: Path | None = None,
) -> ClosingPodklady:
    """Načte (nebo z cache vezme) kompletní podklady uzávěrky za měsíc.

    Hromadné přihlášky se berou vždy, protože je potřebuje rekapitulace.
    """
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "Chybí balíček psycopg. Nainstalujte závislosti z requirements.txt."
        ) from exc

    year = config.report_date.year
    month = config.report_date.month
    cache_file = cache_path_for(year, month, cache_dir)
    report_progress(on_progress, 0.03, "Podklady: připojuji se k databázi…")
    with psycopg.connect(**config.database) as connection:
        with connection.cursor() as cursor:
            report_progress(on_progress, 0.06, "Podklady: kontroluji otisk dat…")
            fingerprint = fetch_fingerprint(cursor, year, month)
            if use_cache:
                cached = load_cache(cache_file)
                if (
                    cached is not None
                    and cached.fingerprint == fingerprint
                    and cached.period.year == year
                    and cached.period.month == month
                ):
                    report_progress(
                        on_progress,
                        1.0,
                        "Podklady: otisk sedí, používám uložený výpočet.",
                    )
                    return cached
            report_progress(
                on_progress,
                0.10,
                "Podklady: otisk nesedí nebo cache chybí, počítám přihlášky…",
            )
            header = fetch_subject_header(cursor)
            payments = _load_payment_names(cursor)
            report_progress(
                on_progress,
                0.14,
                "Podklady: načítám individuální přihlášky (může to trvat minutu)…",
            )
            individuals = _fetch_rows(cursor, INDIVIDUAL_QUERY, (year, month))
            report_progress(
                on_progress,
                0.72,
                f"Podklady: {len(individuals)} individuálních řádků, načítám hromadné…",
            )
            bulk = _fetch_rows(cursor, BULK_QUERY, (year, month))
            bulk = tuple(row for row in bulk if row.portions > 0)
            report_progress(
                on_progress,
                0.84,
                f"Podklady: hromadných skupin {len(bulk)}, počítám stavy strávníků…",
            )
            counts = _fetch_counts(
                cursor,
                year,
                month,
                tuple(individuals) + tuple(bulk),
                on_progress,
            )

    podklady = ClosingPodklady(
        header=header,
        payments=payments,
        individuals=individuals,
        bulk=bulk,
        counts=counts,
        period=config.report_date,
        fingerprint=fingerprint,
        from_cache=False,
    )
    if use_cache:
        save_cache(cache_file, podklady)
        report_progress(on_progress, 0.98, f"Podklady: uloženy do {cache_file.name}.")
    report_progress(on_progress, 1.0, "Podklady: hotovo.")
    return podklady
