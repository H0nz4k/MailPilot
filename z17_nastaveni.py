"""Nastavení ročního podkladu k výkazu Z 17-01 (stav k 31. 10.)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from stravovaci_sestava import ConfigError


Z17_FLAG_PATTERN = re.compile(r"^--z17_(\d{4})$")
Z17_FLAG_EXAMPLE = "--z17_2026"
Z17_FLAG_HELP = (
    "Podklad Z 17-01 zadejte ve tvaru --z17_2026 "
    "(rok RRRR, stav k 31. 10. daného roku)."
)

PUPIL_ROWS = (
    "0102",
    "0103",
    "0104",
    "0104a",
    "0105",
    "0105a",
    "0106",
    "0107",
    "0108",
    "0110",
    "0111",
    "0112",
)
STAFF_ROWS = ("0114", "0114a")
OTHER_ROW = "0113"
MAPPABLE_ROWS = PUPIL_ROWS + STAFF_ROWS + (OTHER_ROW,)

DEFAULT_SUPPLEMENT_IN_SCOPE = ("0102", "0103", "0112")
DEFAULT_Z17_OUTPUT = "vystup/z17/{rok}"

ROW_LABELS = {
    "0101": "Děti, žáci a studenti celkem",
    "0101a": "z toho dietní stravování",
    "0102": "Děti v mateřské škole (vč. odkladů)",
    "0103": "Přípravné třídy / přípravný stupeň",
    "0104": "Žáci 1. stupně ZŠ (7–10 let)",
    "0104a": "z toho 10letí a starší ve skupině 11–14",
    "0105": "Žáci 2. stupně ZŠ (11–14 let)",
    "0105a": "z toho 14letí a starší ve skupině 15+",
    "0106": "Žáci nižšího stupně gymnázia",
    "0107": "Žáci 1.–4. ročníku 8leté konzervatoře",
    "0108": "Žáci středních škol (vč. vyššího stupně gymnázia)",
    "0110": "Žáci konzervatoře (vyšší ročníky)",
    "0111": "Studenti vyšších odborných škol",
    "0112": "Děti v ústavní / ochranné výchově bez školy",
    "0113": "Ostatní pravidelně stravovaní",
    "0114": "z toho pracovníci škol a školských zařízení",
    "0114a": "z toho pracovníci vykazujícího subjektu",
    "0115": "Pravidelně stravovaní celkem (0101 + 0113)",
}

MEAL_ROW_LABELS = {
    "0301": "Obědy",
    "0302": "Večeře",
    "0303": "Snídaně",
    "0304": "Přesnídávky",
    "0305": "Svačiny",
    "0306": "Druhé večeře",
    "0309": "Ostatní / nerozpoznaný typ jídla",
}


@dataclass(frozen=True)
class Z17Settings:
    year: int
    category_rows: dict[str, tuple[str, ...]]
    supplement_in_scope: tuple[str, ...]
    output_directory: Path
    use_all_categories: bool = True
    allowed_categories: tuple[str, ...] = ()

    @property
    def snapshot_date_label(self) -> str:
        return f"31. 10. {self.year}"

    @property
    def school_year_label(self) -> str:
        start_year, end_year = school_year_bounds(self.year)
        return f"{start_year}/{end_year}"

    @property
    def period_stamp(self) -> str:
        return str(self.year)


def school_year_bounds(report_year: int) -> tuple[int, int]:
    """Školní rok pro sl. 2 a 4 oddílu III: 1. 9. (Y-1) až 31. 8. Y."""
    return report_year - 1, report_year


def school_year_periods(report_year: int) -> tuple[tuple[int, int], ...]:
    start_year, end_year = school_year_bounds(report_year)
    months = [(start_year, month) for month in range(9, 13)]
    months.extend((end_year, month) for month in range(1, 9))
    return tuple(months)


def period_keys(periods: Sequence[tuple[int, int]]) -> tuple[int, ...]:
    return tuple(year * 100 + month for year, month in periods)


def parse_z17_year(value: object) -> int:
    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError("Rok podkladu Z 17-01 musí být celé číslo.") from exc
    if year < 2000 or year > 2100:
        raise ConfigError("Rok podkladu Z 17-01 musí být v rozsahu 2000–2100.")
    return year


def z17_flag(year: int) -> str:
    return f"--z17_{parse_z17_year(year)}"


def parse_z17_flag(value: object) -> int:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(Z17_FLAG_HELP)
    match = Z17_FLAG_PATTERN.fullmatch(value.strip())
    if not match:
        raise ConfigError(Z17_FLAG_HELP)
    return parse_z17_year(match.group(1))


def consume_z17_flag(argv: Sequence[str]) -> tuple[list[str], int | None]:
    remaining: list[str] = []
    year: int | None = None
    for arg in argv:
        if arg == "--z17" or (
            arg.startswith("--z17_") and Z17_FLAG_PATTERN.fullmatch(arg) is None
        ):
            raise ConfigError(Z17_FLAG_HELP)
        if Z17_FLAG_PATTERN.fullmatch(arg):
            if year is not None:
                raise ConfigError("Rok podkladu Z 17-01 zadejte jen jednou.")
            year = parse_z17_flag(arg)
            continue
        remaining.append(arg)
    return remaining, year


def require_z17_flag(argv: Sequence[str]) -> tuple[list[str], int]:
    remaining, year = consume_z17_flag(argv)
    if year is None:
        raise ConfigError(Z17_FLAG_HELP)
    return remaining, year


def _parse_code_list(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigError(f"'{label}' musí být JSON pole označení kategorií.")
    codes: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"Položky v '{label}' musí být neprázdný text.")
        code = item.strip()
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return tuple(codes)


def peek_z17_ui(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Hodnoty pro záložku Special, i ze staršího configu."""
    block = raw.get("z17") if isinstance(raw, dict) else None
    if not isinstance(block, dict):
        block = {}
    output = block.get("vystup", DEFAULT_Z17_OUTPUT)
    if not isinstance(output, str) or not output.strip():
        output = DEFAULT_Z17_OUTPUT
    use_all = block.get("vsechny_kategorie", True)
    if not isinstance(use_all, bool):
        use_all = True
    categories: list[str] = []
    source = block.get("povolene_kategorie", [])
    if isinstance(source, list):
        for item in source:
            code = str(item or "").strip()
            if code and code not in categories:
                categories.append(code)
    try:
        year = parse_z17_year(block.get("rok"))
    except ConfigError:
        year = date.today().year
    return {
        "vystup": output.strip(),
        "vsechny_kategorie": use_all,
        "povolene_kategorie": categories,
        "rok": year,
    }


