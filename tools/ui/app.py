"""
skymeshx gcs — QML application entry point (SkyMeshX ground control station).

Architecture
------------
Three-stage cold start:

  Stage 1 (sync, fast):     QGuiApplication, Splash, Profiler
  Stage 2 (sync, deferred): Context objects + signal wiring
  Stage 3 (async):          QML engine load, then close splash

Heavy imports (rclpy, skymeshx SDK, QtWebEngine) are lazy:
they are only triggered when actually needed, NOT at import-time.
"""

import sys
from pathlib import Path

from tools.ui.startup_profiler import profiler

profiler.mark("python_start")

# ──────────────────────────────────────────────────────────────────────
# Stage 1 — minimal Qt imports (no QtWebEngine, no rclpy, no SDK yet)
# ──────────────────────────────────────────────────────────────────────
import os

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
# Force QML disk cache: compiled .qmlc files persist between runs.
# First start is slow (~9s), every subsequent start should drop to <1s.
os.environ.setdefault("QML_DISK_CACHE", "1")
os.environ.setdefault("QML_FORCE_DISK_CACHE", "1")
# Suppress harmless DirectWrite warning about legacy GDI fonts
# ("MS Sans Serif" has no DirectWrite font face — this is a Qt internal
# fallback and does not affect rendering quality).
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts=false")

# QtWebEngine MUST be initialised before QGuiApplication on some platforms.
# We import it here but defer initialize() if possible. Some platforms
# (Windows) do require initialize() pre-app — we keep that contract.
from PySide6.QtWebEngineQuick import QtWebEngineQuick

QtWebEngineQuick.initialize()
profiler.mark("qtwebengine_init")

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QSplashScreen

profiler.mark("qt_core_imports")


