"""Denní stav: nastavení sestavy, tvorba PDF a odeslání mailem."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence

from credential_store import sanitize_config
from funkce import FUNCTION_DAILY, load_function_mails
from mail_service import (
    MailDispatchResult,
    cooking_status_message,
    fetch_cooking_status,
    mail_subject,
    normalize_recipient,
    normalize_recipients,
    send_pdf_via_mailsender,
    should_send_on_cooking_day,
)
from pocty_nastaveni import peek_client_categories
from stravovaci_sestava import ConfigError, create_pdf, fetch_report, load_config

from services.config_io import (
    CZECH_DATE_FORMAT,
    DEFAULT_PDF_OUTPUT,
    configured_date,
)


ORIENTATIONS = ("na_vysku", "na_sirku")
ORIENTATION_LABELS = {"na_vysku": "Na výšku", "na_sirku": "Na šířku"}
FONT_SIZE_MIN = 5.0
FONT_SIZE_MAX = 18.0


@dataclass(frozen=True)
class DailySettings:
    """Hodnoty obrazovky Denní stav odpovídající klíčům config.json."""

    report_date: date
    categories: tuple[str, ...] = ()
    language: str = "česky"
    menu_list_number: int = 1
    pdf_output: str = DEFAULT_PDF_OUTPUT
    pdf_orientation: str = "na_vysku"
    pdf_data_font_size: float = 7.4
    pdf_label_font_size: float = 7.4
    pdf_bold: bool = False
    category_separation: bool = False
    show_by_categories: bool = True
    show_by_norms: bool = True

    def with_categories(self, categories: Sequence[str]) -> "DailySettings":
        return replace(self, categories=tuple(categories))


@dataclass(frozen=True)
class DailyMail:
    """Mailové nastavení funkce Denní stav."""

    recipients: tuple[str, ...] = ()
    body: str = ""
    only_cooking_days: bool = False
    sender: str = ""


@dataclass(frozen=True)
class DailyDispatch:
    """Výsledek akce „Vytvořit PDF a odeslat“."""

    skipped: bool
    message: str = ""
    pdf_path: Path | None = None
    dispatch: MailDispatchResult | None = None


@dataclass(frozen=True)
class ActionState:
    """Stav tlačítek obrazovky Denní stav."""

    can_create: bool
    can_send: bool
    can_open_last: bool
    reason: str = ""


def _dropped_phrase(count: int) -> str:
    if count == 1:
        return "z výběru vypadla 1 kategorie, která už v databázi není"
    if count < 5:
        return f"z výběru vypadly {count} kategorie, které už v databázi nejsou"
    return f"z výběru vypadlo {count} kategorií, které už v databázi nejsou"


def recipients_phrase(count: int) -> str:
    """Skloňování příjemců pro krátká hlášení ve stavovém řádku."""
    if count == 1:
        return "1 příjemci"
    return f"{count} příjemcům"


def _selected_all_phrase(count: int) -> str:
    if count == 1:
        return "vybrána jediná dostupná kategorie"
    if count < 5:
        return f"vybrány všechny {count} dostupné kategorie"
    return f"vybráno všech {count} dostupných kategorií"


@dataclass(frozen=True)
class CategoryResolution:
    """Výběr kategorií po srovnání s aktuální databází."""

    selected: tuple[str, ...]
    dropped: tuple[str, ...]
    selected_all: bool

    def status_note(self, available: int) -> str:
        """Doplňující text do stavového řádku; prázdný, pokud se nic nezměnilo."""
        parts: list[str] = []
        if self.dropped:
            parts.append(_dropped_phrase(len(self.dropped)))
        if self.selected_all:
            parts.append(_selected_all_phrase(available))
        return " · ".join(parts)


@dataclass(frozen=True)
class OverviewRow:
    """Jeden řádek přehledu porcí."""

    meal_type: str
    menu: int
    meal_name: str
    portions: int


@dataclass(frozen=True)
class DailyOverview:
    """Souhrn dne, který se zobrazuje ještě před tvorbou PDF."""

    report_date: date | None = None
    rows: tuple[OverviewRow, ...] = ()
    diners: int = 0
    categories: int = 0

    @property
    def total_portions(self) -> int:
        return sum(row.portions for row in self.rows)


@dataclass(frozen=True)
class DailyResult:
    """Výsledek tvorby PDF včetně dat pro přehled."""

    pdf_path: Path
    overview: DailyOverview


def _orientation(value: object) -> str:
    text = str(value or "").strip().casefold()
    aliases = {
        "na_sirku": "na_sirku",
        "na šířku": "na_sirku",
        "na sirku": "na_sirku",
        "landscape": "na_sirku",
        "na_vysku": "na_vysku",
        "na výšku": "na_vysku",
        "na vysku": "na_vysku",
        "portrait": "na_vysku",
    }
    return aliases.get(text, "na_vysku")


def _font_size(value: object, default: float) -> float:
    try:
        size = float(value)
    except (TypeError, ValueError):
        return default
    if not FONT_SIZE_MIN <= size <= FONT_SIZE_MAX:
        return default
    return size


def peek_daily_settings(raw: dict[str, Any] | None) -> DailySettings:
    """Načte nastavení denní sestavy; chybějící klíče doplní výchozími."""
    source = raw if isinstance(raw, dict) else {}
    categories = peek_client_categories(source)
    if not categories:
        fallback = source.get("povolene_kategorie")
        if isinstance(fallback, list):
            categories = [str(code) for code in fallback if str(code).strip()]
    language = str(source.get("jazyk_jidelnicku") or "česky").strip() or "česky"
    try:
        menu_number = int(source.get("cislo_jidelnicku", 1))
    except (TypeError, ValueError):
        menu_number = 1
    output = str(source.get("pdf_vystup") or "").strip() or DEFAULT_PDF_OUTPUT
    return DailySettings(
        report_date=configured_date(source),
        categories=tuple(categories),
        language=language,
        menu_list_number=max(1, menu_number),
        pdf_output=output,
        pdf_orientation=_orientation(source.get("pdf_orientace")),
        pdf_data_font_size=_font_size(source.get("pdf_velikost_dat"), 7.4),
        pdf_label_font_size=_font_size(source.get("pdf_velikost_popisku"), 7.4),
        pdf_bold=source.get("pdf_tucne") is True,
        category_separation=source.get("kategor_separ") is True,
        show_by_categories=source.get("dle_kategorii") is not False,
        show_by_norms=source.get("dle_norem") is not False,
    )


def peek_daily_mail(raw: dict[str, Any] | None) -> DailyMail:
    """Načte příjemce a text mailu funkce Denní stav."""
    source = raw if isinstance(raw, dict) else {}
    daily = load_function_mails(source)[FUNCTION_DAILY]
    sender = str(source.get("mail_odesilatel") or "").strip()
    return DailyMail(
        recipients=tuple(daily["prijemci"]),
        body=str(daily["text"] or ""),
        only_cooking_days=bool(daily["jen_varne_dny"]),
        sender=sender,
    )


def validate_daily_settings(settings: DailySettings) -> None:
    """Zvaliduje hodnoty z formuláře; chyby hlásí jako ConfigError."""
    if not settings.categories:
        raise ConfigError("Vyberte alespoň jednu kategorii pro export.")
    if not settings.language.strip():
        raise ConfigError("Jazyk jídelníčku nesmí být prázdný.")
    output = settings.pdf_output.strip()
    if not output:
        raise ConfigError("Výstupní cesta PDF nesmí být prázdná.")
    if not output.casefold().endswith(".pdf"):
        raise ConfigError("Výstupní soubor musí mít příponu .pdf.")
    if settings.menu_list_number < 1:
        raise ConfigError("Číslo jídelníčku musí být kladné.")
    for size in (settings.pdf_data_font_size, settings.pdf_label_font_size):
        if not FONT_SIZE_MIN <= size <= FONT_SIZE_MAX:
            raise ConfigError("Velikosti písma musí být v rozsahu 5 až 18.")
    if settings.pdf_orientation not in ORIENTATIONS:
        raise ConfigError("Orientace musí být na výšku, nebo na šířku.")


def apply_daily_settings(
    raw: dict[str, Any], settings: DailySettings
) -> dict[str, Any]:
    """Zapíše nastavení denní sestavy do configu; ostatní bloky zachová."""
    validate_daily_settings(settings)
    updated = sanitize_config(raw)
    categories = list(settings.categories)
    pocty = updated.get("poctyemailem")
    pocty = dict(pocty) if isinstance(pocty, dict) else {}
    pocty["povolene_kategorie"] = categories
    updated.update(
        {
            "povolene_kategorie": categories,
            "poctyemailem": pocty,
            "kategor_separ": bool(settings.category_separation),
            "dle_kategorii": bool(settings.show_by_categories),
            "dle_norem": bool(settings.show_by_norms),
            "datum": settings.report_date.strftime(CZECH_DATE_FORMAT),
            "jazyk_jidelnicku": settings.language.strip(),
            "cislo_jidelnicku": int(settings.menu_list_number),
            "pdf_vystup": settings.pdf_output.strip(),
            "pdf_orientace": settings.pdf_orientation,
            "pdf_velikost_dat": float(settings.pdf_data_font_size),
            "pdf_velikost_popisku": float(settings.pdf_label_font_size),
            "pdf_tucne": bool(settings.pdf_bold),
        }
    )
    return updated


def selection_summary(selected: int, total: int) -> str:
    """Text „18 z 21 vybráno“ pro kompaktní řádek kategorií."""
    if total <= 0:
        return f"{selected} vybráno"
    return f"{selected} z {total} vybráno"


def describe_moment(moment: datetime, *, now: datetime | None = None) -> str:
    """Čas v podobě „dnes 08:12“, „včera 08:12“ nebo „05.08.2026 08:12“."""
    reference = (now or datetime.now()).date()
    day = moment.date()
    clock = moment.strftime("%H:%M")
    if day == reference:
        return f"dnes {clock}"
    if (reference - day).days == 1:
        return f"včera {clock}"
    return f"{moment.strftime(CZECH_DATE_FORMAT)} {clock}"


def selection_preview(codes: Sequence[str], limit: int = 10) -> str:
    """Krátký výpis vybraných kategorií; zbytek shrne počtem."""
    items = [str(code) for code in codes]
    if not items:
        return "žádná kategorie"
    if len(items) <= limit:
        return ", ".join(items)
    rest = len(items) - limit
    return ", ".join(items[:limit]) + f" + {rest} dalších"


def restrict_categories(
    selected: Sequence[str], available: Sequence[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Rozdělí výběr na kategorie existující v databázi a na zaniklé."""
    existing = {str(code).strip() for code in available if str(code).strip()}
    kept = tuple(code for code in selected if str(code).strip() in existing)
    dropped = tuple(code for code in selected if str(code).strip() not in existing)
    return kept, dropped


