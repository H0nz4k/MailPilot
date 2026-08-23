"""Měsíční uzávěrka pro libovolnou prezentační vrstvu.

Obal nad ``uzaverka.py``: čte a zapisuje blok ``uzaverka`` v konfiguraci
a spouští existující běh uzávěrky. Business logika zůstává v původních
modulech, tady je jen převod na hodnoty vhodné pro formulář.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Callable, Sequence

from mail_service import normalize_recipients
from uzaverka import run_monthly_closing
from uzaverka_nastaveni import (
    ARCH_VARIANTS,
    ATTACHMENT_MODES,
    CURRENT_CLOSING_PERIOD,
    DEFAULT_CLOSING_OUTPUT,
    IMPLEMENTED_REPORTS,
    REKAPITULACE_VARIANTS,
    SESTAVA_ARCH,
    SESTAVA_FKSP,
    SESTAVA_REKAPITULACE,
    SUPPORTED_REPORTS,
    closing_flag,
    czech_month_name,
)
from stravovaci_sestava import ConfigError


REPORT_LABELS = {
    SESTAVA_FKSP: "FKSP",
    SESTAVA_ARCH: "Stravovací arch",
    SESTAVA_REKAPITULACE: "Rekapitulace",
}
REPORT_HINTS = {
    SESTAVA_FKSP: "Podklad pro FKSP za zvolený měsíc.",
    SESTAVA_ARCH: "Stravovací arch se seznamem strávníků a dnů.",
    SESTAVA_REKAPITULACE: "Rekapitulace plateb a odebraných jídel.",
}
ARCH_LABELS = {
    "StravovaciArch": "Stravovací arch",
    "StravArch2": "Stravovací arch 2",
    "StravovaciArchHromadnych": "Arch hromadných strávníků",
}
RECAP_LABELS = {
    "R": "Rekapitulace (R)",
    "S": "Sestava (S)",
    "ST": "Stravné (ST)",
}
ATTACHMENT_LABELS = {
    "zip": "Zabalit do jednoho ZIP",
    "samostatne": "Poslat samostatná PDF",
}

MONTH_NAMES = tuple(czech_month_name(month) for month in range(1, 13))


@dataclass(frozen=True)
class ClosingForm:
    """Hodnoty, které obrazovka uzávěrky nabízí a ukládá."""

    year: int
    month: int
    use_current_period: bool = False
    reports: tuple[str, ...] = IMPLEMENTED_REPORTS
    output: str = DEFAULT_CLOSING_OUTPUT
    pack_zip: bool = True
    send_mail: bool = False
    arch_variant: str = "StravovaciArch"
    include_bulk_arch: bool = True
    recap_variant: str = "R"
    use_all_categories: bool = True
    recipients: tuple[str, ...] = ()

    @property
    def period_label(self) -> str:
        return f"{czech_month_name(self.month)} {self.year}"

    @property
    def cli_flag(self) -> str:
        if self.use_current_period:
            return f"--zaverka_{CURRENT_CLOSING_PERIOD}"
        return closing_flag(self.year, self.month)

    def with_period(self, year: int, month: int) -> "ClosingForm":
        return replace(self, year=int(year), month=int(month))


@dataclass(frozen=True)
class ClosingRun:
    """Výsledek jednoho běhu uzávěrky."""

    status: str
    year: int
    month: int
    files: tuple[Path, ...]
    attachments: tuple[Path, ...]
    recipients: tuple[str, ...]
    detail: str

    @property
    def sent(self) -> bool:
        return self.status == "sent"

    @property
    def zip_file(self) -> Path | None:
        for path in self.attachments:
            if path.suffix.casefold() == ".zip":
                return path
        return None

    @property
    def directory(self) -> Path | None:
        return self.files[0].parent if self.files else None

    def summary(self) -> str:
        count = len(self.files)
        label = "sestava" if count == 1 else ("sestavy" if count < 5 else "sestav")
        text = f"{count} {label}"
        if self.zip_file is not None:
            text += " · ZIP"
        if self.sent:
            text += f" · odesláno {len(self.recipients)} příjemcům"
        return text


def previous_period(today: date | None = None) -> tuple[int, int]:
    """Uzávěrka se obvykle dělá za minulý měsíc."""
    reference = today or date.today()
    year = reference.year
    month = reference.month - 1
    if month == 0:
        month = 12
        year -= 1
    return year, month


def _clean_text(value: object, fallback: str, allowed: Sequence[str]) -> str:
    text = str(value or "").strip()
    return text if text in allowed else fallback


def peek_closing_form(
    raw: dict[str, Any] | None, *, today: date | None = None
) -> ClosingForm:
    """Načte blok ``uzaverka``; starší config zůstává čitelný."""
    block = raw.get("uzaverka") if isinstance(raw, dict) else None
    if not isinstance(block, dict):
        block = {}
    reports: list[str] = []
    raw_reports = block.get("sestavy")
    if isinstance(raw_reports, list):
        for item in raw_reports:
            name = str(item).strip()
            if name in SUPPORTED_REPORTS and name not in reports:
                reports.append(name)
    if not reports:
        reports = list(IMPLEMENTED_REPORTS)
    output = str(block.get("vystup") or "").strip() or DEFAULT_CLOSING_OUTPUT
    attachment = _clean_text(block.get("prilohy"), "zip", ATTACHMENT_MODES)
    recipients = block.get("mail_prijemci")
    if isinstance(recipients, list):
        try:
            clean_recipients = tuple(normalize_recipients(recipients))
        except ConfigError:
            clean_recipients = tuple(
                str(item).strip() for item in recipients if str(item).strip()
            )
    else:
        clean_recipients = ()
    year, month = previous_period(today)
    return ClosingForm(
        year=year,
        month=month,
        use_current_period=False,
        reports=tuple(reports),
        output=output,
        pack_zip=attachment != "samostatne",
        send_mail=block.get("odeslat_mail") is True,
        arch_variant=_clean_text(
            block.get("stravovaci_arch"), "StravovaciArch", ARCH_VARIANTS
        ),
        include_bulk_arch=block.get("stravovaci_arch_hromadne", True) is not False,
        recap_variant=_clean_text(
            block.get("rekapitulace"), "R", REKAPITULACE_VARIANTS
        ),
        use_all_categories=block.get("vsechny_kategorie", True) is not False,
        recipients=clean_recipients,
    )


def validate_output(output: str) -> str:
    """Ověří cestu i zástupné hodnoty a vrátí ořezaný text."""
    path = str(output or "").strip()
    if not path:
        raise ConfigError("Zadejte složku, kam se mají tisky uzávěrky ukládat.")
    try:
        path.format(rok=2026, mesic="07")
    except (KeyError, ValueError, IndexError) as exc:
        raise ConfigError(
            "Cesta smí používat pouze zástupné hodnoty {rok} a {mesic}."
        ) from exc
    return path


def apply_closing_form(
    raw: dict[str, Any], form: ClosingForm
) -> dict[str, Any]:
    """Zapíše volby uzávěrky a ostatní klíče nechá beze změny."""
    block = raw.get("uzaverka")
    block = dict(block) if isinstance(block, dict) else {}
    selected = [name for name in SUPPORTED_REPORTS if name in form.reports]
    if not selected:
        raise ConfigError("Vyberte alespoň jednu tiskovou sestavu uzávěrky.")
    block["sestavy"] = selected
    block["vystup"] = validate_output(form.output)
    block["prilohy"] = "zip" if form.pack_zip else "samostatne"
    block["odeslat_mail"] = bool(form.send_mail)
    block["stravovaci_arch"] = _clean_text(
        form.arch_variant, "StravovaciArch", ARCH_VARIANTS
    )
    block["stravovaci_arch_hromadne"] = bool(form.include_bulk_arch)
    block["rekapitulace"] = _clean_text(form.recap_variant, "R", REKAPITULACE_VARIANTS)
    block["vsechny_kategorie"] = bool(form.use_all_categories)
    return dict(raw, uzaverka=block)


def resolve_output(
    output: str, *, year: int, month: int, config_directory: Path
) -> Path:
    """Cesta se zástupnými hodnotami převedená na skutečnou složku."""
    path = Path(validate_output(output).format(rok=year, mesic=f"{month:02d}"))
    if not path.is_absolute():
        path = config_directory / path
    return path


def existing_outputs(directory: Path) -> tuple[Path, ...]:
    """Soubory poslední uzávěrky ve výstupní složce, nejnovější první."""
    try:
        files = [
            item
            for item in directory.iterdir()
            if item.is_file() and item.suffix.casefold() in {".pdf", ".zip"}
        ]
    except OSError:
        return ()
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return tuple(files)


def run_closing(
    config_path: Path,
    *,
    year: int | None = None,
    month: int | None = None,
    current_month: bool = False,
    on_progress: Callable[[int, str], None] | None = None,
) -> ClosingRun:
    """Spustí existující měsíční uzávěrku a převede výsledek na dataclass."""
    result = run_monthly_closing(
        config_path,
        year=year,
        month=month,
        current_month=current_month,
        on_progress=on_progress,
    )
    return ClosingRun(
        status=str(result.get("status", "")),
        year=int(result.get("year", year or 0)),
        month=int(result.get("month", month or 0)),
        files=tuple(Path(item) for item in result.get("files", ())),
        attachments=tuple(Path(item) for item in result.get("attachments", ())),
        recipients=tuple(str(item) for item in result.get("recipients", ())),
        detail=str(result.get("detail", "")),
    )
