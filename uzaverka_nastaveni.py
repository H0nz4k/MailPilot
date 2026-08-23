"""Nastavení měsíční uzávěrky: které sestavy, jak zabalit, komu poslat."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from stravovaci_sestava import ConfigError

CLOSING_FLAG_PATTERN = re.compile(r"^--(?:u)?zaverka_(\d{2})(\d{4})$")
CLOSING_FLAG_EXAMPLE = "--zaverka_072026"
CLOSING_FLAG_ALIASES = ("--zaverka", "--uzaverka")
CLOSING_CURRENT_FLAGS = ("--zaverka_am", "--uzaverka_am")
CURRENT_CLOSING_PERIOD = "am"
CLOSING_FLAG_HELP = (
    "Období uzávěrky zadejte ve tvaru --zaverka_072026 "
    "(měsíc MM a rok RRRR, například červenec 2026), "
    "nebo --zaverka_am pro aktuální měsíc z Jídelny "
    "(public.parametry / TentoMesic a TentoRok). "
    "Starší tvar --uzaverka_072026 zůstává platný."
)


SESTAVA_FKSP = "fksp"
SESTAVA_ARCH = "stravovaci_arch"
SESTAVA_REKAPITULACE = "rekapitulace"
SUPPORTED_REPORTS = (SESTAVA_FKSP, SESTAVA_ARCH, SESTAVA_REKAPITULACE)
IMPLEMENTED_REPORTS = (SESTAVA_FKSP, SESTAVA_ARCH, SESTAVA_REKAPITULACE)

REPORT_LABELS = {
    SESTAVA_FKSP: "FKSP",
    SESTAVA_ARCH: "Stravovací arch",
    SESTAVA_REKAPITULACE: "Rekapitulace",
}
DEFAULT_CLOSING_OUTPUT = "vystup/uzaverka/{rok}-{mesic}"

ARCH_VARIANTS = (
    "StravovaciArch",
    "StravArch2",
    "StravovaciArchHromadnych",
)
REKAPITULACE_VARIANTS = ("R", "S", "ST")
ATTACHMENT_MODES = ("zip", "samostatne")

CZECH_MONTHS = (
    "leden",
    "únor",
    "březen",
    "duben",
    "květen",
    "červen",
    "červenec",
    "srpen",
    "září",
    "říjen",
    "listopad",
    "prosinec",
)


@dataclass(frozen=True)
class ClosingSettings:
    year: int
    month: int
    reports: tuple[str, ...]
    arch_variant: str
    include_bulk_arch: bool
    recap_variant: str
    attachment_mode: str
    use_all_categories: bool
    send_mail: bool
    output_directory: Path
    recipients: tuple[str, ...]
    mail_body: str | None

    @property
    def period_date(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def month_name(self) -> str:
        return CZECH_MONTHS[self.month - 1]

    @property
    def period_label(self) -> str:
        return f"{self.month_name} {self.year}"

    @property
    def period_stamp(self) -> str:
        return f"{self.year}-{self.month:02d}"

    @property
    def period_token(self) -> str:
        return f"{self.month:02d}{self.year:04d}"

    @property
    def cli_flag(self) -> str:
        return closing_flag(self.year, self.month)


def parse_period(year: object, month: object) -> tuple[int, int]:
    """Ověří rok a měsíc uzávěrky."""
    try:
        parsed_year = int(year)
        parsed_month = int(month)
    except (TypeError, ValueError) as exc:
        raise ConfigError("Rok a měsíc uzávěrky musí být celá čísla.") from exc
    if parsed_year < 2000 or parsed_year > 2100:
        raise ConfigError("Rok uzávěrky musí být v rozsahu 2000–2100.")
    if not 1 <= parsed_month <= 12:
        raise ConfigError("Měsíc uzávěrky musí být v rozsahu 1–12.")
    return parsed_year, parsed_month


def closing_flag(year: int, month: int) -> str:
    parsed_year, parsed_month = parse_period(year, month)
    return f"--zaverka_{parsed_month:02d}{parsed_year:04d}"


def parse_closing_flag(value: object) -> tuple[int, int]:
    """Rozpozná --zaverka_072026 nebo --uzaverka_072026 a vrátí (rok, měsíc)."""
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(CLOSING_FLAG_HELP)
    match = CLOSING_FLAG_PATTERN.fullmatch(value.strip())
    if not match:
        raise ConfigError(CLOSING_FLAG_HELP)
    return parse_period(match.group(2), match.group(1))


def _looks_like_closing_flag(arg: str) -> bool:
    return arg in CLOSING_FLAG_ALIASES or arg.startswith("--zaverka_") or arg.startswith(
        "--uzaverka_"
    )


def consume_closing_flag(
    argv: Sequence[str],
) -> tuple[list[str], tuple[int, int] | str | None]:
    """Vyjme z argv právě jeden přepínač --zaverka_MMRRRR, --zaverka_am nebo alias."""
    remaining: list[str] = []
    period: tuple[int, int] | str | None = None
    for arg in argv:
        if arg in {"--rok", "--mesic"} or arg.startswith("--rok=") or arg.startswith(
            "--mesic="
        ):
            raise ConfigError(
                "Místo --rok a --mesic použijte jeden přepínač "
                f"{CLOSING_FLAG_EXAMPLE} nebo {CLOSING_CURRENT_FLAGS[0]}."
            )
        if arg in CLOSING_CURRENT_FLAGS:
            if period is not None:
                raise ConfigError("Období uzávěrky zadejte jen jednou.")
            period = CURRENT_CLOSING_PERIOD
            continue
        if _looks_like_closing_flag(arg) and CLOSING_FLAG_PATTERN.fullmatch(arg) is None:
            raise ConfigError(CLOSING_FLAG_HELP)
        if CLOSING_FLAG_PATTERN.fullmatch(arg):
            if period is not None:
                raise ConfigError("Období uzávěrky zadejte jen jednou.")
            period = parse_closing_flag(arg)
            continue
        remaining.append(arg)
    return remaining, period


def require_closing_flag(
    argv: Sequence[str],
) -> tuple[list[str], tuple[int, int] | str]:
    remaining, period = consume_closing_flag(argv)
    if period is None:
        raise ConfigError(CLOSING_FLAG_HELP)
    return remaining, period


def czech_month_name(month: int) -> str:
    if not 1 <= month <= 12:
        raise ConfigError("Měsíc uzávěrky musí být v rozsahu 1–12.")
    return CZECH_MONTHS[month - 1]


def peek_closing_ui(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Vrátí hodnoty pro záložku tiskových sestav, i ze staršího configu."""
    block = raw.get("uzaverka") if isinstance(raw, dict) else None
    if not isinstance(block, dict):
        block = {}
    reports_raw = block.get("sestavy", list(IMPLEMENTED_REPORTS))
    reports: list[str] = []
    if isinstance(reports_raw, list):
        for item in reports_raw:
            if item in SUPPORTED_REPORTS and item not in reports:
                reports.append(str(item))
    if not reports:
        reports = list(IMPLEMENTED_REPORTS)
    output = block.get("vystup", DEFAULT_CLOSING_OUTPUT)
    if not isinstance(output, str) or not output.strip():
        output = DEFAULT_CLOSING_OUTPUT
    return {
        "sestavy": reports,
        "vystup": output.strip(),
        "zip": block.get("prilohy", "zip") != "samostatne",
        "odeslat_mail": block.get("odeslat_mail") is True,
    }


