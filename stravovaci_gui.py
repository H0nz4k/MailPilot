#!/usr/bin/env python3
"""Záložní technické UI pro AutoReport."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from datetime import date
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, BooleanVar, StringVar, Text, Tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Sequence

from credential_store import (
    CredentialStoreError,
    get_password,
    sanitize_config,
    set_password,
    write_config,
)
from env_store import EnvStoreError, get_resend_api_key, set_resend_api_key
from mail_service import (
    cooking_status_message,
    fetch_cooking_status,
    mail_subject,
    normalize_recipient,
    normalize_recipients,
    send_pdf_via_mailsender,
    should_send_on_cooking_day,
)
from stravovaci_sestava import ConfigError, create_pdf, fetch_report, load_config


APP_TITLE = "AutoReport"


def load_ui_config(path: Path) -> dict[str, Any]:
    """Načte config nebo použije bezpečný vzor při prvním spuštění."""
    source = path if path.is_file() else Path(__file__).with_name("config.example.json")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Konfigurační soubor neexistuje: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Neplatný JSON v {source} (řádek {exc.lineno}, sloupec {exc.colno})."
        ) from exc
    if not isinstance(raw, dict):
        raise ConfigError("Kořen configu musí být JSON objekt.")
    return raw


def database_parameters(raw: dict[str, Any]) -> dict[str, Any]:
    database = raw.get("databaze", {})
    if not isinstance(database, dict):
        database = {}
    return {
        "host": str(database.get("host", "127.0.0.1")).strip(),
        "port": database.get("port", 5432),
        "dbname": str(database.get("dbname", "jidelna")).strip(),
        "user": str(database.get("user", "altisima-client")).strip(),
        "sslmode": str(database.get("sslmode", "prefer")).strip() or "prefer",
        "connect_timeout": int(database.get("connect_timeout", 10)),
    }


def open_document(path: Path) -> None:
    """Otevře PDF ve výchozím systémovém prohlížeči."""
    path = path.resolve()
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class StravovaciApp:
    def __init__(self, root: Tk, config_path: Path) -> None:
        self.root = root
        self.config_path = config_path.resolve()
        self.raw = load_ui_config(self.config_path)
        self.connection_ok = False
        self.initializing = True
        self.selected_categories: set[str] = set()
        self.category_code_by_iid: dict[str, str] = {}
        self.last_pdf: Path | None = None
        self.mail_recipients: list[str] = []

        self.root.title(APP_TITLE)
        self.root.geometry("980x720")
        self.root.minsize(850, 620)
        self._configure_style()
        self._create_variables()
        self._build_window()
        self._load_initial_password()
        self._load_initial_resend_api_key()
        self._bind_connection_changes()
        self._bind_date_changes()
        self.initializing = False

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Hint.TLabel", foreground="#5d6b78")
        style.configure("Success.TLabel", foreground="#18794e")
        style.configure("Error.TLabel", foreground="#b42318")
        style.configure("Primary.TButton", padding=(18, 8))

    def _create_variables(self) -> None:
        db = database_parameters(self.raw)
        self.host_var = StringVar(value=db["host"])
        self.port_var = StringVar(value=str(db["port"]))
        self.dbname_var = StringVar(value=db["dbname"])
        self.user_var = StringVar(value=db["user"])
        self.password_var = StringVar(value="")

        today = date.today()
        configured_date = str(self.raw.get("datum") or "")
        try:
            day, month, year = (int(part) for part in configured_date.split("."))
            selected_date = date(year, month, day)
        except (TypeError, ValueError):
            selected_date = today
        self.day_var = StringVar(value=str(selected_date.day))
        self.month_var = StringVar(value=str(selected_date.month))
        self.year_var = StringVar(value=str(selected_date.year))

        self.category_separation_var = BooleanVar(
            value=bool(self.raw.get("kategor_separ", False))
        )
        self.language_var = StringVar(
            value=str(self.raw.get("jazyk_jidelnicku", "česky"))
        )
        self.menu_list_var = StringVar(
            value=str(self.raw.get("cislo_jidelnicku", 1))
        )
        self.pdf_output_var = StringVar(
            value=str(
                self.raw.get(
                    "pdf_vystup",
                    "vystup/AutoReport_{datum}.pdf",
                )
            )
        )
        orientation = str(self.raw.get("pdf_orientace", "na_vysku"))
        self.pdf_orientation_var = StringVar(
            value="Na výšku" if "vys" in orientation.casefold() else "Na šířku"
        )
        self.pdf_data_size_var = StringVar(
            value=str(self.raw.get("pdf_velikost_dat", 8.5))
        )
        self.pdf_label_size_var = StringVar(
            value=str(self.raw.get("pdf_velikost_popisku", 9.0))
        )
        self.pdf_bold_var = BooleanVar(value=bool(self.raw.get("pdf_tucne", False)))
        self.show_categories_var = BooleanVar(
            value=bool(self.raw.get("dle_kategorii", True))
        )
        self.show_norms_var = BooleanVar(value=bool(self.raw.get("dle_norem", True)))
        self.status_var = StringVar(value="Nejprve otestujte připojení k databázi.")
        self.category_count_var = StringVar(value="Vybráno: 0")
        self.pdf_status_var = StringVar(value="PDF zatím nebylo vytvořeno.")
        self.mail_recipient_var = StringVar(value="")
        self.mail_sender_var = StringVar(
            value=str(self.raw.get("mail_odesilatel", "podpora@altisima.cz"))
        )
        self.resend_api_key_var = StringVar(value="")
        self.mail_only_cooking_days_var = BooleanVar(
            value=bool(self.raw.get("mail_jen_varne_dny", False))
        )
        self.mail_subject_var = StringVar(value="")
        self.mail_status_var = StringVar(value="Mail zatím nebyl odeslán.")

    def _build_window(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill=BOTH, expand=True)

        ttk.Label(outer, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Technická konfigurace databázového exportu",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(2, 14))

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill=BOTH, expand=True)

        self.db_tab = ttk.Frame(self.notebook, padding=20)
        self.category_tab = ttk.Frame(self.notebook, padding=16)
        self.settings_tab = ttk.Frame(self.notebook, padding=16)
        self.pdf_tab = ttk.Frame(self.notebook, padding=20)
        self.mail_tab = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(self.db_tab, text="  DB connect  ")
        self.notebook.add(self.category_tab, text="  Kategorie  ", state="disabled")
        self.notebook.add(self.settings_tab, text="  Nastavení  ")
        self.notebook.add(self.pdf_tab, text="  PDF  ", state="disabled")
        self.notebook.add(self.mail_tab, text="  Mail  ")

        self._build_db_tab()
        self._build_category_tab()
        self._build_settings_tab()
        self._build_pdf_tab()
        self._build_mail_tab()

        footer = ttk.Frame(outer)
        footer.pack(fill=X, pady=(12, 0))
        ttk.Label(footer, textvariable=self.status_var, style="Hint.TLabel").pack(
            side=LEFT, fill=X, expand=True
        )
        ttk.Label(footer, text="AutoReport by HanzG", style="Hint.TLabel").pack(
            side=RIGHT
        )

    def _build_db_tab(self) -> None:
        ttk.Label(
            self.db_tab, text="Připojení k PostgreSQL", style="Section.TLabel"
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))
        fields = (
            ("IP / server", self.host_var, False),
            ("Port", self.port_var, False),
            ("Název databáze", self.dbname_var, False),
            ("Uživatel", self.user_var, False),
            ("Heslo", self.password_var, True),
        )
        for row, (label, variable, secret) in enumerate(fields, start=1):
            ttk.Label(self.db_tab, text=label).grid(
                row=row, column=0, sticky="w", padx=(0, 14), pady=6
            )
            entry = ttk.Entry(
                self.db_tab,
                textvariable=variable,
                width=42,
                show="●" if secret else "",
            )
            entry.grid(row=row, column=1, sticky="ew", pady=6)
            if secret:
                ttk.Label(
                    self.db_tab,
                    text="Uloženo v systémovém trezoru, ne v config.json.",
                    style="Hint.TLabel",
                ).grid(row=row, column=2, sticky="w", padx=(12, 0))

        self.test_button = ttk.Button(
            self.db_tab,
            text="TEST připojení",
            style="Primary.TButton",
            command=self.test_connection,
        )
        self.test_button.grid(row=7, column=1, sticky="w", pady=(20, 8))
        self.db_status_label = ttk.Label(
            self.db_tab, text="Připojení zatím nebylo ověřeno.", style="Hint.TLabel"
        )
        self.db_status_label.grid(row=8, column=0, columnspan=3, sticky="w")
        self.db_tab.columnconfigure(1, weight=1)

    def _build_category_tab(self) -> None:
        top = ttk.Frame(self.category_tab)
        top.pack(fill=X, pady=(0, 10))
        ttk.Label(top, text="Kategorie z databáze", style="Section.TLabel").pack(
            side=LEFT
        )
        ttk.Label(top, textvariable=self.category_count_var).pack(side=RIGHT)

        actions = ttk.Frame(self.category_tab)
        actions.pack(fill=X, pady=(0, 8))
        ttk.Button(actions, text="Vybrat vše", command=self.select_all_categories).pack(
            side=LEFT
        )
        ttk.Button(actions, text="Zrušit vše", command=self.clear_categories).pack(
            side=LEFT, padx=(8, 0)
        )
        ttk.Label(
            actions,
            text="Kliknutím na řádek kategorii zahrnete nebo vyřadíte.",
            style="Hint.TLabel",
        ).pack(side=LEFT, padx=(16, 0))

        table_frame = ttk.Frame(self.category_tab)
        table_frame.pack(fill=BOTH, expand=True)
        self.category_tree = ttk.Treeview(
            table_frame,
            columns=("selected", "code", "name"),
            show="headings",
            selectmode="none",
        )
        self.category_tree.heading("selected", text="Export")
        self.category_tree.heading("code", text="Označení")
        self.category_tree.heading("name", text="Název kategorie")
        self.category_tree.column("selected", width=70, anchor="center", stretch=False)
        self.category_tree.column("code", width=150, anchor="w", stretch=False)
        self.category_tree.column("name", width=520, anchor="w")
        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.category_tree.yview
        )
        self.category_tree.configure(yscrollcommand=scrollbar.set)
        self.category_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill="y")
        self.category_tree.bind("<Button-1>", self._toggle_category_click)
        self.category_tree.tag_configure("included", background="#eaf5ef")

    def _build_settings_tab(self) -> None:
        canvas = ttk.Frame(self.settings_tab)
        canvas.pack(fill=BOTH, expand=True)
        ttk.Label(canvas, text="Vzhled a obsah exportu", style="Section.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
        )

        row = 1
        row = self._add_checkbox_setting(
            canvas,
            row,
            "Oddělit seznam dle kategorií",
            self.category_separation_var,
            "Každá kategorie dostane vlastní nadpis a abecední seznam.",
        )
        row = self._add_entry_setting(
            canvas,
            row,
            "Jazyk jídelníčku",
            self.language_var,
            "Hodnota sloupce jazyk v tabulce jidelnicek, obvykle ‚česky‘.",
        )
        row = self._add_spin_setting(
            canvas,
            row,
            "Číslo jídelníčku",
            self.menu_list_var,
            1,
            99,
            "Určuje, ze kterého jídelníčku se načtou názvy objednaných menu.",
        )
        row = self._add_entry_setting(
            canvas,
            row,
            "Výstupní PDF",
            self.pdf_output_var,
            "Cesta a název souboru; lze použít {datum} nebo {datum_cz}.",
            width=52,
        )

        ttk.Label(canvas, text="Orientace PDF").grid(
            row=row, column=0, sticky="w", padx=(0, 12), pady=5
        )
        ttk.Combobox(
            canvas,
            textvariable=self.pdf_orientation_var,
            values=("Na výšku", "Na šířku"),
            state="readonly",
            width=18,
        ).grid(row=row, column=1, sticky="w", pady=5)
        ttk.Label(
            canvas,
            text="Na výšku je užší; na šířku poskytne více místa názvům jídel.",
            style="Hint.TLabel",
        ).grid(row=row, column=2, sticky="w", padx=(14, 0))
        row += 1

        row = self._add_spin_setting(
            canvas,
            row,
            "Velikost dat",
            self.pdf_data_size_var,
            5,
            18,
            "Velikost textu v datových řádcích PDF, v bodech.",
            increment=0.5,
        )
        row = self._add_spin_setting(
            canvas,
            row,
            "Velikost popisků",
            self.pdf_label_size_var,
            5,
            18,
            "Velikost záhlaví sloupců, nadpisů a popisků, v bodech.",
            increment=0.5,
        )
        row = self._add_checkbox_setting(
            canvas,
            row,
            "Tučná data",
            self.pdf_bold_var,
            "Vytiskne tučně také obsah tabulek; nadpisy jsou tučné vždy.",
        )
        row = self._add_checkbox_setting(
            canvas,
            row,
            "Souhrn dle kategorií",
            self.show_categories_var,
            "Zobrazí tabulku počtu přihlášek pro jednotlivé kategorie.",
        )
        self._add_checkbox_setting(
            canvas,
            row,
            "Souhrn dle norem",
            self.show_norms_var,
            "Zobrazí rozpad Menu 1–9 podle norem A, B, C a D.",
        )
        canvas.columnconfigure(2, weight=1)

    def _add_entry_setting(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: StringVar,
        help_text: str,
        width: int = 24,
    ) -> int:
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", padx=(0, 12), pady=5
        )
        ttk.Entry(parent, textvariable=variable, width=width).grid(
            row=row, column=1, sticky="w", pady=5
        )
        ttk.Label(parent, text=help_text, style="Hint.TLabel", wraplength=420).grid(
            row=row, column=2, sticky="w", padx=(14, 0)
        )
        return row + 1

    def _add_spin_setting(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: StringVar,
        minimum: float,
        maximum: float,
        help_text: str,
        increment: float = 1,
    ) -> int:
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", padx=(0, 12), pady=5
        )
        ttk.Spinbox(
            parent,
            textvariable=variable,
            from_=minimum,
            to=maximum,
            increment=increment,
            width=10,
        ).grid(row=row, column=1, sticky="w", pady=5)
        ttk.Label(parent, text=help_text, style="Hint.TLabel", wraplength=420).grid(
            row=row, column=2, sticky="w", padx=(14, 0)
        )
        return row + 1

    def _add_checkbox_setting(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: BooleanVar,
        help_text: str,
    ) -> int:
        ttk.Checkbutton(parent, text=label, variable=variable).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=6
        )
        ttk.Label(parent, text=help_text, style="Hint.TLabel", wraplength=420).grid(
            row=row, column=2, sticky="w", padx=(14, 0)
        )
        return row + 1

    def _build_pdf_tab(self) -> None:
        ttk.Label(self.pdf_tab, text="Vytvoření PDF", style="Section.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            self.pdf_tab,
            text=(
                "Zvolte den, pro který se mají načíst přihlášky. PDF se po "
                "vytvoření automaticky otevře ve výchozím prohlížeči."
            ),
            style="Hint.TLabel",
            wraplength=700,
        ).pack(anchor="w", pady=(5, 20))

        date_row = ttk.Frame(self.pdf_tab)
        date_row.pack(anchor="w")
        ttk.Label(date_row, text="Datum:").pack(side=LEFT, padx=(0, 10))
        ttk.Spinbox(date_row, textvariable=self.day_var, from_=1, to=31, width=4).pack(
            side=LEFT
        )
        ttk.Label(date_row, text=".").pack(side=LEFT)
        ttk.Spinbox(
            date_row, textvariable=self.month_var, from_=1, to=12, width=4
        ).pack(side=LEFT)
        ttk.Label(date_row, text=".").pack(side=LEFT)
        ttk.Spinbox(
            date_row, textvariable=self.year_var, from_=2020, to=2100, width=7
        ).pack(side=LEFT)

        self.generate_button = ttk.Button(
            self.pdf_tab,
            text="Vytvořit a zobrazit PDF",
            style="Primary.TButton",
            command=self.generate_pdf,
        )
        self.generate_button.pack(anchor="w", pady=(24, 10))
        self.open_pdf_button = ttk.Button(
            self.pdf_tab,
            text="Znovu otevřít poslední PDF",
            command=self.open_last_pdf,
            state="disabled",
        )
        self.open_pdf_button.pack(anchor="w")
        ttk.Label(
            self.pdf_tab, textvariable=self.pdf_status_var, style="Hint.TLabel"
        ).pack(anchor="w", pady=(16, 0))

    def _build_mail_tab(self) -> None:
        ttk.Label(
            self.mail_tab, text="Odeslání PDF e-mailem", style="Section.TLabel"
        ).pack(anchor="w")
        ttk.Label(
            self.mail_tab,
            text=(
                "Každému příjemci se odešle vytvořené PDF. Předmět se skládá "
                "automaticky z data exportu."
            ),
            style="Hint.TLabel",
            wraplength=760,
        ).pack(anchor="w", pady=(5, 12))

        transport_frame = ttk.LabelFrame(
            self.mail_tab, text=" Resend ", padding=(10, 8)
        )
        transport_frame.pack(fill=X, pady=(0, 10))
        ttk.Label(transport_frame, text="API klíč:").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=3
        )
        ttk.Entry(
            transport_frame,
            textvariable=self.resend_api_key_var,
            width=42,
            show="●",
        ).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(
            transport_frame,
            text="Načítá se ze souboru .env, nikdy z config.json.",
            style="Hint.TLabel",
        ).grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Label(transport_frame, text="Odesílatel:").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=3
        )
        ttk.Entry(
            transport_frame,
            textvariable=self.mail_sender_var,
            width=42,
        ).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Label(
            transport_frame,
            text="E-mail na doméně ověřené v Resendu.",
            style="Hint.TLabel",
        ).grid(row=1, column=2, sticky="w", padx=(12, 0))
        transport_frame.columnconfigure(1, weight=1)

        recipient_row = ttk.Frame(self.mail_tab)
        recipient_row.pack(fill=X)
        ttk.Label(recipient_row, text="E-mail:").pack(side=LEFT, padx=(0, 8))
        recipient_entry = ttk.Entry(
            recipient_row, textvariable=self.mail_recipient_var, width=42
        )
        recipient_entry.pack(side=LEFT)
        recipient_entry.bind("<Return>", lambda _event: self.add_mail_recipient())
        ttk.Button(
            recipient_row, text="Přidat", command=self.add_mail_recipient
        ).pack(side=LEFT, padx=(8, 0))
        ttk.Button(
            recipient_row, text="Smazat vybrané", command=self.delete_mail_recipients
        ).pack(side=LEFT, padx=(8, 0))

        list_frame = ttk.Frame(self.mail_tab)
        list_frame.pack(fill=X, pady=(8, 12))
        self.mail_tree = ttk.Treeview(
            list_frame,
            columns=("address",),
            show="headings",
            height=4,
            selectmode="extended",
        )
        self.mail_tree.heading("address", text="Příjemci")
        self.mail_tree.column("address", width=640, anchor="w")
        mail_scroll = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.mail_tree.yview
        )
        self.mail_tree.configure(yscrollcommand=mail_scroll.set)
        self.mail_tree.pack(side=LEFT, fill=X, expand=True)
        mail_scroll.pack(side=RIGHT, fill="y")
        self._populate_mail_recipients()

        ttk.Label(self.mail_tab, text="Text v těle mailu:").pack(anchor="w")
        self.mail_body_text = Text(
            self.mail_tab,
            height=4,
            wrap="word",
            font=("Segoe UI", 9),
            undo=True,
        )
        self.mail_body_text.pack(fill=X, pady=(5, 10))
        configured_body = self.raw.get("mail_text", "")
        if isinstance(configured_body, str):
            self.mail_body_text.insert("1.0", configured_body)

        subject_row = ttk.Frame(self.mail_tab)
        subject_row.pack(fill=X, pady=(0, 8))
        ttk.Label(subject_row, text="Předmět:").pack(side=LEFT, padx=(0, 8))
        ttk.Label(subject_row, textvariable=self.mail_subject_var).pack(side=LEFT)

        ttk.Checkbutton(
            self.mail_tab,
            text="Odesílat jen ve varných dnech",
            variable=self.mail_only_cooking_days_var,
        ).pack(anchor="w")
        ttk.Label(
            self.mail_tab,
            text=(
                "Kontroluje public.varnedny pouze pro typy stravy, které mají "
                "ve vybraných kategoriích objednávky. Hodnota dne musí být A."
            ),
            style="Hint.TLabel",
            wraplength=760,
        ).pack(anchor="w", pady=(2, 10))

        self.send_mail_button = ttk.Button(
            self.mail_tab,
            text="Vytvořit PDF a odeslat",
            style="Primary.TButton",
            command=self.send_mail,
            state="disabled",
        )
        self.send_mail_button.pack(anchor="w")
        ttk.Label(
            self.mail_tab, textvariable=self.mail_status_var, style="Hint.TLabel"
        ).pack(anchor="w", pady=(10, 0))

    def _bind_connection_changes(self) -> None:
        for variable in (
            self.host_var,
            self.port_var,
            self.dbname_var,
            self.user_var,
            self.password_var,
        ):
            variable.trace_add("write", self._invalidate_connection)

    def _bind_date_changes(self) -> None:
        for variable in (self.day_var, self.month_var, self.year_var):
            variable.trace_add("write", self._update_mail_subject)
        self._update_mail_subject()

    def _update_mail_subject(self, *_args: object) -> None:
        try:
            selected_date = self._selected_date()
        except ConfigError:
            self.mail_subject_var.set("Seznam strávníků: [neplatné datum]")
        else:
            self.mail_subject_var.set(mail_subject(selected_date))

    def _invalidate_connection(self, *_args: object) -> None:
        if self.initializing or not self.connection_ok:
            return
        self.connection_ok = False
        self.notebook.tab(self.category_tab, state="disabled")
        self.notebook.tab(self.pdf_tab, state="disabled")
        self.send_mail_button.configure(state="disabled")
        self.db_status_label.configure(
            text="Údaje se změnily – proveďte TEST znovu.", style="Error.TLabel"
        )
        self.status_var.set("Připojení je nutné znovu ověřit.")

    def _load_initial_password(self) -> None:
        database = database_parameters(self.raw)
        legacy = None
        raw_database = self.raw.get("databaze")
        if isinstance(raw_database, dict):
            legacy = raw_database.get("password")
        try:
            if isinstance(legacy, str) and legacy:
                set_password(database, legacy)
                self.raw = sanitize_config(self.raw)
                write_config(self.config_path, self.raw)
                self.password_var.set(legacy)
                self.status_var.set(
                    "Heslo bylo přesunuto z config.json do systémového trezoru."
                )
            else:
                stored = get_password(database)
                if stored:
                    self.password_var.set(stored)
        except CredentialStoreError as exc:
            self.status_var.set(str(exc))

    def _load_initial_resend_api_key(self) -> None:
        """Načte klíč z .env a případný starý zápis z configu odstraní."""
        legacy = None
        for key in ("resend_api_key", "mail_api_key", "RESEND_API_KEY"):
            value = self.raw.get(key)
            if isinstance(value, str) and value.strip():
                legacy = value.strip()
                break
        raw_mail = self.raw.get("mail")
        if legacy is None and isinstance(raw_mail, dict):
            for key in ("resend_api_key", "mail_api_key", "RESEND_API_KEY"):
                value = raw_mail.get(key)
                if isinstance(value, str) and value.strip():
                    legacy = value.strip()
                    break
        try:
            if legacy:
                set_resend_api_key(legacy)
                self.raw = sanitize_config(self.raw)
                write_config(self.config_path, self.raw)
                self.resend_api_key_var.set(legacy)
                self.status_var.set(
                    "Resend API klíč byl přesunut z configu do souboru .env."
                )
            else:
                stored = get_resend_api_key()
                if stored:
                    self.resend_api_key_var.set(stored)
        except EnvStoreError as exc:
            self.status_var.set(str(exc))

    def _collect_database(self) -> dict[str, Any]:
        host = self.host_var.get().strip()
        dbname = self.dbname_var.get().strip()
        user = self.user_var.get().strip()
        if not host or not dbname or not user:
            raise ConfigError("IP/server, název databáze a uživatel jsou povinné.")
        try:
            port = int(self.port_var.get())
        except ValueError as exc:
            raise ConfigError("Port musí být celé číslo.") from exc
        if not 1 <= port <= 65535:
            raise ConfigError("Port musí být v rozsahu 1–65535.")
        return {
            "host": host,
            "port": port,
            "dbname": dbname,
            "user": user,
            "sslmode": "prefer",
            "connect_timeout": 10,
        }

    def _selected_category_order(self) -> list[str]:
        result: list[str] = []
        for iid in self.category_tree.get_children(""):
            code = self.category_code_by_iid.get(iid)
            if code in self.selected_categories:
                result.append(code)
        if not result and not self.category_code_by_iid:
            configured = self.raw.get("povolene_kategorie", [])
            if isinstance(configured, list):
                result = [str(code) for code in configured if str(code).strip()]
        return result

    def _selected_date(self) -> date:
        try:
            return date(
                int(self.year_var.get()),
                int(self.month_var.get()),
                int(self.day_var.get()),
            )
        except ValueError as exc:
            raise ConfigError("Zvolené datum není platné.") from exc

    def _mail_body(self) -> str:
        if not hasattr(self, "mail_body_text"):
            value = self.raw.get("mail_text", "")
            return value if isinstance(value, str) else ""
        return self.mail_body_text.get("1.0", "end-1c")

    def _collect_config(self) -> dict[str, Any]:
        database = self._collect_database()
        categories = self._selected_category_order()
        if not categories:
            raise ConfigError("Vyberte alespoň jednu kategorii pro export.")
        selected_date = self._selected_date()
        try:
            menu_list = int(self.menu_list_var.get())
        except ValueError as exc:
            raise ConfigError("Číslo jídelníčku musí být celé kladné číslo.") from exc
        if menu_list < 1:
            raise ConfigError("Číslo jídelníčku musí být celé kladné číslo.")
        try:
            data_size = float(self.pdf_data_size_var.get().replace(",", "."))
            label_size = float(self.pdf_label_size_var.get().replace(",", "."))
        except ValueError as exc:
            raise ConfigError("Velikosti písma musí být čísla od 5 do 18.") from exc
        if not 5 <= data_size <= 18 or not 5 <= label_size <= 18:
            raise ConfigError("Velikosti písma musí být v rozsahu 5 až 18.")
        language = self.language_var.get().strip()
        output = self.pdf_output_var.get().strip()
        if not language or not output:
            raise ConfigError("Jazyk jídelníčku a výstupní cesta nesmí být prázdné.")
        mail_sender = normalize_recipient(self.mail_sender_var.get())

        raw = sanitize_config(self.raw)
        raw.update(
            {
                "databaze": database,
                "povolene_kategorie": categories,
                "kategor_separ": self.category_separation_var.get(),
                "dle_kategorii": self.show_categories_var.get(),
                "dle_norem": self.show_norms_var.get(),
                "datum": selected_date.strftime("%d.%m.%Y"),
                "jazyk_jidelnicku": language,
                "cislo_jidelnicku": menu_list,
                "pdf_vystup": output,
                "pdf_orientace": (
                    "na_vysku"
                    if self.pdf_orientation_var.get() == "Na výšku"
                    else "na_sirku"
                ),
                "pdf_velikost_dat": data_size,
                "pdf_velikost_popisku": label_size,
                "pdf_tucne": self.pdf_bold_var.get(),
                "mail_prijemci": list(
                    normalize_recipients(self.mail_recipients, allow_empty=True)
                ),
                "mail_text": self._mail_body(),
                "mail_jen_varne_dny": self.mail_only_cooking_days_var.get(),
                "mail_odesilatel": mail_sender,
            }
        )
        return raw

    def _run_background(
        self,
        worker: Callable[[], Any],
        success: Callable[[Any], None],
        failure: Callable[[Exception], None],
    ) -> None:
        def run() -> None:
            try:
                result = worker()
            except Exception as exc:  # Python po bloku except proměnnou exc uvolní
                self.root.after(0, lambda error=exc: failure(error))
            else:
                self.root.after(0, lambda: success(result))

        threading.Thread(target=run, daemon=True).start()

    def test_connection(self) -> None:
        try:
            database = self._collect_database()
            password = self.password_var.get()
            if not password:
                password = get_password(database) or ""
            if not password:
                raise ConfigError("Vyplňte heslo k databázi.")
        except (ConfigError, CredentialStoreError, EnvStoreError) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self.root)
            return

        self.test_button.configure(state="disabled")
        self.db_status_label.configure(text="Testuji připojení…", style="Hint.TLabel")
        self.status_var.set("Probíhá test připojení k databázi.")

        def worker() -> tuple[list[tuple[str, str]], str]:
            try:
                import psycopg
            except ImportError as exc:
                raise RuntimeError(
                    "Chybí psycopg. Nainstalujte requirements.txt."
                ) from exc
            connection_values = dict(database, password=password)
            with psycopg.connect(**connection_values) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT current_database()")
                    database_name = str(cursor.fetchone()[0])
                    cursor.execute(
                        """
                        SELECT BTRIM(oznaceni), COALESCE(NULLIF(BTRIM(nazev), ''), '')
                        FROM public.kategor
                        WHERE NULLIF(BTRIM(oznaceni), '') IS NOT NULL
                        ORDER BY LOWER(BTRIM(oznaceni)), BTRIM(oznaceni)
                        """
                    )
                    categories = [(str(code), str(name)) for code, name in cursor.fetchall()]
            set_password(database, password)
            return categories, database_name

        def success(result: tuple[list[tuple[str, str]], str]) -> None:
            categories, database_name = result
            self.test_button.configure(state="normal")
            self.connection_ok = True
            self.raw["databaze"] = database
            write_config(self.config_path, self.raw)
            self._populate_categories(categories)
            self.notebook.tab(self.category_tab, state="normal")
            self.notebook.tab(self.pdf_tab, state="normal")
            self.send_mail_button.configure(state="normal")
            self.db_status_label.configure(
                text=f"Připojení je v pořádku: {database_name} ({len(categories)} kategorií).",
                style="Success.TLabel",
            )
            self.status_var.set("Připojení ověřeno. Můžete vybrat kategorie.")

        def failure(exc: Exception) -> None:
            self.test_button.configure(state="normal")
            self.connection_ok = False
            self.db_status_label.configure(
                text=f"Připojení selhalo: {exc}", style="Error.TLabel"
            )
            self.status_var.set("Připojení k databázi se nepodařilo.")
            messagebox.showerror(APP_TITLE, str(exc), parent=self.root)

        self._run_background(worker, success, failure)

    def _populate_categories(self, categories: Sequence[tuple[str, str]]) -> None:
        self.category_tree.delete(*self.category_tree.get_children(""))
        self.category_code_by_iid.clear()
        configured = self.raw.get("povolene_kategorie", [])
        configured_set = {
            str(item) for item in configured if isinstance(item, (str, int))
        }
        self.selected_categories = {
            code for code, _name in categories if code in configured_set
        }
        for index, (code, name) in enumerate(categories):
            iid = f"category-{index}"
            included = code in self.selected_categories
            self.category_code_by_iid[iid] = code
            self.category_tree.insert(
                "",
                END,
                iid=iid,
                values=("✓" if included else "", code, name or "[bez názvu]"),
                tags=("included",) if included else (),
            )
        self._update_category_count()

    def _toggle_category_click(self, event: Any) -> str | None:
        iid = self.category_tree.identify_row(event.y)
        if not iid:
            return None
        code = self.category_code_by_iid[iid]
        if code in self.selected_categories:
            self.selected_categories.remove(code)
            self.category_tree.set(iid, "selected", "")
            self.category_tree.item(iid, tags=())
        else:
            self.selected_categories.add(code)
            self.category_tree.set(iid, "selected", "✓")
            self.category_tree.item(iid, tags=("included",))
        self._update_category_count()
        return "break"

    def select_all_categories(self) -> None:
        self.selected_categories = set(self.category_code_by_iid.values())
        for iid in self.category_tree.get_children(""):
            self.category_tree.set(iid, "selected", "✓")
            self.category_tree.item(iid, tags=("included",))
        self._update_category_count()

    def clear_categories(self) -> None:
        self.selected_categories.clear()
        for iid in self.category_tree.get_children(""):
            self.category_tree.set(iid, "selected", "")
            self.category_tree.item(iid, tags=())
        self._update_category_count()

    def _update_category_count(self) -> None:
        total = len(self.category_code_by_iid)
        self.category_count_var.set(f"Vybráno: {len(self.selected_categories)} / {total}")

    def _populate_mail_recipients(self) -> None:
        configured = self.raw.get("mail_prijemci", [])
        try:
            self.mail_recipients = list(
                normalize_recipients(configured, allow_empty=True)
            )
        except ConfigError:
            self.mail_recipients = []
        self._refresh_mail_tree()

    def _refresh_mail_tree(self) -> None:
        if not hasattr(self, "mail_tree"):
            return
        self.mail_tree.delete(*self.mail_tree.get_children(""))
        for index, address in enumerate(self.mail_recipients):
            self.mail_tree.insert("", END, iid=f"mail-{index}", values=(address,))

    def add_mail_recipient(self) -> None:
        try:
            address = normalize_recipient(self.mail_recipient_var.get())
        except ConfigError as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self.root)
            return
        if address.casefold() not in {
            item.casefold() for item in self.mail_recipients
        }:
            self.mail_recipients.append(address)
            self._refresh_mail_tree()
        self.mail_recipient_var.set("")

    def delete_mail_recipients(self) -> None:
        selected = {
            self.mail_tree.item(iid, "values")[0]
            for iid in self.mail_tree.selection()
        }
        self.mail_recipients = [
            item for item in self.mail_recipients if item not in selected
        ]
        self._refresh_mail_tree()

    def save_settings(self) -> None:
        try:
            raw = self._collect_config()
            api_key = self.resend_api_key_var.get().strip()
            if api_key:
                set_resend_api_key(api_key)
            write_config(self.config_path, raw)
            self.raw = raw
        except (ConfigError, CredentialStoreError, EnvStoreError) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self.root)
            return
        self.status_var.set(f"Nastavení uloženo: {self.config_path.name}")

    def generate_pdf(self) -> None:
        if not self.connection_ok:
            messagebox.showwarning(
                APP_TITLE,
                "Nejprve proveďte úspěšný TEST připojení.",
                parent=self.root,
            )
            return
        try:
            raw = self._collect_config()
            password = self.password_var.get()
            if password:
                set_password(raw["databaze"], password)
            api_key = self.resend_api_key_var.get().strip()
            if api_key:
                set_resend_api_key(api_key)
            write_config(self.config_path, raw)
            self.raw = raw
        except (ConfigError, CredentialStoreError, EnvStoreError) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self.root)
            return

        self.generate_button.configure(state="disabled")
        self.pdf_status_var.set("Načítám data a vytvářím PDF…")
        self.status_var.set("Probíhá tvorba PDF.")

        def worker() -> Path:
            config = load_config(self.config_path)
            report = fetch_report(config)
            return create_pdf(config, report)

        def success(path: Path) -> None:
            self.generate_button.configure(state="normal")
            self.last_pdf = path
            self.open_pdf_button.configure(state="normal")
            self.pdf_status_var.set(f"PDF vytvořeno: {path}")
            self.status_var.set("PDF bylo vytvořeno a otevřeno.")
            try:
                open_document(path)
            except Exception as exc:
                messagebox.showwarning(
                    APP_TITLE,
                    f"PDF bylo vytvořeno, ale nepodařilo se otevřít:\n{exc}",
                    parent=self.root,
                )

        def failure(exc: Exception) -> None:
            self.generate_button.configure(state="normal")
            self.pdf_status_var.set(f"Vytvoření PDF selhalo: {exc}")
            self.status_var.set("PDF se nepodařilo vytvořit.")
            messagebox.showerror(APP_TITLE, str(exc), parent=self.root)

        self._run_background(worker, success, failure)

    def send_mail(self) -> None:
        if not self.connection_ok:
            messagebox.showwarning(
                APP_TITLE,
                "Nejprve proveďte úspěšný TEST připojení.",
                parent=self.root,
            )
            return
        try:
            recipients = normalize_recipients(self.mail_recipients)
            raw = self._collect_config()
            api_key = self.resend_api_key_var.get().strip()
            if not api_key:
                api_key = get_resend_api_key() or ""
            if not api_key:
                raise ConfigError("Zadejte Resend API klíč.")
            password = self.password_var.get()
            if password:
                set_password(raw["databaze"], password)
            set_resend_api_key(api_key)
            sender_email = normalize_recipient(self.mail_sender_var.get())
            write_config(self.config_path, raw)
            self.raw = raw
        except (ConfigError, CredentialStoreError, EnvStoreError) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self.root)
            return

        if not messagebox.askyesno(
            APP_TITLE,
            (
                f"Opravdu vytvořit PDF a odeslat ho {len(recipients)} "
                f"příjemcům?\n\nPředmět: {mail_subject(self._selected_date())}"
            ),
            parent=self.root,
        ):
            return

        self.send_mail_button.configure(state="disabled")
        self.mail_status_var.set("Kontroluji data a připravuji mail…")
        self.status_var.set("Probíhá příprava mailového exportu.")
        only_cooking_days = self.mail_only_cooking_days_var.get()
        body = self._mail_body()

        def worker() -> dict[str, Any]:
            config = load_config(self.config_path)
            statuses = fetch_cooking_status(config) if only_cooking_days else ()
            if only_cooking_days and not should_send_on_cooking_day(statuses):
                return {
                    "skipped": True,
                    "message": cooking_status_message(statuses),
                }

            report = fetch_report(config)
            path = create_pdf(config, report)
            dispatch = send_pdf_via_mailsender(
                recipients,
                mail_subject(config.report_date),
                body,
                path,
                api_key=api_key,
                sender_email=sender_email,
            )
            return {
                "skipped": False,
                "path": path,
                "dispatch": dispatch,
                "cooking": cooking_status_message(statuses) if statuses else None,
            }

        def success(result: dict[str, Any]) -> None:
            self.send_mail_button.configure(state="normal")
            if result["skipped"]:
                message = str(result["message"])
                self.mail_status_var.set(f"Neodesláno: {message}")
                self.status_var.set("Mail nebyl odeslán – není relevantní varný den.")
                messagebox.showinfo(APP_TITLE, message, parent=self.root)
                return

            path = Path(result["path"])
            dispatch = result["dispatch"]
            self.last_pdf = path
            self.open_pdf_button.configure(state="normal")
            detail = f" ({dispatch.detail})" if dispatch.detail else ""
            self.mail_status_var.set(
                f"Odesláno {len(dispatch.recipients)} příjemcům{detail}."
            )
            self.pdf_status_var.set(f"PDF vytvořeno: {path}")
            self.status_var.set("PDF bylo vytvořeno a mail odeslán.")

        def failure(exc: Exception) -> None:
            self.send_mail_button.configure(state="normal")
            self.mail_status_var.set(f"Odeslání selhalo: {exc}")
            self.status_var.set("Mail se nepodařilo odeslat.")
            messagebox.showerror(APP_TITLE, str(exc), parent=self.root)

        self._run_background(worker, success, failure)

    def open_last_pdf(self) -> None:
        if self.last_pdf and self.last_pdf.is_file():
            open_document(self.last_pdf)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="UI pro AutoReport")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("config.json"),
        help="cesta ke config.json",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = Tk()
    try:
        StravovaciApp(root, args.config)
    except Exception as exc:
        messagebox.showerror(APP_TITLE, str(exc), parent=root)
        root.destroy()
        return 2
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
