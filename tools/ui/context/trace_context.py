"""QML-facing trace session context."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from skymeshx.core.trace_logger import TraceLogger


class TraceContext(QObject):
    """Expose trace bundle session controls to QML."""

    sessionStarted = Signal(str, arguments=["path"])
    sessionStopped = Signal(str, arguments=["path"])
    sessionError = Signal(str, arguments=["message"])
    sessionChanged = Signal()

    def __init__(self, logger: TraceLogger | None = None, parent=None):
        super().__init__(parent)
        self._logger = logger or TraceLogger.get()
        self._last_error = ""

    @Property(bool, notify=sessionChanged)
    def sessionActive(self) -> bool:
        return self._logger.session_active

    @Property(str, notify=sessionChanged)
    def sessionPath(self) -> str:
        return self._logger.session_path

    @Property(str, notify=sessionChanged)
    def sessionScenario(self) -> str:
        return self._logger.session_scenario

    @Property(str, notify=sessionChanged)
    def lastError(self) -> str:
        return self._last_error

    @Slot(str, result=bool)
    @Slot(str, "QVariant", result=bool)
    def startSession(self, scenario: str, simConfig: Any = None) -> bool:
        config = dict(simConfig) if isinstance(simConfig, dict) else {}
        name = str(scenario or "").strip() or "manual_trace_session"
        try:
            path = self._logger.start_session(name, config)
        except Exception as exc:
            return self._fail(str(exc))

        self._last_error = ""
        self.sessionStarted.emit(path)
        self.sessionChanged.emit()
        return True

    @Slot(result=str)
    def stopSession(self) -> str:
        try:
            path = self._logger.stop_session()
        except Exception as exc:
            self._fail(str(exc))
            return ""

        self._last_error = ""
        self.sessionStopped.emit(path)
        self.sessionChanged.emit()
        return path

    @Slot(result=str)
    @Slot(str, result=str)
    def exportSummary(self, path: str = "") -> str:
        try:
            summary_path = self._logger.export_markdown(path or None)
        except Exception as exc:
            self._fail(str(exc))
            return ""

        self._last_error = ""
        self.sessionChanged.emit()
        return summary_path

    @Slot(int, str)
    def logTabChange(self, tab_index: int, tab_id: str) -> None:
        """Called from QML when the user switches tabs."""
        self._logger.log_tab_change(tab_index, str(tab_id))

    @Slot(result=bool)
    def openFolder(self) -> bool:
        folder = self._logger.session_path
        if not folder:
            return self._fail("No trace session folder available")
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(folder))))
        if not ok:
            return self._fail("Could not open trace session folder")
        self._last_error = ""
        self.sessionChanged.emit()
        return True

    def shutdown(self) -> None:
        if self._logger.session_active:
            self._logger.stop_session()
            self.sessionChanged.emit()

    def _fail(self, message: str) -> bool:
        self._last_error = message
        self.sessionError.emit(message)
        self.sessionChanged.emit()
        return False
