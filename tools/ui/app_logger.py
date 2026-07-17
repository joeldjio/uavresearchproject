"""
tools/ui/app_logger.py — Centralized structured logging for SkyMeshX GCS.

Architecture
------------
One Python `logging.Logger` per subsystem, all funnelled through a shared
`RotatingFileHandler` that writes to ``logs/app/<date>/gcs.log``.

Log structure
-------------
logs/
  app/
    <YYYY-MM-DD>/
      gcs.log          — all levels, rotating, JSON-lines format
  drone/
    <timestamp>_<id>_events.jsonl   (unchanged — written by DroneLogger)
    <timestamp>_<id>_telemetry.csv  (unchanged)
  sitl/
    <timestamp>_sitl.log            — stdout/stderr of ArduPilot process
  bridge/
    <timestamp>_bridge.log          — stdout/stderr of gz→MAVLink bridge
  batterylogs/
    battery_history.json
  mavproxy/                          (unchanged — written by MAVProxy itself)
  sitl_sensor/                       (unchanged)

trace_runs/
  <timestamp>_<scenario>/
    manifest.json
    ui_events.jsonl      — UI interactions
    sitl_events.jsonl    — SITL lifecycle
    bridge_events.jsonl  — sensor bridge
    apf_events.jsonl     — APF/safety
    mission_trace.jsonl  — mission waypoints
    ros2_topic_health.json
    video/
    config/

Usage
-----
    from tools.ui.app_logger import get_logger, log_to_trace

    log = get_logger("sitl")
    log.info("[SITL] Bridge started pid=%d", proc.pid)

    # Also write to active trace session (noop if no session active):
    log_to_trace("bridge_events.jsonl", "bridge_start", "bridge",
                 {"pid": proc.pid, "mavlink": conn})
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# ── Constants ────────────────────────────────────────────────────────────────

_LOG_ROOT = Path(os.environ.get("SKYMESHX_LOG_ROOT", "logs"))
_MAX_BYTES = 10 * 1024 * 1024   # 10 MB per file
_BACKUP_COUNT = 5
_FREEZE_THRESHOLD_S = 3.0        # seconds without Qt event loop → freeze warning

# Subsystem → logger name mapping
SUBSYSTEMS = ("app", "swarm", "sitl", "bridge", "safety", "mission", "ros2", "video")

# ── Internal state ───────────────────────────────────────────────────────────

_lock = threading.Lock()
_handlers_installed: set[str] = set()
_loggers: dict[str, logging.Logger] = {}
_trace_logger: Optional[Any] = None   # TraceLogger instance, injected at startup


# ── JSON formatter ───────────────────────────────────────────────────────────

class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line for structured log parsing."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts":      datetime.fromtimestamp(record.created).astimezone().isoformat(
                timespec="milliseconds"
            ),
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


# ── Public API ───────────────────────────────────────────────────────────────

def get_logger(subsystem: str = "app") -> logging.Logger:
    """Return (and lazily configure) the logger for *subsystem*.

    Each subsystem writes to ``logs/app/<today>/gcs.log`` (shared file) and
    additionally to ``stderr`` at WARNING+ level so the terminal shows issues.
    """
    with _lock:
        if subsystem in _loggers:
            return _loggers[subsystem]
        logger = logging.getLogger(f"skymeshx.{subsystem}")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        _install_handlers(logger)
        _loggers[subsystem] = logger
        return logger


def inject_trace_logger(tl: Any) -> None:
    """Called once from service_locator.wire() to inject the TraceLogger singleton."""
    global _trace_logger
    _trace_logger = tl


def log_to_trace(
    filename: str,
    event_type: str,
    source: str,
    data: dict,
) -> None:
    """Append one event to *filename* inside the active trace session.

    Silently no-ops when no trace session is active.  Thread-safe.

    Args:
        filename:   Target file inside the trace bundle, e.g. ``"bridge_events.jsonl"``.
        event_type: Short dot-separated event type, e.g. ``"bridge.start"``.
        source:     Subsystem name, e.g. ``"bridge"``.
        data:       Arbitrary dict payload.
    """
    tl = _trace_logger
    if tl is None or not tl.session_active:
        return
    try:
        tl._append_jsonl(filename, event_type, source, data)
    except Exception:
        pass


def setup_qt_message_handler() -> None:
    """Install a Qt message handler that routes qWarning/qCritical to our logger.

    Call once from app.py before QML engine load.
    """
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler

        _qt_log = get_logger("qt")

        def _handler(msg_type: QtMsgType, context, msg: str) -> None:
            if msg_type == QtMsgType.QtDebugMsg:
                _qt_log.debug(msg)
            elif msg_type == QtMsgType.QtInfoMsg:
                _qt_log.info(msg)
            elif msg_type == QtMsgType.QtWarningMsg:
                # Suppress known harmless noise
                if any(s in msg for s in ("MS Sans Serif", "QML Disk Cache",
                                          "qt.qpa.fonts")):
                    return
                _qt_log.warning(msg)
            elif msg_type == QtMsgType.QtCriticalMsg:
                _qt_log.error(msg)
                log_to_trace("ui_events.jsonl", "qt.critical", "qt", {"msg": msg})
            elif msg_type == QtMsgType.QtFatalMsg:
                _qt_log.critical(msg)
                log_to_trace("ui_events.jsonl", "qt.fatal", "qt", {"msg": msg})

        qInstallMessageHandler(_handler)
    except Exception:
        pass  # PySide6 not available — tests or CLI usage


def start_freeze_watchdog(interval_s: float = 1.0) -> None:
    """Start a background thread that warns when the Qt event loop is frozen.

    The watchdog pings a QTimer every *interval_s* seconds. If the timer
    callback is delayed by more than ``_FREEZE_THRESHOLD_S`` it logs a
    WARNING with a thread-name dump to help diagnose deadlocks / busy loops.

    Call once from app.py after QApplication is created.
    """
    try:
        from PySide6.QtCore import QTimer

        _wdog_log = get_logger("watchdog")
        _last_ping = [time.monotonic()]

        def _qt_ping() -> None:
            _last_ping[0] = time.monotonic()

        timer = QTimer()
        timer.setInterval(int(interval_s * 1000))
        timer.timeout.connect(_qt_ping)
        timer.start()

        def _monitor() -> None:
            while True:
                time.sleep(interval_s * 2)
                delay = time.monotonic() - _last_ping[0]
                if delay > _FREEZE_THRESHOLD_S:
                    thread_info = {
                        t.name: t.is_alive()
                        for t in threading.enumerate()
                    }
                    _wdog_log.warning(
                        "Qt event loop frozen for %.1fs — threads: %s",
                        delay,
                        thread_info,
                    )
                    log_to_trace(
                        "ui_events.jsonl",
                        "app.freeze_detected",
                        "watchdog",
                        {"frozen_s": round(delay, 2), "threads": thread_info},
                    )

        t = threading.Thread(target=_monitor, daemon=True, name="freeze-watchdog")
        t.start()
    except Exception:
        pass


def get_log_dir(subsystem: str = "app") -> Path:
    """Return the directory for *subsystem* logs, creating it if needed."""
    today = datetime.now().strftime("%Y-%m-%d")
    d = _LOG_ROOT / subsystem / today
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_session_log_path(subsystem: str, suffix: str = ".log") -> Path:
    """Return a timestamped log-file path inside logs/<subsystem>/<today>/."""
    d = get_log_dir(subsystem)
    stamp = datetime.now().strftime("%H%M%S")
    return d / f"{stamp}_{subsystem}{suffix}"


# ── Internal helpers ─────────────────────────────────────────────────────────

def _install_handlers(logger: logging.Logger) -> None:
    """Attach RotatingFileHandler + stderr handler to *logger* (idempotent)."""
    name = logger.name
    if name in _handlers_installed:
        return
    _handlers_installed.add(name)

    # ── Shared rotating file in logs/app/<today>/gcs.log ─────────────────
    log_dir = get_log_dir("app")
    log_file = log_dir / "gcs.log"
    fh = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_JsonFormatter())
    logger.addHandler(fh)

    # ── stderr: WARNING+ for terminal visibility ──────────────────────────
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.WARNING)
    sh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(sh)
