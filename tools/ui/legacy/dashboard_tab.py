"""
Dashboard Tab — Live telemetry overview for a single drone.
"""
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QComboBox, QPushButton, QSizePolicy,
    QFrame,
)
from PySide6.QtCore import Qt

import pyqtgraph as pg

from tools.ui.legacy.style import Colors, STATE_COLORS
from tools.ui.legacy.widgets import (
    MetricCard, StateBadge, AttitudeIndicator,
    CompassWidget, BatteryBar, section_header, h_separator
)


class DashboardTab(QWidget):
    """
    Single-drone live telemetry dashboard.
    Receives data via set_telemetry(snap, drone_id).
    """

    def __init__(self, swarm_backend, parent=None):
        super().__init__(parent)
        self._swarm   = swarm_backend
        self._drone_id: str = ""
        self._history  = {"alt": [], "speed": [], "battery": [], "time": []}
        self._t0       = None
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── Top bar: drone selector + state + controls ─────────────────────
        top = QHBoxLayout()

        top.addWidget(QLabel("Active Drone:"))
        self._drone_combo = QComboBox()
        self._drone_combo.setMinimumWidth(140)
        self._drone_combo.currentTextChanged.connect(self._on_drone_selected)
        top.addWidget(self._drone_combo)

        top.addSpacing(12)
        self._badge = StateBadge("UNKNOWN")
        top.addWidget(self._badge)

        top.addSpacing(12)
        lbl_conn = QLabel("●")
        lbl_conn.setObjectName("conn_dot")
        lbl_conn.setStyleSheet("color: #ef4444; font-size: 18px;")
        self._conn_dot = lbl_conn
        top.addWidget(lbl_conn)
        self._conn_label = QLabel("Disconnected")
        self._conn_label.setStyleSheet("color: #64748b;")
        top.addWidget(self._conn_label)

        top.addStretch()

        # Quick-command buttons
        for label, obj_name, slot in [
            ("ARM",      "btn_success", "arm"),
            ("DISARM",   "btn_danger",  "disarm"),
            ("TAKEOFF",  "btn_primary", "takeoff"),
            ("LAND",     "btn_warning", "land"),
            ("RTL",      "btn_warning", "rtl"),
        ]:
            btn = QPushButton(label)
            btn.setObjectName(obj_name)
            btn.setFixedWidth(80)
            btn.clicked.connect(lambda _, s=slot: self._quick_cmd(s))
            top.addWidget(btn)

        root.addLayout(top)
        root.addWidget(h_separator())

        # ── KPI cards row ─────────────────────────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)

        self._card_alt     = MetricCard("Altitude",    "m",   "🏔",  "#3b82f6")
        self._card_speed   = MetricCard("Groundspeed", "m/s", "💨", "#22c55e")
        self._card_heading = MetricCard("Heading",     "°",   "🧭", "#8b5cf6")
        self._card_climb   = MetricCard("Climb Rate",  "m/s", "↑",  "#14b8a6")
        self._card_sats    = MetricCard("Satellites",  "",    "🛰",  "#f59e0b")
        self._card_throttle= MetricCard("Throttle",    "%",   "⚡", "#f97316")

        for c in [self._card_alt, self._card_speed, self._card_heading,
                  self._card_climb, self._card_sats, self._card_throttle]:
            cards_row.addWidget(c)

        root.addLayout(cards_row)

        # ── Main content: instruments + charts ────────────────────────────
        content = QHBoxLayout()
        content.setSpacing(12)

        # Left: attitude + compass + battery
        left = QVBoxLayout()
        left.setSpacing(10)

        grp_att = QGroupBox("Attitude")
        att_lay = QVBoxLayout(grp_att)
        self._attitude = AttitudeIndicator()
        self._attitude.setMinimumSize(160, 160)
        att_lay.addWidget(self._attitude, alignment=Qt.AlignmentFlag.AlignCenter)

        roll_row = QHBoxLayout()
        roll_row.addWidget(QLabel("Roll"))
        self._lbl_roll = QLabel("0.0°")
        self._lbl_roll.setStyleSheet("color: #3b82f6; font-weight: 700;")
        roll_row.addWidget(self._lbl_roll)
        roll_row.addStretch()
        roll_row.addWidget(QLabel("Pitch"))
        self._lbl_pitch = QLabel("0.0°")
        self._lbl_pitch.setStyleSheet("color: #22c55e; font-weight: 700;")
        roll_row.addWidget(self._lbl_pitch)
        att_lay.addLayout(roll_row)
        left.addWidget(grp_att)

        grp_cmp = QGroupBox("Heading")
        cmp_lay = QVBoxLayout(grp_cmp)
        self._compass = CompassWidget()
        self._compass.setMinimumSize(140, 140)
        cmp_lay.addWidget(self._compass, alignment=Qt.AlignmentFlag.AlignCenter)
        left.addWidget(grp_cmp)

        grp_bat = QGroupBox("Battery")
        bat_lay = QVBoxLayout(grp_bat)
        self._battery_bar = BatteryBar()
        bat_lay.addWidget(self._battery_bar)
        row_bat = QHBoxLayout()
        self._lbl_volts   = QLabel("—V")
        self._lbl_current = QLabel("—A")
        self._lbl_volts.setStyleSheet("color: #f59e0b; font-weight: 600;")
        self._lbl_current.setStyleSheet("color: #94a3b8;")
        row_bat.addWidget(self._lbl_volts)
        row_bat.addStretch()
        row_bat.addWidget(self._lbl_current)
        bat_lay.addLayout(row_bat)
        left.addWidget(grp_bat)

        left.addStretch()
        content.addLayout(left, stretch=0)

        # Right: live charts
        right = QVBoxLayout()
        right.setSpacing(10)

        pg.setConfigOption("background", "#161b27")
        pg.setConfigOption("foreground", "#94a3b8")

        self._plt_alt = pg.PlotWidget(title="Altitude (m)")
        self._plt_alt.showGrid(x=True, y=True, alpha=0.2)
        self._curve_alt = self._plt_alt.plot(pen=pg.mkPen("#3b82f6", width=2))
        right.addWidget(self._plt_alt)

        self._plt_speed = pg.PlotWidget(title="Groundspeed (m/s)")
        self._plt_speed.showGrid(x=True, y=True, alpha=0.2)
        self._curve_speed = self._plt_speed.plot(pen=pg.mkPen("#22c55e", width=2))
        right.addWidget(self._plt_speed)

        self._plt_battery = pg.PlotWidget(title="Battery (%)")
        self._plt_battery.showGrid(x=True, y=True, alpha=0.2)
        self._plt_battery.setYRange(0, 100)
        self._curve_battery = self._plt_battery.plot(pen=pg.mkPen("#f59e0b", width=2))
        right.addWidget(self._plt_battery)

        content.addLayout(right, stretch=1)
        root.addLayout(content, stretch=1)

        # ── Position info strip ───────────────────────────────────────────
        pos_bar = QHBoxLayout()
        pos_bar.addWidget(QLabel("GPS:"))
        self._lbl_gps = QLabel("—")
        self._lbl_gps.setStyleSheet("color: #22c55e; font-weight: 600; font-family: monospace;")
        pos_bar.addWidget(self._lbl_gps)
        pos_bar.addSpacing(20)
        pos_bar.addWidget(QLabel("Alt AMSL:"))
        self._lbl_alt_amsl = QLabel("—")
        self._lbl_alt_amsl.setStyleSheet("color: #3b82f6; font-weight: 600;")
        pos_bar.addWidget(self._lbl_alt_amsl)
        pos_bar.addSpacing(20)
        pos_bar.addWidget(QLabel("Fix:"))
        self._lbl_fix = QLabel("—")
        self._lbl_fix.setStyleSheet("color: #f59e0b; font-weight: 600;")
        pos_bar.addWidget(self._lbl_fix)
        pos_bar.addStretch()
        pos_bar.addWidget(QLabel("Autopilot:"))
        self._lbl_autopilot = QLabel("—")
        self._lbl_autopilot.setStyleSheet("color: #8b5cf6; font-weight: 600;")
        pos_bar.addWidget(self._lbl_autopilot)
        root.addLayout(pos_bar)

    def _connect_signals(self):
        self._swarm.drone_added.connect(self._refresh_combo)
        self._swarm.drone_removed.connect(self._refresh_combo)
        self._swarm.swarm_telemetry_updated.connect(self._on_swarm_telemetry)

    # ── Slots ─────────────────────────────────────────────────────────────

    def _refresh_combo(self, _=None):
        current = self._drone_combo.currentText()
        self._drone_combo.blockSignals(True)
        self._drone_combo.clear()
        for did in self._swarm.all_backends().keys():
            self._drone_combo.addItem(did)
        idx = self._drone_combo.findText(current)
        if idx >= 0:
            self._drone_combo.setCurrentIndex(idx)
        self._drone_combo.blockSignals(False)

    def _on_drone_selected(self, drone_id: str):
        self._drone_id = drone_id
        self._history  = {"alt": [], "speed": [], "battery": [], "time": []}
        self._t0       = None

    def _on_swarm_telemetry(self, all_snaps: dict):
        if self._drone_id not in all_snaps:
            return
        snap = all_snaps[self._drone_id]
        self._update_ui(snap)

    def _update_ui(self, snap: dict) -> None:
        if self._t0 is None:
            self._t0 = time.time()
        t = time.time() - self._t0

        self._update_state(snap)
        self._update_kpis(snap)
        self._update_instruments(snap)
        self._update_battery(snap)
        self._update_gps_strip(snap)
        self._update_charts(snap, t)

    def _update_state(self, snap: dict) -> None:
        mode  = snap.get("flight_mode", "UNKNOWN")
        armed = snap.get("armed", False)
        self._badge.set_state("ARMED" if armed else mode)
        self._conn_dot.setStyleSheet(f"color: {Colors.green}; font-size: 18px;")
        self._conn_label.setText("Connected")
        self._conn_label.setStyleSheet(f"color: {Colors.green};")

    def _update_kpis(self, snap: dict) -> None:
        self._card_alt.set_value(snap.get("alt_rel", 0.0), "{:.1f}")
        self._card_speed.set_value(snap.get("groundspeed", 0.0), "{:.1f}")
        self._card_heading.set_value(snap.get("yaw", 0.0), "{:.0f}")
        self._card_climb.set_value(snap.get("climb", 0.0), "{:+.1f}")
        self._card_sats.set_value(int(snap.get("satellites", 0)))
        self._card_throttle.set_value(snap.get("throttle", 0.0), "{:.0f}")

    def _update_instruments(self, snap: dict) -> None:
        roll  = snap.get("roll", 0.0)
        pitch = snap.get("pitch", 0.0)
        self._attitude.set_attitude(roll, pitch)
        self._lbl_roll.setText(f"{roll:+.1f}°")
        self._lbl_pitch.setText(f"{pitch:+.1f}°")
        self._compass.set_heading(snap.get("yaw", 0.0))

    def _update_battery(self, snap: dict) -> None:
        bat_pct = snap.get("battery_pct", -1.0)
        bat_v   = snap.get("battery_v", 0.0)
        bat_a   = snap.get("current_a", 0.0)
        if bat_pct >= 0:
            self._battery_bar.set_percent(bat_pct)
        self._lbl_volts.setText(f"{bat_v:.2f}V" if bat_v > 0 else "—V")
        self._lbl_current.setText(f"{bat_a:.1f}A" if bat_a > 0 else "—A")

    def _update_gps_strip(self, snap: dict) -> None:
        _FIX_LABELS = ["No Fix", "No Fix", "2D", "3D", "3D+DGPS"]
        lat     = snap.get("lat", 0.0)
        lon     = snap.get("lon", 0.0)
        gps_fix = snap.get("gps_fix", 0)
        self._lbl_gps.setText(f"{lat:.6f}, {lon:.6f}")
        self._lbl_alt_amsl.setText(f"{snap.get('alt', 0.0):.1f} m")
        self._lbl_fix.setText(
            _FIX_LABELS[gps_fix] if gps_fix < len(_FIX_LABELS) else str(gps_fix)
        )
        self._lbl_autopilot.setText(snap.get("autopilot", "—").upper())

    def _update_charts(self, snap: dict, t: float) -> None:
        _MAX_POINTS = 300
        bat_pct = snap.get("battery_pct", -1.0)
        self._history["time"].append(t)
        self._history["alt"].append(snap.get("alt_rel", 0.0))
        self._history["speed"].append(snap.get("groundspeed", 0.0))
        self._history["battery"].append(bat_pct if bat_pct >= 0 else 0)
        for k in self._history:
            if len(self._history[k]) > _MAX_POINTS:
                self._history[k] = self._history[k][-_MAX_POINTS:]
        self._curve_alt.setData(self._history["time"], self._history["alt"])
        self._curve_speed.setData(self._history["time"], self._history["speed"])
        self._curve_battery.setData(self._history["time"], self._history["battery"])

    def _quick_cmd(self, cmd: str):
        b = self._swarm.get_backend(self._drone_id)
        if not b:
            return
        if cmd == "arm":
            b.arm()
        elif cmd == "disarm":
            b.disarm()
        elif cmd == "takeoff":
            b.takeoff(10.0)
        elif cmd == "land":
            b.land()
        elif cmd == "rtl":
            b.rtl()