def apply_z17_ui(
    block: dict[str, Any],
    *,
    output: str,
    use_all_categories: bool = True,
    categories: Sequence[str] | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """Zapíše cestu a výběr kategorií z UI a zachová mapování."""
    updated = dict(block)
    path = output.strip()
    if not path:
        raise ConfigError("Zadejte složku, kam se má podklad Z 17-01 ukládat.")
    try:
        path.format(rok=2026)
    except (KeyError, ValueError) as exc:
        raise ConfigError("Cesta smí používat pouze zástupnou hodnotu {rok}.") from exc
    selected = _parse_code_list(
        list(categories or []),
        label="z17.povolene_kategorie",
    )
    updated["vystup"] = path
    updated["vsechny_kategorie"] = bool(use_all_categories)
    updated["povolene_kategorie"] = list(selected)
    if year is not None:
        updated["rok"] = parse_z17_year(year)
    return updated


def parse_z17_settings(
    raw: dict[str, Any],
    *,
    year: int,
    config_directory: Path,
) -> Z17Settings:
    block = raw.get("z17", {})
    if block is None:
        block = {}
    if not isinstance(block, dict):
        raise ConfigError("'z17' musí být JSON objekt.")

    mapping_raw = block.get("mapovani_kategorii", {})
    if mapping_raw is None:
        mapping_raw = {}
    if not isinstance(mapping_raw, dict):
        raise ConfigError("'z17.mapovani_kategorii' musí být JSON objekt.")
    category_rows: dict[str, tuple[str, ...]] = {}
    for row, codes in mapping_raw.items():
        name = str(row).strip()
        if name not in MAPPABLE_ROWS:
            raise ConfigError(
                f"Neznámý řádek Z 17-01 {name!r}. Povolené: "
                + ", ".join(MAPPABLE_ROWS)
            )
        category_rows[name] = _parse_code_list(
            codes, label=f"z17.mapovani_kategorii.{name}"
        )

    supplement_raw = block.get(
        "doplnkova_v_ramci_vyhlasky", list(DEFAULT_SUPPLEMENT_IN_SCOPE)
    )
    if not isinstance(supplement_raw, list):
        raise ConfigError("'z17.doplnkova_v_ramci_vyhlasky' musí být JSON pole.")
    supplement: list[str] = []
    for item in supplement_raw:
        if not isinstance(item, str) or item.strip() not in MAPPABLE_ROWS:
            raise ConfigError(
                "'z17.doplnkova_v_ramci_vyhlasky' smí obsahovat jen řádky výkazu."
            )
        code = item.strip()
        if code not in supplement:
            supplement.append(code)

    output = block.get("vystup", "vystup/z17/{rok}")
    if not isinstance(output, str) or not output.strip():
        raise ConfigError("'z17.vystup' musí být neprázdná cesta ke složce.")
    try:
        output = output.strip().format(rok=year)
    except (KeyError, ValueError) as exc:
        raise ConfigError("'z17.vystup' smí používat pouze zástupnou hodnotu {rok}.") from exc
    output_directory = Path(output)
    if not output_directory.is_absolute():
        output_directory = config_directory / output_directory

    use_all = block.get("vsechny_kategorie", True)
    if not isinstance(use_all, bool):
        raise ConfigError("'z17.vsechny_kategorie' musí být true nebo false.")
    allowed: tuple[str, ...] = ()
    if not use_all:
        allowed = _parse_code_list(
            block.get("povolene_kategorie", []),
            label="z17.povolene_kategorie",
        )
        if not allowed:
            raise ConfigError(
                "'z17.povolene_kategorie' musí obsahovat alespoň jednu kategorii, "
                "nebo zapněte z17.vsechny_kategorie."
            )

    return Z17Settings(
        year=parse_z17_year(year),
        category_rows=category_rows,
        supplement_in_scope=tuple(supplement),
        output_directory=output_directory,
        use_all_categories=use_all,
        allowed_categories=allowed,
    )


def reverse_category_map(category_rows: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    """Označení kategorie → řádky výkazu, ve kterých je uvedena."""
    result: dict[str, list[str]] = {}
    for row, codes in category_rows.items():
        for code in codes:
            result.setdefault(code, []).append(row)
    return {code: tuple(rows) for code, rows in result.items()}
