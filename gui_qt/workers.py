"""Spouštění pomalých operací mimo vlákno GUI.

Business logika o Qt nic neví; runner jen zabalí volání do QRunnable
a výsledek doručí přes signály zpět do hlavního vlákna.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


# Běžící úlohy drží i modul, aby je Python nesebral dřív, než dokončí práci.
_RUNNING: set["Task"] = set()


class TaskSignals(QObject):
    """Signály jedné úlohy."""

    finished = Signal(object)
    failed = Signal(str, object)
    progress = Signal(int, str)


class Task(QRunnable):
    """Zavolá funkci v pracovním vlákně a ohlásí výsledek."""

    def __init__(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.signals = TaskSignals()
        self._function = function
        self._args = args
        self._kwargs = kwargs

    def add_kwarg(self, name: str, value: Any) -> None:
        """Doplní argument volané funkce ještě před spuštěním úlohy."""
        self._kwargs[name] = value

    @Slot()
    def run(self) -> None:  # pragma: no cover - běží v jiném vlákně
        try:
            result = self._function(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001 - chybu předáváme do UI
            self._emit(
                self.signals.failed, str(exc) or exc.__class__.__name__, exc
            )
        else:
            self._emit(self.signals.finished, result)

    @staticmethod
    def _emit(signal: Any, *args: Any) -> None:
        try:
            signal.emit(*args)
        except RuntimeError:
            # Okno se zavřelo dřív, než úloha dokončila práci.
            pass


class BackgroundRunner(QObject):
    """Drží pool a referenci na běžící úlohy, aby je nesebral GC."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._stopped = False

    def run(
        self,
        function: Callable[..., Any],
        *args: Any,
        on_success: Callable[[Any], None],
        on_error: Callable[[str, Exception], None] | None = None,
        on_progress: Callable[[int, str], None] | None = None,
        progress_kwarg: str = "on_progress",
        **kwargs: Any,
    ) -> Task:
        task = Task(function, *args, **kwargs)
        if on_progress is not None:
            # Signál doručí hlášení průběhu zpět do vlákna GUI.
            task.signals.progress.connect(on_progress)
            task.add_kwarg(progress_kwarg, task.signals.progress.emit)
        _RUNNING.add(task)

        def _done(result: Any) -> None:
            _RUNNING.discard(task)
            if not self._stopped:
                on_success(result)

        def _failed(message: str, error: Any) -> None:
            _RUNNING.discard(task)
            if not self._stopped and on_error is not None:
                on_error(message, error)

        task.signals.finished.connect(_done)
        task.signals.failed.connect(_failed)
        self._pool.start(task)
        return task

    def shutdown(self, milliseconds: int = 3000) -> bool:
        """Přestane doručovat výsledky a počká na dobíhající úlohy."""
        self._stopped = True
        return self._pool.waitForDone(milliseconds)

    def wait(self, milliseconds: int = 5000) -> bool:
        """Počká na dokončení úloh; využívají to i testy."""
        return self._pool.waitForDone(milliseconds)
