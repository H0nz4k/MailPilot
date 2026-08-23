"""Modely Qt pro tabulková zobrazení."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from services.daily import OverviewRow
from services.scheduler import (
    ACTION_LABELS,
    PlannedJob,
    describe_command,
    describe_next_run,
    describe_schedule,
)


class OverviewModel(QAbstractTableModel):
    """Souhrn porcí podle druhu stravy a jídelníčku."""

    HEADERS = ("Druh stravy", "Jídelníček", "Jídlo", "Porcí")

    def __init__(self, rows: tuple[OverviewRow, ...] = ()) -> None:
        super().__init__()
        self._rows: tuple[OverviewRow, ...] = tuple(rows)

    def set_rows(self, rows: tuple[OverviewRow, ...]) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):  # noqa: ANN201
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        column = index.column()
        if role == Qt.DisplayRole:
            if column == 0:
                return row.meal_type
            if column == 1:
                return str(row.menu)
            if column == 2:
                return row.meal_name
            return str(row.portions)
        if role == Qt.TextAlignmentRole and column in (1, 3):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ToolTipRole and column == 2:
            return row.meal_name
        return None

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ):  # noqa: ANN201
        if orientation != Qt.Horizontal:
            return None
        if role == Qt.DisplayRole:
            return self.HEADERS[section]
        if role == Qt.TextAlignmentRole:
            if section in (1, 3):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return None


class RecipientModel(QAbstractTableModel):
    """Strávníci vybraných tříd nebo kategorií a jejich e-maily."""

    HEADERS = ("Strávník", "Třída", "Kategorie", "E-mail")
    MISSING = "chybí e-mail"

    def __init__(self, rows: tuple[tuple[str, str, str, str], ...] = ()) -> None:
        super().__init__()
        self._rows = tuple(rows)

    def set_rows(self, rows: tuple[tuple[str, str, str, str], ...]) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):  # noqa: ANN201
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        value = row[index.column()]
        if role == Qt.DisplayRole:
            return value
        if role == Qt.ToolTipRole:
            if value == self.MISSING:
                return "Strávník nemá v databázi platnou e-mailovou adresu."
            return value
        return None

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ):  # noqa: ANN201
        if orientation != Qt.Horizontal:
            return None
        if role == Qt.DisplayRole:
            return self.HEADERS[section]
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return None


class PlannedJobModel(QAbstractTableModel):
    """Naplánované úlohy včetně nejbližšího spuštění."""

    HEADERS = ("Úloha", "Funkce", "Plán", "Příští spuštění", "Stav")
    COLUMNS = len(HEADERS)

    def __init__(self, jobs: tuple[PlannedJob, ...] = ()) -> None:
        super().__init__()
        self._jobs: tuple[PlannedJob, ...] = tuple(jobs)

    def set_jobs(self, jobs: tuple[PlannedJob, ...]) -> None:
        self.beginResetModel()
        self._jobs = tuple(jobs)
        self.endResetModel()

    def job_at(self, row: int) -> PlannedJob | None:
        if 0 <= row < len(self._jobs):
            return self._jobs[row]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._jobs)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else self.COLUMNS

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):  # noqa: ANN201
        if not index.isValid():
            return None
        job = self._jobs[index.row()]
        column = index.column()
        if role == Qt.DisplayRole:
            if column == 0:
                return job.name
            if column == 1:
                return ACTION_LABELS.get(job.action, job.action)
            if column == 2:
                return describe_schedule(job)
            if column == 3:
                return describe_next_run(job)
            return "Aktivní" if job.enabled else "Vypnutá"
        if role == Qt.ToolTipRole:
            return describe_command(job)
        return None

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ):  # noqa: ANN201
        if orientation != Qt.Horizontal:
            return None
        if role == Qt.DisplayRole:
            return self.HEADERS[section]
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return None