def _resolve_qml_root() -> Path:
    """
    Locate ``main.qml`` whether running from source or from a PyInstaller
    bundle.

    PyInstaller ``--onedir`` extracts data files (declared in the .spec
    via ``datas=[...]``) under ``sys._MEIPASS``. The path layout we ship
    is ``<MEIPASS>/tools/ui/qml/main.qml``, mirroring the source tree so
    the same ``Path(__file__)`` logic works for non-frozen runs.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "tools" / "ui" / "qml" / "main.qml"
    return Path(__file__).parent / "qml" / "main.qml"


_QML_ROOT = _resolve_qml_root()


def _make_splash() -> QSplashScreen:
    """
    Ultra-minimal splash. Critical: NO setStyleSheet, NO showMessage,
    NO QPainter. Each of those pulls in QStyle / QFontDatabase first
    time (~1.2s on Windows cold start).

    Pure colored pixmap only. Text is "baked" into the pixmap as raster.
    """
    W, H = 520, 280
    pix = QPixmap(W, H)
    pix.fill(QColor("#0a0d14"))

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    # ── Soft radial glow behind the logo (top-center) ─────────────────
    glow = QRadialGradient(QPointF(W / 2, 95), 220)
    glow.setColorAt(0.0, QColor(37, 99, 235, 90))  # blue-600 @ ~35%
    glow.setColorAt(0.5, QColor(37, 99, 235, 30))
    glow.setColorAt(1.0, QColor(37, 99, 235, 0))
    painter.fillRect(0, 0, W, H, QBrush(glow))

    # ── Subtle bottom gradient for depth ──────────────────────────────
    bottom = QLinearGradient(0, H - 80, 0, H)
    bottom.setColorAt(0.0, QColor(15, 17, 23, 0))
    bottom.setColorAt(1.0, QColor(15, 17, 23, 200))
    painter.fillRect(0, 0, W, H, QBrush(bottom))

    # ── Logo mark: abstract drone/radar emblem inside a rounded badge ─────
    badge_cx, badge_cy, badge_r = W / 2, 78, 32
    painter.setPen(QPen(QColor("#2563eb"), 2))
    painter.setBrush(QColor(37, 99, 235, 40))
    painter.drawEllipse(QPointF(badge_cx, badge_cy), badge_r, badge_r)
    painter.setPen(QPen(QColor(59, 130, 246, 120), 1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(badge_cx, badge_cy), badge_r - 5, badge_r - 5)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#e0ecff"))
    painter.drawEllipse(QPointF(badge_cx, badge_cy), 4.5, 4.5)
    painter.setBrush(QColor(59, 130, 246, 90))
    painter.drawEllipse(QPointF(badge_cx, badge_cy), 10, 10)

    painter.setPen(QPen(QColor("#93c5fd"), 2))
    for dx, dy in ((0, -18), (18, 0), (0, 18), (-18, 0)):
        painter.drawLine(
            QPointF(badge_cx, badge_cy),
            QPointF(badge_cx + dx, badge_cy + dy),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#bfdbfe"))
        painter.drawEllipse(QPointF(badge_cx + dx, badge_cy + dy), 3.5, 3.5)
        painter.setBrush(QColor(59, 130, 246, 70))
        painter.drawEllipse(QPointF(badge_cx + dx, badge_cy + dy), 7, 7)
        painter.setPen(QPen(QColor("#93c5fd"), 2))

    # ── Wordmark ───────────────────────────────────────────────────────
    title_font = QFont("Segoe UI", 24)
    title_font.setBold(True)
    title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.8)
    painter.setFont(title_font)

    title_rect = QRectF(0, 140, W, 44)
    painter.setPen(QColor(0, 0, 0, 180))
    painter.drawText(
        title_rect.translated(0, 2),
        int(Qt.AlignmentFlag.AlignCenter),
        "SkyMeshX",
    )
    painter.setPen(QColor("#f1f5f9"))
    painter.drawText(title_rect, int(Qt.AlignmentFlag.AlignCenter), "SkyMeshX")

    # ── Divider line with gradient ────────────────────────────────────
    line_grad = QLinearGradient(W * 0.25, 0, W * 0.75, 0)
    line_grad.setColorAt(0.0, QColor(37, 99, 235, 0))
    line_grad.setColorAt(0.5, QColor(96, 165, 250, 230))
    line_grad.setColorAt(1.0, QColor(37, 99, 235, 0))
    painter.fillRect(QRectF(W * 0.25, 196, W * 0.5, 1.5), QBrush(line_grad))

    # ── Subtitle ──────────────────────────────────────────────────────
    sub_font = QFont("Segoe UI", 10)
    sub_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.0)
    painter.setFont(sub_font)
    painter.setPen(QColor("#7c8ba6"))
    painter.drawText(
        QRectF(0, 206, W, 22),
        int(Qt.AlignmentFlag.AlignCenter),
        "GROUND CONTROL STATION",
    )

    # ── Version / build tag (bottom-right) ────────────────────────────
    tag_font = QFont("Consolas", 8)
    tag_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
    painter.setFont(tag_font)
    painter.setPen(QColor("#475569"))
    from tools.ui._version import VERSION as _APP_VERSION

    painter.drawText(
        QRectF(0, H - 26, W - 16, 18),
        int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
        f"v{_APP_VERSION}  ·  loading…",
    )

    painter.end()

    splash = QSplashScreen(pix, Qt.WindowType.WindowStaysOnTopHint)
    splash.show()
    return splash


def _build_contexts(app):
    """Stage 2 — heavy context construction via ServiceLocator."""
    profiler.mark("ctx_import_start")

    from tools.ui.service_locator import build_default_locator, wire

    profiler.mark("ctx_import_done")

    locator = build_default_locator(app)
    locator.eager_init()
    profiler.mark("ctx_construct_done")

    wire(locator)
    profiler.mark("ctx_wired")

    return dict(locator.items())


def run() -> int:
    # QApplication required for QSplashScreen (uses QWidget)
    from tools.ui._version import VERSION

    app = QApplication(sys.argv)
    app.setApplicationName("SkyMeshX")
    app.setApplicationDisplayName("SkyMeshX")
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("SkyMeshX")
    app.setOrganizationDomain("skymeshx.local")
    profiler.mark("qapplication_ready")

    splash = _make_splash()
    profiler.mark("splash_built")
    app.processEvents()  # ensure splash paints
    profiler.mark("splash_visible")

    contexts = _build_contexts(app)
    
    def cleanup_contexts():
        for obj in contexts.values():
            shutdown = getattr(obj, "shutdown", None)
            if callable(shutdown):
                shutdown()

    app.aboutToQuit.connect(cleanup_contexts)

    # ── QML engine ────────────────────────────────────────────────────────
    engine = QQmlApplicationEngine()
    video_stream = contexts.get("videoStream")
    image_provider = getattr(video_stream, "image_provider", None)
    if callable(image_provider):
        engine.addImageProvider("videoStream", image_provider())
    ctx = engine.rootContext()
    for name, obj in contexts.items():
        ctx.setContextProperty(name, obj)
    profiler.mark("qml_ctx_set")

    engine.load(QUrl.fromLocalFile(str(_QML_ROOT)))
    profiler.mark("qml_loaded")

    if not engine.rootObjects():
        print("[GCS] ERROR: QML root failed to load.", file=sys.stderr)
        splash.close()
        return 1

    # Close splash once QML window is up
    root_window = engine.rootObjects()[0]
    QTimer.singleShot(150, lambda: splash.finish(None) if splash else None)
    profiler.mark("ready")
    profiler.report()

    exit_code = app.exec()

    # Explicitly destroy the QML engine before the Python GC runs.
    # Without this, async Loaders that are still constructing objects at
    # window-close time trigger Qt's "items still being created at engine
    # destruction" warning.  Clearing root objects first lets the engine
    # shut down all pending async work cleanly before it is deleted.
    del root_window
    engine.clearComponentCache()
    del engine

    return exit_code


if __name__ == "__main__":
    sys.exit(run())
