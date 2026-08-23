"""Porovná živá čísla uzávěrky s referenčním tiskem Jídelny za květen 2026."""

from __future__ import annotations

from pathlib import Path

from stravovaci_arch import fetch_arch_report
from stravovaci_sestava import load_config
from uzaverka import resolve_categories
from uzaverka_nastaveni import parse_closing_settings, parse_period
from rekapitulace_sestava import fetch_recap_report

ROOT = Path(__file__).resolve().parent

# Strana 1 rekapitulace Jídelny: porce, limit, sazba, Přepl.MM, Nedo.MM
JIDELNA_MEALS = {
    "10": (2742, 106938, 106938, 441825, 0),
    "11": (3232, 132512, 132512, 728380, 0),
    "12": (412, 16892, 28016, 98979, 40),
    "13": (117, 4797, 12285, 13105, 0),
    "20": (151, 6191, 13439, 11219, 0),
    "4": (4425, 163725, 163725, 483947, 28),
    "5": (3536, 137904, 137904, 400468, 0),
    "6": (632, 25912, 25912, 75355, 0),
    "7": (234, 9594, 9594, 6047, 246),
    "9": (707, 28987, 28987, 121696, 0),
    "MŠ-P": (148, 6068, 6068, 0, 6232),
    "MŠ3-6": (548, 28496, 28496, 0, 29276),
    "MŠ7": (11, 605, 605, 0, 770),
    "MŠ7-P": (3, 129, 129, 0, 172),
    "MŠZAM": (83, 2905, 2905, 0, 3360),
}

# Strana 2: Placeno, Přepl.AM, FKSP, Ostatní
JIDELNA_FINANCE = {
    "10": (468805, 133918, 0, 0),
    "11": (792449, 196417, 0, 0),
    "12": (95214, 24291, 0, 8240),
    "13": (11365, 10545, 0, 2340),
    "20": (11520, 13740, 0, 3020),
    "4": (489301, 168412, 0, 0),
    "5": (426932, 163627, 0, 0),
    "6": (75518, 25993, 3160, 0),
    "7": (4975, 7743, 1170, 0),
    "9": (125050, 32341, 0, 0),
}

JIDELNA_TOTALS = {
    "portions": 16981,
    "limit": 671655,
    "rate": 697515,
    "fksp": 4330,
    "other": 13600,
    "dining": 1107,
    "registered": 1180,
    "enrolled": 1296,
    "bulk": 62,
}

JIDELNA_ARCH = {
    "22606": ("Černohorský Valentýn", 16, 624, 274, 898, 0),
    "20102": ("Bohm Tomáš", 16, 624, 2439, 2163, 900),
    "25502": ("Bradáč Michal", 16, 624, 2730, 2496, 858),
}


def _money(value: float) -> int:
    return int(round(value))


def compare_may_2026() -> list[str]:
    config_path = ROOT / "config.json"
    config = load_config(config_path, date_override="01.05.2026")
    raw = __import__("json").loads(config_path.read_text(encoding="utf-8"))
    year, month = parse_period(2026, 5)
    settings = parse_closing_settings(
        raw, year=year, month=month, config_directory=config_path.parent
    )
    config = resolve_categories(config, settings)
    recap = fetch_recap_report(config, variant=settings.recap_variant)
    arch = fetch_arch_report(config, include_bulk=settings.include_bulk_arch)

    errors: list[str] = []
    by_code = {row.category_code: row for row in recap.rows}

    for code, expected in JIDELNA_MEALS.items():
        row = by_code.get(code)
        if row is None:
            errors.append(f"chybí kategorie {code}")
            continue
        got = (
            row.portions,
            _money(row.monthly_limit),
            _money(row.monthly_rate),
            _money(row.credit_prev_plus),
            _money(row.debit_prev),
        )
        if got != expected:
            errors.append(f"{code} jídla {got} != {expected}")

    for code, expected in JIDELNA_FINANCE.items():
        row = by_code.get(code)
        if row is None:
            continue
        got = (
            _money(row.payment),
            _money(row.credit_now_plus),
            _money(row.fksp),
            _money(row.other_overhead),
        )
        if got != expected:
            errors.append(f"{code} finance {got} != {expected}")

    totals = (
        sum(row.portions for row in recap.rows),
        _money(sum(row.monthly_limit for row in recap.rows)),
        _money(sum(row.monthly_rate for row in recap.rows)),
        _money(sum(row.fksp for row in recap.rows)),
        _money(sum(row.other_overhead for row in recap.rows)),
        recap.counts.dining,
        recap.counts.registered,
        recap.counts.enrolled,
        recap.counts.bulk,
    )
    expected_totals = (
        JIDELNA_TOTALS["portions"],
        JIDELNA_TOTALS["limit"],
        JIDELNA_TOTALS["rate"],
        JIDELNA_TOTALS["fksp"],
        JIDELNA_TOTALS["other"],
        JIDELNA_TOTALS["dining"],
        JIDELNA_TOTALS["registered"],
        JIDELNA_TOTALS["enrolled"],
        JIDELNA_TOTALS["bulk"],
    )
    if totals != expected_totals:
        errors.append(f"součty {totals} != {expected_totals}")

    people = {person.var_symbol: person for person in arch.individuals}
    for symbol, expected in JIDELNA_ARCH.items():
        person = people.get(symbol)
        if person is None:
            errors.append(f"arch chybí VS {symbol}")
            continue
        got = (
            person.name,
            person.portions,
            _money(person.prescription),
            _money(person.payment),
            _money(max(person.credit_prev, 0)),
            _money(max(person.credit_now, 0)),
        )
        if got != expected:
            errors.append(f"arch {symbol} {got} != {expected}")
    return errors


def main() -> None:
    errors = compare_may_2026()
    out = ROOT / "_compare_jidelna_out.txt"
    if errors:
        text = "NESROVNALOSTÍ: {}\n{}".format(len(errors), "\n".join(errors))
    else:
        text = "OK: rekapitulace i vzorek archu sedí na PDF Jídelny za 2026-05."
    out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
