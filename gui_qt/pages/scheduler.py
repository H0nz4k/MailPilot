"""Administrace → Plánovač: seznam úloh a jednoduchý editor."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from gui_qt.models import PlannedJobModel
from gui_qt.theme import Palette, UiMetrics
from gui_qt.widgets.common import (
    field_label,
    ghost_button,
    page_body,
    primary_button,
    scroll_area,
    secondary_button,
    section_label,
    size_choice,
    size_input,
    SmartTimeEdit,
)
from gui_qt.widgets.empty_state import TableEmptyState
from services.scheduler import (
    ACTION_CUSTOM,
    ACTION_LABELS,
    KNOWN_ACTIONS,
    SCHEDULE_LABELS,
    PlannedJob,
    build_job,
    default_launcher_path,
    ensure_unique,
)
from stravovaci_sestava import ConfigError


EMPTY_TITLE = "Zatím není naplánovaná žádná úloha"
EMPTY_HINT = ""


class SchedulerPage(QWidget):
    """Editace ``planovac.json``; zápis na disk provádí controller."""

    save_requested = Signal(list)
    failed = Signal(str)
    runtime_start_requested = Signal()
    runtime_stop_requested = Signal()
    runtime_restart_requested = Signal()
    runtime_open_log_requested = Signal()
    service_install_requested = Signal()
    service_remove_requested = Signal()
    service_restart_requested = Signal()
    run_job_requested = Signal(object)

    def __init__(
        self,
        metrics: UiMetrics,
        parent: QWidget | None = None,
        *,
        palette: Palette,
    ) -> None:
        super().__init__(parent)
        self._metrics = metrics
        self._jobs: list[PlannedJob] = []
        self._directory: Path | None = None
        self._service_name_value = "MailPilot_denniprehled"
        self._nssm_path_value = ""

        content, layout = page_body(metrics, "Plánovač")
        layout.setContentsMargins(
            metrics.margin, metrics.small_gap, metrics.margin, metrics.small_gap
        )
        layout.setSpacing(metrics.normal_gap)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(metrics.normal_gap)
        top.addWidget(section_label("Naplánované úlohy"))
        self._summary = QLabel("")
        self._summary.setProperty("role", "hint")
        top.addWidget(self._summary)
        top.addStretch(1)
        layout.addLayout(top)

        self._model = PlannedJobModel()
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.setSelectionMode(QTableView.SingleSelection)
        self._table.setEditTriggers(QTableView.NoEditTriggers)
        self._table.setWordWrap(False)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(metrics.row_height)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, PlannedJobModel.COLUMNS):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setHighlightSections(False)
        header.setFixedHeight(metrics.control_height - metrics.px(4))
        self._table.setMinimumHeight(metrics.px(130))
        layout.addWidget(self._table, 1)
        self._empty_state = TableEmptyState(
            self._table, metrics, palette, EMPTY_TITLE, EMPTY_HINT
        )

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(metrics.small_gap)
        self._run_selected = secondary_button("Spustit")
        self._run_selected.clicked.connect(self._run_selected_job)
        self._toggle_selected = ghost_button("Povolit / Zakázat")
        self._toggle_selected.clicked.connect(self._toggle_selected_job)
        self._remove_selected_btn = ghost_button("Odstranit")
        self._remove_selected_btn.clicked.connect(self._remove_selected)
        controls.addWidget(self._run_selected)
        controls.addWidget(self._toggle_selected)
        controls.addWidget(self._remove_selected_btn)
        controls.addStretch(1)
        layout.addLayout(controls)
        self._table.selectionModel().selectionChanged.connect(
            lambda *_: self._update_selection_actions()
        )

        layout.addWidget(section_label("Nová úloha"))
        layout.addLayout(self._build_editor())

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(metrics.normal_gap)
        add = secondary_button("Přidat úlohu")
        add.clicked.connect(self._add_job)
        self._save = primary_button("Uložit plánovač")
        self._save.clicked.connect(self._emit_save)
        actions.addWidget(add)
        actions.addStretch(1)
        actions.addWidget(self._save)
        layout.addLayout(actions)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll_area(content, self, metrics))
        self._update_view()

    # ------------------------------------------------------------------
    # Stavba rozvržení
    # ------------------------------------------------------------------
    def _build_editor(self) -> QGridLayout:
        metrics = self._metrics
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(metrics.normal_gap)
        grid.setVerticalSpacing(metrics.small_gap)
        grid.setColumnMinimumWidth(0, metrics.label_column)

        self._name = size_input(QLineEdit(), metrics, 210)
        self._name.setPlaceholderText("Denní stav")

        self._action = QComboBox()
        for key in KNOWN_ACTIONS:
            self._action.addItem(ACTION_LABELS[key], key)
        size_choice(self._action, metrics, 170)
        self._action.currentIndexChanged.connect(self._sync_launcher)

        self._schedule = QComboBox()
        for key, label in SCHEDULE_LABELS.items():
            self._schedule.addItem(label, key)
        size_choice(self._schedule, metrics, 170)
        self._schedule.currentIndexChanged.connect(self._sync_schedule_fields)

        self._time = SmartTimeEdit()
        size_input(self._time, metrics, 94)
        self._minute = QSpinBox()
        self._minute.setRange(0, 59)
        size_input(self._minute, metrics, 84)
        self._minutes = QSpinBox()
        self._minutes.setRange(1, 1440)
        self._minutes.setValue(15)
        size_input(self._minutes, metrics, 94)

        self._launcher = QLineEdit()
        self._launcher.setMinimumWidth(metrics.px(260))
        self._launcher.setMaximumWidth(metrics.px(380))
        browse = secondary_button("Procházet…")
        browse.clicked.connect(self._pick_launcher)

        self._enabled = QCheckBox("Úloha je aktivní")
        self._enabled.setChecked(True)

        grid.addWidget(field_label("Název", self._name), 0, 0)
        grid.addWidget(self._name, 0, 1)
        grid.addWidget(field_label("Funkce", self._action), 0, 2)
        grid.addWidget(self._action, 0, 3)

        grid.addWidget(field_label("Plán", self._schedule), 1, 0)
        grid.addWidget(self._schedule, 1, 1)
        self._time_label = field_label("Čas", self._time)
        self._minute_label = field_label("Minuta", self._minute)
        self._minutes_label = field_label("Interval (min)", self._minutes)
        grid.addWidget(self._time_label, 1, 2)
        grid.addWidget(self._time, 1, 3)
        grid.addWidget(self._minute_label, 2, 2)
        grid.addWidget(self._minute, 2, 3)
        grid.addWidget(self._minutes_label, 3, 2)
        grid.addWidget(self._minutes, 3, 3)

        launcher_row = QHBoxLayout()
        launcher_row.setContentsMargins(0, 0, 0, 0)
        launcher_row.setSpacing(metrics.small_gap)
        launcher_row.addWidget(self._launcher, 1)
        launcher_row.addWidget(browse)
        grid.addWidget(field_label("Spouštěč", self._launcher), 4, 0)
        grid.addLayout(launcher_row, 4, 1, 1, 3)
        grid.addWidget(self._enabled, 5, 1, 1, 3)
        grid.setColumnStretch(4, 1)

        self._sync_schedule_fields()
        return grid

    # ------------------------------------------------------------------
    # Rozhraní pro controller
    # ------------------------------------------------------------------
    def set_jobs(self, jobs: Sequence[PlannedJob], directory: Path | None = None) -> None:
        self._jobs = list(jobs)
        self._directory = directory
        self._sync_launcher()
        self._update_view()

    def jobs(self) -> list[PlannedJob]:
        return list(self._jobs)

    def mark_saved(self) -> None:
        self._save.setEnabled(False)

    def set_runtime_status(self, text: str, *, running: bool) -> None:
        del text, running

    def set_service_status(self, text: str, *, running: bool, installed: bool = True) -> None:
        del text, running, installed

    def set_service_config(self, *, service_name: str, nssm_path: str) -> None:
        self._service_name_value = service_name.strip() or "MailPilot_denniprehled"
        self._nssm_path_value = nssm_path.strip()

    def service_name(self) -> str:
        return self._service_name_value

    def nssm_path(self) -> str:
        return self._nssm_path_value

    def focus_default(self) -> None:
        self._name.setFocus()

    # ------------------------------------------------------------------
    # Interakce
    # ------------------------------------------------------------------
    def _update_view(self) -> None:
        self._model.set_jobs(tuple(self._jobs))
        count = len(self._jobs)
        active = sum(1 for job in self._jobs if job.enabled)
        self._summary.setText(
            f"· {count} úloh · {active} aktivních" if count else ""
        )
        self._empty_state.setVisible(count == 0)
        self._update_selection_actions()

    def _selected_row(self) -> int:
        row = self._table.currentIndex().row()
        return row if 0 <= row < len(self._jobs) else -1

    def _update_selection_actions(self) -> None:
        row = self._selected_row()
        has_selection = row >= 0
        self._run_selected.setEnabled(has_selection)
        self._toggle_selected.setEnabled(has_selection)
        self._remove_selected_btn.setEnabled(has_selection)
        if has_selection:
            enabled = self._jobs[row].enabled
            self._toggle_selected.setText(
                "Zakázat" if enabled else "Povolit"
            )
        else:
            self._toggle_selected.setText("Povolit / Zakázat")

    def _sync_schedule_fields(self) -> None:
        kind = str(self._schedule.currentData())
        for widget, visible in (
            (self._time, kind == "daily"),
            (self._time_label, kind == "daily"),
            (self._minute, kind == "hourly"),
            (self._minute_label, kind == "hourly"),
            (self._minutes, kind == "interval"),
            (self._minutes_label, kind == "interval"),
        ):
            widget.setVisible(visible)

    def _sync_launcher(self) -> None:
        action = str(self._action.currentData())
        if action == ACTION_CUSTOM:
            return
        self._launcher.setText(str(default_launcher_path(action, self._directory)))

    def _pick_launcher(self) -> None:
        start = self._launcher.text().strip() or str(self._directory or Path("."))
        chosen, _filter = QFileDialog.getOpenFileName(
            self, "Vyberte spouštěč", start, "Spustitelné (*.exe *.bat);;Vše (*)"
        )
        if chosen:
            self._launcher.setText(chosen)

    def _add_job(self) -> None:
        qtime = self._time.time()
        try:
            job = build_job(
                name=self._name.text(),
                action=str(self._action.currentData()),
                schedule_type=str(self._schedule.currentData()),
                launcher=self._launcher.text(),
                enabled=self._enabled.isChecked(),
                time=f"{qtime.hour():02d}:{qtime.minute():02d}",
                minute=int(self._minute.value()),
                minutes=int(self._minutes.value()),
                config_directory=self._directory,
            )
            ensure_unique(self._jobs, job)
        except ConfigError as exc:
            self.failed.emit(str(exc))
            return
        self._jobs.append(job)
        self._name.clear()
        self._save.setEnabled(True)
        self._update_view()
        row = len(self._jobs) - 1
        if row >= 0:
            self._table.selectRow(row)

    def _remove_selected(self) -> None:
        row = self._selected_row()
        if row < 0 or row >= len(self._jobs):
            self.failed.emit("Nejdřív vyberte úlohu v seznamu.")
            return
        name = self._jobs[row].name
        answer = QMessageBox.question(
            self,
            "Odstranit úlohu",
            f"Opravdu chcete odstranit úlohu „{name}“?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        del self._jobs[row]
        self._save.setEnabled(True)
        self._update_view()
        if self._jobs:
            self._table.selectRow(min(row, len(self._jobs) - 1))
        else:
            self._table.clearSelection()

    def _toggle_selected_job(self) -> None:
        row = self._selected_row()
        if row < 0:
            self.failed.emit("Nejdřív vyberte úlohu v seznamu.")
            return
        current = self._jobs[row]
        self._jobs[row] = PlannedJob(
            name=current.name,
            action=current.action,
            path=current.path,
            schedule_type=current.schedule_type,
            time=current.time,
            minute=current.minute,
            minutes=current.minutes,
            enabled=not current.enabled,
        )
        self._save.setEnabled(True)
        self._update_view()
        self._table.selectRow(row)

    def _run_selected_job(self) -> None:
        row = self._selected_row()
        if row < 0:
            self.failed.emit("Nejdřív vyberte úlohu v seznamu.")
            return
        self.run_job_requested.emit(self._jobs[row])

    def _emit_save(self) -> None:
        self.save_requested.emit(list(self._jobs))
