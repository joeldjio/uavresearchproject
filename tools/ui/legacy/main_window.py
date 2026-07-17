"""
skymeshx gcs — Main Window.

Tabs:
  1. Dashboard  — Live telemetry for active drone
  2. Map        — OSM map with all drones
  3. Swarm      — Multi-drone management & formation
  4. Experiment — Scenario runner & metrics
  5. Safety     — APF filter & geofence monitor
  6. Log        — System log & telemetry export
"""

import time

from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from tools.ui._version import VERSION
from tools.ui.backend import SwarmBackend
from tools.ui.legacy.dashboard_tab import DashboardTab
from tools.ui.legacy.experiment_tab import ExperimentTab
from tools.ui.legacy.log_tab import LogTab
from tools.ui.legacy.map_tab import MapTab
from tools.ui.legacy.safety_tab import SafetyTab
from tools.ui.legacy.style import DARK_THEME, STATUSBAR_STYLESHEET, TAB_STYLESHEET, Colors
from tools.ui.legacy.swarm_tab import SwarmTab

_APP_TITLE = "skymeshx gcs"
_APP_VERSION = f"v{VERSION}"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(_APP_TITLE)
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(DARK_THEME)

        self._swarm = SwarmBackend(parent=self)
        self._swarm.log_message.connect(self._on_log)

        self._build_ui()
        self._start_status_timer()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QVBoxLayout(central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        main_lay.addWidget(self._build_header())
        main_lay.addWidget(self._build_tabs(), stretch=1)
        self._build_statusbar()

        # Wire log signals from tabs that emit them
        for tab in (self._tab_experiment, self._tab_safety):
            tab.log_message.connect(self._on_log)
        self._tab_log.append_log("INFO", f"{_APP_TITLE} {_APP_VERSION} started.")

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background: {Colors.bg_panel};
                border-bottom: 1px solid {Colors.border};
            }}
        """)
        header.setFixedHeight(56)
        lay = QHBoxLayout(header)
        lay.setContentsMargins(20, 0, 20, 0)

        lbl_logo = QLabel("◉")
        lbl_logo.setStyleSheet(f"color: {Colors.blue}; font-size: 24px;")
        lay.addWidget(lbl_logo)

        lbl_title = QLabel(_APP_TITLE)
        lbl_title.setObjectName("label_title")
        lay.addWidget(lbl_title)

        lbl_ver = QLabel(_APP_VERSION)
        lbl_ver.setObjectName("label_subtitle")
        lay.addWidget(lbl_ver)

        lay.addSpacing(20)

        self._ind_time = QLabel("00:00:00")
        self._ind_time.setStyleSheet(
            f"color: {Colors.text_dim}; font-family: Consolas; font-size: 12px;"
        )
        lay.addWidget(self._ind_time)

        lay.addStretch()

        lbl_sc = QLabel("SWARM:")
        lbl_sc.setStyleSheet(f"color: {Colors.text_dim}; font-size: 11px;")
        lay.addWidget(lbl_sc)

        self._ind_count = QLabel("0 drones")
        self._ind_count.setStyleSheet(f"color: {Colors.green}; font-weight: 700;")
        lay.addWidget(self._ind_count)

        lay.addSpacing(20)

        btn_estop = QPushButton("⛔  EMERGENCY STOP")
        btn_estop.setObjectName("btn_danger")
        btn_estop.setFixedHeight(36)
        btn_estop.clicked.connect(self._emergency_stop)
        lay.addWidget(btn_estop)

        return header

    def _build_tabs(self) -> QTabWidget:
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(TAB_STYLESHEET)

        self._tab_dashboard = DashboardTab(self._swarm)
        self._tab_map = MapTab(self._swarm)
        self._tab_swarm = SwarmTab(self._swarm)
        self._tab_experiment = ExperimentTab()
        self._tab_safety = SafetyTab(self._swarm)
        self._tab_log = LogTab(self._swarm)

        for widget, label in [
            (self._tab_dashboard, "📊  Dashboard"),
            (self._tab_map, "🗺  Map"),
            (self._tab_swarm, "🚁  Swarm"),
            (self._tab_experiment, "🔬  Experiment"),
            (self._tab_safety, "🛡  Safety"),
            (self._tab_log, "📋  Log"),
        ]:
            self._tabs.addTab(widget, label)

        return self._tabs

    def _build_statusbar(self) -> None:
        self._status = QStatusBar()
        self._status.setStyleSheet(STATUSBAR_STYLESHEET)
        self.setStatusBar(self._status)
        self._status.showMessage(f"{_APP_TITLE} ready.")

    # ── Timer / slots ─────────────────────────────────────────────────────

    def _start_status_timer(self) -> None:
        self._time_timer = QTimer(self)
        self._time_timer.setInterval(1000)
        self._time_timer.timeout.connect(self._tick)
        self._time_timer.start()

    @Slot()
    def _tick(self) -> None:
        self._ind_time.setText(time.strftime("%H:%M:%S"))
        backends = self._swarm.all_backends()
        total = len(backends)
        connected = sum(1 for b in backends.values() if b.is_connected)
        self._ind_count.setText(f"{connected}/{total} drones")

    @Slot(str, str)
    def _on_log(self, level: str, msg: str) -> None:
        self._tab_log.append_log(level, msg)
        self._status.showMessage(f"[{level}] {msg}", 4000)

    def _emergency_stop(self) -> None:
        self._swarm.disarm_all(force=True)
        self._on_log("ERROR", "⚛ EMERGENCY STOP — All drones force-disarmed!")
