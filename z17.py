#!/usr/bin/env python3
"""Roční podklad k výkazu Z 17-01 ze stavů Jídelny."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from runtime_paths import application_directory
from stravovaci_sestava import ConfigError, load_config
from uzaverka import emit_progress, write_log
from z17_nastaveni import (
    Z17_FLAG_HELP,
    parse_z17_settings,
    require_z17_flag,
    z17_flag,
)
from z17_sestava import export_z17_pdf


ProgressFn = Callable[[int, str], None]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    remaining, year = require_z17_flag(raw_argv)
    parser = argparse.ArgumentParser(
        description=(
            "Vytvoří podklad PDF k výkazu Z 17-01. "
            f"Rok je povinný, například {z17_flag(2026)}."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=application_directory() / "config.json",
        help="cesta ke config.json",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=application_directory() / "logy" / "z17.log",
        help="cesta k provoznímu logu",
    )
    args = parser.parse_args(remaining)
    args.rok = year
    args.z17_flag = z17_flag(year)
    return args


def read_saved_settings(path: Path) -> dict[str, Any]:
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
    return raw


def run_z17_report(
    config_path: Path,
    *,
    year: int,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    emit_progress(on_progress, 0, "Spouštím podklad Z 17-01…")
    raw = read_saved_settings(config_path)
    settings = parse_z17_settings(raw, year=year, config_directory=config_path.parent)
    emit_progress(
        on_progress,
        4,
        f"Stav k 31. 10. {year}, školní rok {settings.school_year_label}…",
    )
    config = load_config(config_path, date_override=f"31.10.{year}")
    emit_progress(on_progress, 8, "Načítám přihlášky a skládám sestavu…")

    def bound(fraction: float, message: str) -> None:
        percent = int(round(8 + 90 * max(0.0, min(1.0, fraction))))
        emit_progress(on_progress, percent, message)

    created = export_z17_pdf(config, settings, on_progress=bound)
    emit_progress(on_progress, 100, f"Hotovo: {created.name}")
    return {
        "status": "exported",
        "year": year,
        "files": [created],
        "detail": f"Podklad Z 17-01 za rok {year}.",
    }


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except ConfigError as exc:
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 2
    write_log(args.log, "START", f"Podklad Z 17-01 {args.z17_flag}")

    def on_progress(percent: int, message: str) -> None:
        write_log(args.log, "PRUBEH", f"{percent}% {message}")
        print(f"[{percent:3d} %] {message}", flush=True)

    try:
        result = run_z17_report(args.config, year=args.rok, on_progress=on_progress)
    except (ConfigError, RuntimeError) as exc:
        write_log(args.log, "ERROR", str(exc))
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        write_log(args.log, "ERROR", f"Neočekávaná chyba: {exc}")
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 1

    files = ", ".join(str(path) for path in result["files"])
    message = f"NEODESLÁNO: {result['year']}; soubory: {files}; {result['detail']}"
    write_log(args.log, "OK", message)
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
