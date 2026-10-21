"""Kategorie pro denní stav DataShip / automatické počty.

Výchozí režim je VŠECHNY aktuální kategorie z public.kategor.
Staré seznamy (povolene_kategorie) nemohou nepozorovaně omezit součet.
Výběrový filtr se uplatní jedině po výslovném uložení v Administraci,
kdy poctyemailem.vsechny_kategorie == false.
"""

from __future__ import annotations

from typing import Any

from stravovaci_sestava import ConfigError


def all_client_categories(raw: dict[str, Any]) -> bool:
    """Výchozí režim ALL platí i při migraci starého config.json."""
    block = raw.get("poctyemailem")
    if block is not None and not isinstance(block, dict):
        raise ConfigError("'poctyemailem' musí být JSON objekt.")
    flag = block.get("vsechny_kategorie") if isinstance(block, dict) else None
    if flag is None:
        return True
    if not isinstance(flag, bool):
        raise ConfigError("'poctyemailem.vsechny_kategorie' musí být true/false.")
    return flag


def peek_client_categories(raw: dict[str, Any]) -> list[str]:
    """Vrátí uložený historický seznam pro případ zapnutí vlastního výběru."""
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
    """Prázdná tuple = VŠECHNY kategorie získané přímo z DB v čase sestavy."""
    if all_client_categories(raw):
        return ()
    source = _category_source(raw)
    if not isinstance(source, list) or not source:
        raise ConfigError(
            "Pro režim 'Jen vybrané kategorie' vyberte alespoň jednu kategorii "
            "v Administraci → Kategorie denního stavu."
        )
    if not all(isinstance(item, str) and item.strip() for item in source):
        raise ConfigError("Povolené kategorie musí být neprázdné texty.")
    return tuple(dict.fromkeys(item.strip() for item in source))


def _category_source(raw: dict[str, Any]) -> object:
    block = raw.get("poctyemailem")
    if isinstance(block, dict) and "povolene_kategorie" in block:
        return block.get("povolene_kategorie")
    return raw.get("povolene_kategorie")
