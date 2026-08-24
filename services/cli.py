"""Bezobslužné režimy MailPilotu nezávislé na grafickém rozhraní.

Stejné přepínače jako v předchozí verzi, aby beze změny fungovaly dávkové
soubory, plánovač úloh Windows i volání z Jídelny. Rozhraní (Qt) sem jen
předá argumenty; veškerá práce běží ve stejných modulech jako v okně.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from automaticky_export import main as automatic_export_main
from runtime_paths import application_directory
from services.scheduler_runtime import run_scheduler_loop
from stravovaci_sestava import ConfigError
from uzaverka import main as monthly_closing_main
from uzaverka_nastaveni import (
    CLOSING_FLAG_HELP,
    CURRENT_CLOSING_PERIOD,
    closing_flag,
    consume_closing_flag,
)
from z17 import main as z17_main
from z17_nastaveni import Z17_FLAG_HELP, consume_z17_flag, z17_flag


HEADLESS_FLAGS = ("--automatic", "--poctyemailem")


@dataclass(frozen=True)
class CliRequest:
    """Rozpoznaný požadavek na běh bez okna."""

    config: Path
    log: Path
    automatic: bool = False
    closing_period: tuple[int, int] | None = None
    closing_current: bool = False
    z17_year: int | None = None
    scheduler: bool = False
    scheduler_once: bool = False

    @property
    def headless(self) -> bool:
        return bool(
            self.automatic
            or self.closing_current
            or self.closing_period is not None
            or self.z17_year is not None
            or self.scheduler
            or self.scheduler_once
        )


def default_log() -> Path:
    return application_directory() / "logy" / "automaticky_export.log"


def parse_cli(argv: Sequence[str] | None = None) -> tuple[CliRequest, list[str]]:
    """Vytáhne bezobslužné přepínače a vrátí zbytek pro grafické rozhraní."""
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    remaining, period = consume_closing_flag(raw_argv)
    remaining, z17_year = consume_z17_flag(remaining)

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--log", type=Path, default=None)
    parser.add_argument("--automatic", action="store_true")
    parser.add_argument("--poctyemailem", action="store_true")
    parser.add_argument("--scheduler", action="store_true")
    parser.add_argument("--scheduler-once", action="store_true")
    known, rest = parser.parse_known_args(remaining)

    config = known.config or application_directory() / "config.json"
    request = CliRequest(
        config=Path(config),
        log=Path(known.log) if known.log else default_log(),
        automatic=bool(known.automatic or known.poctyemailem),
        closing_period=period if isinstance(period, tuple) else None,
        closing_current=period == CURRENT_CLOSING_PERIOD,
        z17_year=z17_year,
        scheduler=bool(known.scheduler),
        scheduler_once=bool(known.scheduler_once),
    )
    if known.config is not None:
        rest = [*rest, "--config", str(config)]
    return request, rest


def _conflict(request: CliRequest) -> str:
    closing = request.closing_current or request.closing_period is not None
    if request.automatic and closing:
        return "Zvolte jen --poctyemailem / --automatic, nebo jen přepínač uzávěrky."
    if request.automatic and request.z17_year is not None:
        return "Zvolte jen --poctyemailem / --automatic, nebo jen přepínač Z 17-01."
    if closing and request.z17_year is not None:
        return "Zvolte jen přepínač uzávěrky, nebo jen přepínač Z 17-01."
    if request.scheduler or request.scheduler_once:
        if request.automatic or closing or request.z17_year is not None:
            return "Scheduler nelze kombinovat s ostatními bezobslužnými přepínači."
    return ""


def run_headless(request: CliRequest) -> int:
    """Spustí zvolený režim; návratový kód je vhodný pro plánovač úloh."""
    problem = _conflict(request)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    arguments = ["--config", str(request.config), "--log", str(request.log)]
    try:
        if request.automatic:
            return automatic_export_main(arguments)
        if request.closing_current:
            return monthly_closing_main(["--zaverka_am", *arguments])
        if request.closing_period is not None:
            year, month = request.closing_period
            return monthly_closing_main([closing_flag(year, month), *arguments])
        if request.z17_year is not None:
            return z17_main([z17_flag(request.z17_year), *arguments])
        if request.scheduler or request.scheduler_once:
            return run_scheduler_loop(
                request.config,
                once=bool(request.scheduler_once),
            )
    except ConfigError as exc:
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 2
    print(CLOSING_FLAG_HELP, file=sys.stderr)
    print(Z17_FLAG_HELP, file=sys.stderr)
    return 2