def reconcile_categories(
    selected: Sequence[str], available: Sequence[str]
) -> CategoryResolution:
    """Sladí uložený výběr s kategoriemi v databázi.

    Zůstane-li po odebrání zaniklých kategorií prázdný výběr, vybere všechny
    dostupné.  Denní sestava se běžně dělá za celou provozovnu, takže je to
    použitelnější výchozí stav než zamčená obrazovka.
    """
    options = tuple(str(code).strip() for code in available if str(code).strip())
    kept, dropped = restrict_categories(selected, options)
    if kept or not options:
        return CategoryResolution(kept, dropped, False)
    return CategoryResolution(options, dropped, True)


def action_state(
    *,
    connected: bool,
    selected_categories: int,
    recipients: int,
    has_last_pdf: bool,
    busy: bool = False,
) -> ActionState:
    """Presenter logika tlačítek; UI ji jen promítne do widgetů."""
    if busy:
        return ActionState(False, False, has_last_pdf, "Probíhá operace…")
    if not connected:
        return ActionState(
            False,
            False,
            has_last_pdf,
            "Bez databázového připojení nelze sestavu vytvořit.",
        )
    if selected_categories <= 0:
        return ActionState(
            False, False, has_last_pdf, "Vyberte alespoň jednu kategorii."
        )
    if recipients <= 0:
        return ActionState(
            True,
            False,
            has_last_pdf,
            "Pro odeslání doplňte příjemce v Administraci → E-maily.",
        )
    return ActionState(True, True, has_last_pdf)