def apply_closing_ui(
    block: dict[str, Any],
    *,
    reports: Sequence[str],
    output: str,
    pack_zip: bool,
    send_mail: bool,
) -> dict[str, Any]:
    """Zapíše volby z UI do bloku uzaverka a zachová ostatní klíče."""
    updated = dict(block)
    selected = [name for name in SUPPORTED_REPORTS if name in reports]
    if not selected:
        raise ConfigError("Vyberte alespoň jednu tiskovou sestavu uzávěrky.")
    path = output.strip()
    if not path:
        raise ConfigError("Zadejte složku, kam se mají tisky uzávěrky ukládat.")
    try:
        path.format(rok=2026, mesic="07")
    except (KeyError, ValueError) as exc:
        raise ConfigError(
            "Cesta smí používat pouze zástupné hodnoty {rok} a {mesic}."
        ) from exc
    updated["sestavy"] = selected
    updated["vystup"] = path
    updated["prilohy"] = "zip" if pack_zip else "samostatne"
    updated["odeslat_mail"] = bool(send_mail)
    return updated


def parse_closing_settings(
    raw: dict[str, Any],
    *,
    year: int,
    month: int,
    config_directory: Path,
) -> ClosingSettings:
    """Načte blok uzaverka; chybějící blok použije bezpečné výchozí hodnoty."""
    block = raw.get("uzaverka", {})
    if block is None:
        block = {}
    if not isinstance(block, dict):
        raise ConfigError("'uzaverka' musí být JSON objekt.")

    reports = block.get("sestavy", [SESTAVA_FKSP])
    if not isinstance(reports, list) or not reports:
        raise ConfigError("'uzaverka.sestavy' musí být neprázdné JSON pole.")
    normalized_reports: list[str] = []
    seen: set[str] = set()
    for item in reports:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError("Každá položka v 'uzaverka.sestavy' musí být neprázdný text.")
        name = item.strip()
        if name not in SUPPORTED_REPORTS:
            raise ConfigError(
                "'uzaverka.sestavy' smí obsahovat jen: "
                + ", ".join(SUPPORTED_REPORTS)
            )
        if name not in seen:
            seen.add(name)
            normalized_reports.append(name)

    arch_variant = block.get("stravovaci_arch", "StravovaciArch")
    if not isinstance(arch_variant, str) or arch_variant not in ARCH_VARIANTS:
        raise ConfigError(
            "'uzaverka.stravovaci_arch' musí být jedna z hodnot: "
            + ", ".join(ARCH_VARIANTS)
        )

    include_bulk_arch = block.get("stravovaci_arch_hromadne", True)
    if not isinstance(include_bulk_arch, bool):
        raise ConfigError(
            "'uzaverka.stravovaci_arch_hromadne' musí být true nebo false."
        )

    recap_variant = block.get("rekapitulace", "R")
    if not isinstance(recap_variant, str) or recap_variant not in REKAPITULACE_VARIANTS:
        raise ConfigError(
            "'uzaverka.rekapitulace' musí být jedna z hodnot: "
            + ", ".join(REKAPITULACE_VARIANTS)
        )

    attachment_mode = block.get("prilohy", "zip")
    if not isinstance(attachment_mode, str) or attachment_mode not in ATTACHMENT_MODES:
        raise ConfigError("'uzaverka.prilohy' musí být 'zip' nebo 'samostatne'.")

    use_all_categories = block.get("vsechny_kategorie", True)
    if not isinstance(use_all_categories, bool):
        raise ConfigError("'uzaverka.vsechny_kategorie' musí být true nebo false.")

    send_mail = block.get("odeslat_mail", False)
    if not isinstance(send_mail, bool):
        raise ConfigError("'uzaverka.odeslat_mail' musí být true nebo false.")

    output = block.get("vystup", "vystup/uzaverka/{rok}-{mesic}")
    if not isinstance(output, str) or not output.strip():
        raise ConfigError("'uzaverka.vystup' musí být neprázdná cesta ke složce.")
    try:
        output = output.strip().format(rok=year, mesic=f"{month:02d}")
    except (KeyError, ValueError) as exc:
        raise ConfigError(
            "'uzaverka.vystup' smí používat pouze zástupné hodnoty {rok} a {mesic}."
        ) from exc
    output_directory = Path(output)
    if not output_directory.is_absolute():
        output_directory = config_directory / output_directory

    recipients_raw = block.get("mail_prijemci")
    recipients: tuple[str, ...]
    if recipients_raw is None:
        recipients = ()
    elif isinstance(recipients_raw, list):
        from mail_service import normalize_recipients

        recipients = normalize_recipients(recipients_raw, allow_empty=True)
    else:
        raise ConfigError("'uzaverka.mail_prijemci' musí být JSON pole adres.")

    mail_body = block.get("mail_text")
    if mail_body is not None and not isinstance(mail_body, str):
        raise ConfigError("'uzaverka.mail_text' musí být text.")

    return ClosingSettings(
        year=year,
        month=month,
        reports=tuple(normalized_reports),
        arch_variant=arch_variant,
        include_bulk_arch=include_bulk_arch,
        recap_variant=recap_variant,
        attachment_mode=attachment_mode,
        use_all_categories=use_all_categories,
        send_mail=send_mail,
        output_directory=output_directory,
        recipients=recipients,
        mail_body=mail_body,
    )
