"""Speciál · Z 17-01 pro libovolnou prezentační vrstvu.

Obal nad ``z17.py`` a ``z17_nastaveni.py``: převádí blok ``z17`` na
hodnoty formuláře a spouští existující generování podkladu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Sequence

from z17 import run_z17_report
from z17_nastaveni import (
    DEFAULT_SUPPLEMENT_IN_SCOPE,
    DEFAULT_Z17_OUTPUT,
    MAPPABLE_ROWS,
    ROW_LABELS,
    Z17_FLAG_EXAMPLE,
    apply_z17_ui,
    parse_z17_year,
    peek_z17_ui,
    school_year_bounds,
    z17_flag,
)
from stravovaci_sestava import ConfigError


MIN_YEAR = 2000
MAX_YEAR = 2100
REPORT_PREFIX = "Z17-01_podklad_"


@dataclass(frozen=True)
class SpecialForm:
    """Hodnoty obrazovky Speciál · Z 17-01."""

    year: int
    output: str = DEFAULT_Z17_OUTPUT
    use_all_categories: bool = True
    categories: tuple[str, ...] = ()

    @property
    def cli_flag(self) -> str:
        return z17_flag(self.year)

    @property
    def school_year_label(self) -> str:
        start, end = school_year_bounds(self.year)
        return f"{start}/{end}"

    @property
    def snapshot_label(self) -> str:
        return f"31. 10. {self.year}"


@dataclass(frozen=True)
class SpecialRun:
    """Výsledek jednoho vytvoření podkladu."""

    year: int
    files: tuple[Path, ...]
    detail: str

    @property
    def pdf_path(self) -> Path | None:
        return self.files[0] if self.files else None


def peek_special_form(raw: dict[str, Any] | None) -> SpecialForm:
    values = peek_z17_ui(raw if isinstance(raw, dict) else {})
    try:
        year = parse_z17_year(values.get("rok"))
    except ConfigError:
        year = date.today().year
    categories = values.get("povolene_kategorie") or ()
    return SpecialForm(
        year=year,
        output=str(values.get("vystup") or DEFAULT_Z17_OUTPUT).strip()
        or DEFAULT_Z17_OUTPUT,
        use_all_categories=values.get("vsechny_kategorie", True) is not False,
        categories=tuple(str(code) for code in categories),
    )


def apply_special_form(raw: dict[str, Any], form: SpecialForm) -> dict[str, Any]:
    """Zapíše blok ``z17`` beze změny mapování kategorií na řádky výkazu."""
    block = raw.get("z17")
    block = dict(block) if isinstance(block, dict) else {}
    updated = apply_z17_ui(
        block,
        output=form.output,
        use_all_categories=form.use_all_categories,
        categories=list(form.categories),
        year=form.year,
    )
    return dict(raw, z17=updated)


def validate_form(form: SpecialForm) -> None:
    """Kontroly, které by jinak selhaly až při běhu."""
    if not MIN_YEAR <= int(form.year) <= MAX_YEAR:
        raise ConfigError(
            f"Rok výkazu musí být v rozsahu {MIN_YEAR}–{MAX_YEAR}."
        )
    if not form.use_all_categories and not form.categories:
        raise ConfigError(
            "Vyberte alespoň jednu kategorii, nebo zvolte všechny kategorie."
        )


def resolve_output(
    output: str, *, year: int, config_directory: Path
) -> Path:
    """Složka výstupu se zástupnou hodnotou {rok}."""
    text = str(output or "").strip() or DEFAULT_Z17_OUTPUT
    try:
        resolved = text.format(rok=year)
    except (KeyError, ValueError, IndexError) as exc:
        raise ConfigError(
            "Cesta smí používat pouze zástupnou hodnotu {rok}."
        ) from exc
    path = Path(resolved)
    if not path.is_absolute():
        path = config_directory / path
    return path


def expected_pdf(directory: Path, year: int) -> Path:
    return directory / f"{REPORT_PREFIX}{year}.pdf"


def existing_pdf(directory: Path, year: int) -> Path | None:
    """Podklad z dřívějšího běhu, aby šel otevřít i po restartu."""
    candidate = expected_pdf(directory, year)
    return candidate if candidate.is_file() else None


def category_summary(
    *, use_all: bool, selected: Sequence[str], total: int
) -> str:
    if use_all:
        return f"všechny kategorie ({total})" if total else "všechny kategorie"
    count = len(tuple(selected))
    if not total:
        return f"{count} vybráno"
    return f"{count} z {total} vybráno"


def row_choices() -> tuple[tuple[str, str], ...]:
    """Řádky výkazu, ke kterým lze přiřadit kategorie strávníků."""
    return tuple((code, ROW_LABELS.get(code, code)) for code in MAPPABLE_ROWS)


def peek_row_mapping(raw: dict[str, Any] | None) -> dict[str, tuple[str, ...]]:
    """Přiřazení kategorií k řádkům výkazu z bloku ``z17``."""
    block = raw.get("z17") if isinstance(raw, dict) else None
    mapping_raw = block.get("mapovani_kategorii") if isinstance(block, dict) else None
    mapping: dict[str, tuple[str, ...]] = {}
    for code in MAPPABLE_ROWS:
        values = mapping_raw.get(code) if isinstance(mapping_raw, dict) else None
        if isinstance(values, list):
            mapping[code] = tuple(
                str(item).strip() for item in values if str(item).strip()
            )
        else:
            mapping[code] = ()
    return mapping


def peek_supplement_rows(raw: dict[str, Any] | None) -> tuple[str, ...]:
    """Řádky, u kterých se doplňková jídla počítají v rámci vyhlášky."""
    block = raw.get("z17") if isinstance(raw, dict) else None
    values = (
        block.get("doplnkova_v_ramci_vyhlasky") if isinstance(block, dict) else None
    )
    if not isinstance(values, list):
        return DEFAULT_SUPPLEMENT_IN_SCOPE
    return tuple(
        str(item).strip() for item in values if str(item).strip() in MAPPABLE_ROWS
    )


def apply_row_mapping(
    raw: dict[str, Any],
    mapping: dict[str, Sequence[str]],
    supplement_rows: Sequence[str],
) -> dict[str, Any]:
    """Uloží mapování i doplňková jídla; ostatní klíče zůstanou beze změny."""
    block = raw.get("z17")
    block = dict(block) if isinstance(block, dict) else {}
    clean: dict[str, list[str]] = {}
    for code in MAPPABLE_ROWS:
        values = mapping.get(code, ())
        clean[code] = [str(item).strip() for item in values if str(item).strip()]
    block["mapovani_kategorii"] = clean
    block["doplnkova_v_ramci_vyhlasky"] = [
        str(code) for code in supplement_rows if str(code) in MAPPABLE_ROWS
    ]
    return dict(raw, z17=block)


def unmapped_categories(
    mapping: dict[str, Sequence[str]], categories: Sequence[str]
) -> tuple[str, ...]:
    """Kategorie, které zatím nepatří do žádného řádku výkazu."""
    assigned = {
        str(code).strip()
        for values in mapping.values()
        for code in values
        if str(code).strip()
    }
    return tuple(code for code in categories if code not in assigned)


def run_special(
    config_path: Path,
    *,
    year: int,
    on_progress: Callable[[int, str], None] | None = None,
) -> SpecialRun:
    result = run_z17_report(config_path, year=year, on_progress=on_progress)
    return SpecialRun(
        year=int(result.get("year", year)),
        files=tuple(Path(item) for item in result.get("files", ())),
        detail=str(result.get("detail", "")),
    )


def cli_example(year: int) -> str:
    """Příkaz pro spuštění bez GUI; ve výchozím stavu aktuální rok."""
    try:
        return z17_flag(parse_z17_year(year))
    except ConfigError:
        return Z17_FLAG_EXAMPLE
