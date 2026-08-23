"""Povolené kategorie klienta pro denní počty e-mailem (SCIO)."""

from __future__ import annotations

from typing import Any

from stravovaci_sestava import ConfigError


def peek_client_categories(raw: dict[str, Any]) -> list[str]:
    """Vrátí uložený výběr klienta, i když je ještě prázdný."""
    source = _category_source(raw)
    if not isinstance(source, list):
        return []
    seen: list[str] = []
    for item in source:
        if not isinstance(item, str) or not item.strip():
            continue
        code = item.strip()
        if code not in seen:
            seen.append(code)
    return seen


def parse_client_categories(raw: dict[str, Any]) -> tuple[str, ...]:
    """Vrátí neprázdnou podmnožinu kategorií, kterou si klient sám povolil.

    Uzávěrka má vlastní přepínač ``uzaverka.vsechny_kategorie`` a tento seznam
    ignoruje. Počty e-mailem nesmí skrytě přepnout na všechny kategorie.
    """
    block = raw.get("poctyemailem")
    if block is None:
        block = {}
    if not isinstance(block, dict):
        raise ConfigError("'poctyemailem' musí být JSON objekt.")
    if block.get("vsechny_kategorie") is True:
        raise ConfigError(
            "Počty e-mailem nesmí použít všechny kategorie. "
            "Klient musí v záložce Kategorie vybrat povolenou podmnožinu."
        )

    source = _category_source(raw)
    key = (
        "poctyemailem.povolene_kategorie"
        if isinstance(block, dict) and "povolene_kategorie" in block
        else "povolene_kategorie"
    )
    if not isinstance(source, list) or not source:
        raise ConfigError(
            f"'{key}' musí být neprázdné JSON pole kategorií, "
            "které si klient povolil pro odeslání počtů."
        )
    if not all(isinstance(item, str) and item.strip() for item in source):
        raise ConfigError(f"Každá položka v '{key}' musí být neprázdný text.")
    return tuple(dict.fromkeys(item.strip() for item in source))


def _category_source(raw: dict[str, Any]) -> object:
    block = raw.get("poctyemailem")
    if isinstance(block, dict) and "povolene_kategorie" in block:
        return block.get("povolene_kategorie")
    return raw.get("povolene_kategorie")