def overview_from_report(report: Any, report_date: date) -> DailyOverview:
    """Převede data sestavy na přehledovou tabulku."""
    rows = tuple(
        OverviewRow(
            meal_type=str(menu.meal_type or "").strip(),
            menu=int(menu.menu),
            meal_name=str(menu.meal_name or "").strip(),
            portions=int(menu.portions or 0),
        )
        for menu in report.menus
    )
    return DailyOverview(
        report_date=report_date,
        rows=rows,
        diners=len(report.diners),
        categories=len(report.active_categories or report.categories),
    )


def fetch_daily_overview(config_path: Path) -> DailyOverview:
    """Načte souhrn dne bez tvorby PDF."""
    config = load_config(config_path)
    report = fetch_report(config)
    return overview_from_report(report, config.report_date)


def create_daily_pdf(config_path: Path) -> DailyResult:
    """Načte data z databáze, vytvoří denní PDF a vrátí i souhrn."""
    config = load_config(config_path)
    report = fetch_report(config)
    path = create_pdf(config, report)
    return DailyResult(
        pdf_path=path, overview=overview_from_report(report, config.report_date)
    )


def send_daily_pdf(
    config_path: Path,
    *,
    recipients: Sequence[str],
    api_key: str,
    sender: str,
    body: str,
    only_cooking_days: bool,
) -> DailyDispatch:
    """Vytvoří denní PDF a odešle je mailem; respektuje varné dny."""
    normalized = normalize_recipients(recipients)
    sender_email = normalize_recipient(sender)
    config = load_config(config_path)
    if only_cooking_days:
        statuses = fetch_cooking_status(config)
        if not should_send_on_cooking_day(statuses):
            return DailyDispatch(
                skipped=True, message=cooking_status_message(statuses)
            )
    report = fetch_report(config)
    path = create_pdf(config, report)
    dispatch = send_pdf_via_mailsender(
        normalized,
        mail_subject(config.report_date),
        body,
        path,
        api_key=api_key,
        sender_email=sender_email,
    )
    return DailyDispatch(skipped=False, pdf_path=path, dispatch=dispatch)
