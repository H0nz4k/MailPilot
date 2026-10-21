#!/usr/bin/env python3
"""Read-only daily-count diagnostic; never prints DB credentials or diner names."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def default_config(root: Path) -> Path:
    for relative in ("dist-web/DataShip/config.json", "dist-web/MailPilot-Web/config.json", "config.json"):
        candidate = root / relative
        if candidate.is_file():
            return candidate
    raise ValueError("Nenalezen config.json. Předejte --config cesta/config.json.")


def inspect_counts(config_path: Path, day: date) -> dict:
    import psycopg
    from psycopg import sql
    from stravovaci_sestava import load_config

    config = load_config(config_path, date_override=day.strftime("%d.%m.%Y"))
    day_key = f"d{day.day:02d}"
    with psycopg.connect(**config.database) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '20s'")
            cursor.execute("""
                SELECT column_name, data_type FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'prihlasn'
                ORDER BY ordinal_position
            """)
            columns = [{"name": name, "type": kind} for name, kind in cursor.fetchall()
                       if not (len(name) == 3 and name.startswith("d") and name[1:].isdigit()) or name == day_key]
            cursor.execute(sql.SQL("""
                SELECT BTRIM(p.typsluzby), COUNT(*)::integer
                FROM public.prihlas p JOIN public.stravnik s ON s.evidcislo = p.stravnik
                WHERE p.rok = %s AND p.mesic = %s
                  AND COALESCE(s.deleted, false) = false
                  AND p.{day_column} ~ '^[1-9]$'
                GROUP BY BTRIM(p.typsluzby) ORDER BY 1
            """).format(day_column=sql.Identifier(day_key)), (day.year, day.month))
            individual = [{"typ": typ, "porce": count} for typ, count in cursor.fetchall()]
            cursor.execute("""
                SELECT BTRIM(p.typsluzby),
                       COALESCE(NULLIF(BTRIM(p.kategorie), ''), BTRIM(s.kategorie)),
                       to_jsonb(p) -> %s,
                       (SELECT jsonb_object_agg(e.key, e.value)
                        FROM jsonb_each(to_jsonb(p)) AS e
                        WHERE e.key ILIKE '%%menu%%'),
                       COALESCE(public.pocetprihlashromadnehostr(p.id, %s, %s), 0)
                FROM public.prihlasn p JOIN public.stravnik s ON s.evidcislo = p.stravnik
                WHERE p.rok = %s AND p.mesic = %s
                  AND COALESCE(public.pocetprihlashromadnehostr(p.id, %s, %s), 0) > 0
                ORDER BY 1, 2
                LIMIT 50
            """, (day_key, day.day, day.day, day.year, day.month, day.day, day.day))
            bulk = [{"typ": typ, "kategorie": code, day_key: value,
                     "pole_menu": menu_fields, "porce_funkce": count}
                    for typ, code, value, menu_fields, count in cursor.fetchall()]
            cursor.execute("""
                SELECT pg_get_functiondef(p.oid)
                FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public' AND p.proname = 'pocetprihlashromadnehostr'
            """)
            functions = [row[0] for row in cursor.fetchall()]
    return {"datum": day.isoformat(), "prihlas_bezne": individual,
            "prihlasn_sloupce": columns, "prihlasn_vzorek": bulk,
            "definice_pocetprihlashromadnehostr": functions}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--date", default=date.today().strftime("%d.%m.%Y"))
    args = parser.parse_args()
    try:
        day = datetime.strptime(args.date, "%d.%m.%Y").date()
        config = args.config or default_config(Path(__file__).resolve().parents[1])
        print(json.dumps(inspect_counts(config, day), ensure_ascii=False, indent=2, default=str))
    except Exception as exc:
        # Do not stringify connection exceptions: they can contain host/user details.
        print(f"Diagnostika se nepodařila ({type(exc).__name__}). Ověřte config a uložené DB heslo.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
