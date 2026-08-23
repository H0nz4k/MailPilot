"""Administrace → Pokročilé: mapování Z 17-01, cesty a uložení hesel."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui_qt.dialogs.categories import CategoryDialog
from gui_qt.theme import UiMetrics
from gui_qt.widgets.common import (
    ElidedLabel,
    StatusDot,
    field_label,
    ghost_button,
    hint,
    page_body,
    scroll_area,
    secondary_button,
    section_label,
)
from services.environment import application_files, secret_locations
from services.jidelnasql_warning import DEFAULT_TEMPLATE_PATH
from services.special import row_choices


class AdvancedPage(QWidget):
    """Nastavení, která jinde nemají místo, a přehled souborů."""

    open_path_requested = Signal(Path)
    mapping_changed = Signal()
    warning_show_requested = Signal()
    warning_show_custom_requested = Signal()
    warning_clear_requested = Signal()

    def __init__(self, metrics: UiMetrics, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._metrics = metrics
        self._mapping: dict[str, tuple[str, ...]] = {}
        self._supplement: tuple[str, ...] = ()
        self._category_options: tuple[tuple[str, str], ...] = ()
        self._mapping_labels: dict[str, QLabel] = {}
        self._show_warning_btn: QPushButton | None = None
        self._show_custom_warning_btn: QPushButton | None = None
        self._clear_warning_btn: QPushButton | None = None

        content, layout = page_body(metrics, "Pokročilé", max_width=980)

        layout.addWidget(section_label("Mapování kategorií pro Z 17-01"))
        layout.addWidget(
            hint(
                "Určuje, do kterého řádku výkazu Z 17-01 patří jednotlivé "
                "kategorie strávníků. Nevyplněné řádky se odhadují podle "
                "názvu kategorie."
            )
        )
        self._mapping_grid = QGridLayout()
        self._mapping_grid.setContentsMargins(0, 0, 0, 0)
        self._mapping_grid.setHorizontalSpacing(metrics.normal_gap)
        self._mapping_grid.setVerticalSpacing(metrics.small_gap)
        self._mapping_grid.setColumnStretch(0, 3)
        self._mapping_grid.setColumnStretch(1, 2)
        layout.addLayout(self._mapping_grid)

        self._supplement_label = ElidedLabel("—")
        supplement_row = QGridLayout()
        supplement_row.setContentsMargins(0, 0, 0, 0)
        supplement_row.setHorizontalSpacing(metrics.normal_gap)
        supplement_row.addWidget(
            field_label("Doplňková jídla v rámci vyhlášky"), 0, 0
        )
        supplement_row.addWidget(self._supplement_label, 0, 1)
        change_supplement = secondary_button("Změnit…")
        change_supplement.clicked.connect(self._edit_supplement)
        supplement_row.addWidget(change_supplement, 0, 2)
        supplement_row.setColumnStretch(0, 3)
        supplement_row.setColumnStretch(1, 2)
        layout.addLayout(supplement_row)

        layout.addWidget(section_label("Soubory"))
        self._files = QGridLayout()
        self._files.setContentsMargins(0, 0, 0, 0)
        self._files.setHorizontalSpacing(metrics.normal_gap)
        self._files.setVerticalSpacing(metrics.small_gap)
        self._files.setColumnMinimumWidth(0, metrics.label_column)
        self._files.setColumnStretch(2, 1)
        layout.addLayout(self._files)

        layout.addWidget(section_label("Hesla a klíče"))
        self._secrets = QVBoxLayout()
        self._secrets.setContentsMargins(0, 0, 0, 0)
        self._secrets.setSpacing(metrics.px(2))
        layout.addLayout(self._secrets)

        layout.addWidget(section_label("JídelnaSQL dashboard warning"))
        self._warning_enabled = QCheckBox(
            "Při selhání automatického mailu zobrazit varování v JídelnaSQL"
        )
        self._warning_enabled.toggled.connect(lambda _checked: self.mapping_changed.emit())
        layout.addWidget(self._warning_enabled)
        self._warning_path = ElidedLabel(str(DEFAULT_TEMPLATE_PATH))
        self._warning_path.setToolTip(str(DEFAULT_TEMPLATE_PATH))
        warning_row = QGridLayout()
        warning_row.setContentsMargins(0, 0, 0, 0)
        warning_row.setHorizontalSpacing(metrics.normal_gap)
        warning_row.addWidget(field_label("Soubor dashboardu"), 0, 0)
        warning_row.addWidget(self._warning_path, 0, 1)
        pick_warning = secondary_button("Procházet…")
        pick_warning.clicked.connect(self._pick_warning_template)
        warning_row.addWidget(pick_warning, 0, 2)
        layout.addLayout(warning_row)
        warning_actions = QGridLayout()
        warning_actions.setContentsMargins(0, 0, 0, 0)
        warning_actions.setHorizontalSpacing(metrics.normal_gap)
        show_warning = secondary_button("Test: Show warning")
        show_warning.setToolTip(
            "Ručně vloží warning blok do dashboard.template.html."
        )
        show_warning.clicked.connect(self.warning_show_requested.emit)
        clear_warning = ghost_button("Test: Clear warning")
        clear_warning.setToolTip(
            "Ručně odstraní warning blok z dashboard.template.html."
        )
        clear_warning.clicked.connect(self.warning_clear_requested.emit)
        show_custom_warning = secondary_button("Test: Show sample error…")
        show_custom_warning.setToolTip(
            "Vyžádá text chyby a vloží warning s vlastním popisem."
        )
        show_custom_warning.clicked.connect(
            self.warning_show_custom_requested.emit
        )
        self._show_warning_btn = show_warning
        self._show_custom_warning_btn = show_custom_warning
        self._clear_warning_btn = clear_warning
        warning_actions.addWidget(show_warning, 0, 1)
        warning_actions.addWidget(show_custom_warning, 0, 2)
        warning_actions.addWidget(clear_warning, 0, 3)
        warning_actions.setColumnStretch(4, 1)
        layout.addLayout(warning_actions)
        layout.addWidget(
            hint(
                "Vkládá / odstraňuje blok mezi značkami AUTOREPORT_AUTOMAIL_BEGIN "
                "a AUTOREPORT_AUTOMAIL_END v dashboard.template.html. "
                "Výchozí umístění je C:\\Gastro\\Programy\\Templates."
                "\n\nAutomatické pravidlo:\n"
                "1) Warning se zobrazí při chybě automatického exportu.\n"
                "2) Warning se nespouští při stavu SKIP (např. ne-varný den).\n"
                "3) Warning se odstraní po úspěšném automatickém odeslání."
            )
        )

        layout.addStretch(1)
        layout.addWidget(
            hint(
                "Nastavení sdílí desktopová i původní verze aplikace, "
                "takže se změny projeví v obou."
            )
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll_area(content, self, metrics))
        self._build_mapping_rows()
        self.set_warning_active(False)

    # ------------------------------------------------------------------
    # Mapování Z 17-01
    # ------------------------------------------------------------------
    def _build_mapping_rows(self) -> None:
        for row, (code, label) in enumerate(row_choices()):
            # Názvy řádků výkazu jsou dlouhé; při 160 % se musí umět zkrátit.
            caption = ElidedLabel(f"{code} · {label}")
            caption.setProperty("role", "fieldLabel")
            caption.setToolTip(f"{code} · {label}")
            value = ElidedLabel("—")
            button = secondary_button("Změnit…")
            button.clicked.connect(
                lambda _checked=False, key=code: self._edit_row(key)
            )
            self._mapping_grid.addWidget(caption, row, 0)
            self._mapping_grid.addWidget(value, row, 1)
            self._mapping_grid.addWidget(button, row, 2)
            self._mapping_labels[code] = value

    def set_mapping(
        self,
        mapping: dict[str, Sequence[str]],
        supplement_rows: Sequence[str],
        categories: Sequence[tuple[str, str]] = (),
    ) -> None:
        self._mapping = {
            code: tuple(values) for code, values in mapping.items()
        }
        self._supplement = tuple(supplement_rows)
        if categories:
            self._category_options = tuple(categories)
        self._refresh_mapping()

    def mapping(self) -> dict[str, tuple[str, ...]]:
        return dict(self._mapping)

    def supplement_rows(self) -> tuple[str, ...]:
        return tuple(self._supplement)

    def _refresh_mapping(self) -> None:
        for code, label in self._mapping_labels.items():
            values = self._mapping.get(code, ())
            label.setText(", ".join(values) if values else "—")
            label.setToolTip(", ".join(values))
        names = ", ".join(self._supplement) if self._supplement else "—"
        self._supplement_label.setText(names)

    def _edit_row(self, code: str) -> None:
        options = self._category_options or tuple(
            (value, "") for value in self._mapping.get(code, ())
        )
        dialog = CategoryDialog(
            options,
            self._mapping.get(code, ()),
            self._metrics,
            self,
            title=f"Kategorie pro řádek {code}",
        )
        if dialog.exec() != CategoryDialog.Accepted:
            return
        self._mapping[code] = dialog.selected_codes()
        self._refresh_mapping()
        self.mapping_changed.emit()

    def _edit_supplement(self) -> None:
        dialog = CategoryDialog(
            row_choices(),
            self._supplement,
            self._metrics,
            self,
            title="Řádky s doplňkovými jídly v rámci vyhlášky",
        )
        if dialog.exec() != CategoryDialog.Accepted:
            return
        self._supplement = dialog.selected_codes()
        self._refresh_mapping()
        self.mapping_changed.emit()

    # ------------------------------------------------------------------
    # Soubory a hesla
    # ------------------------------------------------------------------
    def set_context(self, config_path: Path, database: dict[str, Any]) -> None:
        """Naplní cesty podle skutečného umístění nastavení."""
        self._clear(self._files)
        self._clear(self._secrets)

        for row, entry in enumerate(application_files(config_path)):
            dot = StatusDot(self, self._metrics)
            dot.set_state("statusOk" if entry.exists else "")
            dot.setToolTip("Existuje" if entry.exists else "Zatím nevznikl")
            path_label = ElidedLabel(str(entry.path))
            path_label.setToolTip(f"{entry.path}\n{entry.note}")

            open_button = ghost_button("Otevřít složku")
            open_button.clicked.connect(
                lambda _checked=False, path=entry.path: self.open_path_requested.emit(
                    path
                )
            )
            self._files.addWidget(field_label(entry.label), row, 0)
            self._files.addWidget(dot, row, 1)
            self._files.addWidget(path_label, row, 2)
            self._files.addWidget(open_button, row, 3)

        for line in secret_locations(database):
            self._secrets.addWidget(hint(line))

    def set_category_options(self, options: Sequence[tuple[str, str]]) -> None:
        self._category_options = tuple(options)

    def focus_default(self) -> None:
        self.setFocus()

    def set_warning_settings(self, *, enabled: bool, template_path: Path) -> None:
        self._warning_enabled.blockSignals(True)
        self._warning_enabled.setChecked(bool(enabled))
        self._warning_enabled.blockSignals(False)
        text = str(template_path)
        self._warning_path.setText(text)
        self._warning_path.setToolTip(text)

    def warning_enabled(self) -> bool:
        return self._warning_enabled.isChecked()

    def warning_template_path(self) -> Path:
        full = self._warning_path.full_text().strip()
        if not full or full == "—":
            return DEFAULT_TEMPLATE_PATH
        return Path(full)

    def _pick_warning_template(self) -> None:
        current = self.warning_template_path()
        start = current if current.suffix.lower() == ".html" else current.parent
        if not str(start).strip():
            start = DEFAULT_TEMPLATE_PATH.parent
        chosen, _filter = QFileDialog.getOpenFileName(
            self,
            "Vyberte dashboard.template.html",
            str(start),
            "Dashboard šablona (*.html);;Všechny soubory (*)",
        )
        if not chosen:
            return
        path = Path(chosen)
        self._warning_path.setText(str(path))
        self._warning_path.setToolTip(str(path))
        self.mapping_changed.emit()

    def set_warning_active(self, active: bool) -> None:
        show = self._show_warning_btn
        show_custom = self._show_custom_warning_btn
        clear = self._clear_warning_btn
        if show is None or show_custom is None or clear is None:
            return
        if active:
            danger_style = (
                "QPushButton {"
                " background:#FDECEC; border:1px solid #D64545; color:#8B1E1E; "
                "font-weight:600; }"
            )
            clear_style = (
                "QPushButton {"
                " background:#EAF8EE; border:1px solid #2E8B57; color:#1D5F3B; "
                "font-weight:600; }"
            )
            show.setStyleSheet(danger_style)
            show_custom.setStyleSheet(danger_style)
            clear.setStyleSheet(clear_style)
        else:
            show.setStyleSheet("")
            show_custom.setStyleSheet("")
            clear.setStyleSheet("")

    @staticmethod
    def _clear(layout) -> None:  # noqa: ANN001 - Qt API
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
