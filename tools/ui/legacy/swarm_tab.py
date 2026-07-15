"""
Swarm Tab — Multi-drone management, formation control, parallel commands.
"""
import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QPushButton, QLineEdit,
    QComboBox, QDoubleSpinBox, QSpinBox, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QScrollArea,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from tools.ui.legacy.style import STATE_COLORS, DRONE_COLORS
from tools.ui.legacy.widgets import StateBadge, MetricCard, section_header, h_separator, BatteryBar


class DroneRow(QFrame):
    """One row per drone in the swarm panel."""

    def __init__(self, drone_id: str, color: str, backend, parent=None):
        super().__init__(parent)
        self._id      = drone_id
        self._color   = color
        self._backend = backend
        self.setStyleSheet(f"""
            QFrame {{
                background: #1a2035;
                border: 1px solid #2d3748;
                border-left: 3px solid {color};
                border-radius: 8px;
            }}
        """)
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(12)

        # Color dot + ID
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {self._color}; font-size: 20px;")
        lay.addWidget(dot)

        lbl_id = QLabel(self._id)
        lbl_id.setStyleSheet("font-weight: 700; font-size: 13px; min-width: 60px;")
        lay.addWidget(lbl_id)

        self._badge = StateBadge("UNKNOWN")
        lay.addWidget(self._badge)

        # Mini telemetry
        self._lbl_alt   = QLabel("Alt: —")
        self._lbl_speed = QLabel("Spd: —")
        self._lbl_bat   = QLabel("Bat: —")
        self._lbl_gps   = QLabel("GPS: —")
        for lbl in [self._lbl_alt, self._lbl_speed, self._lbl_bat, self._lbl_gps]:
            lbl.setStyleSheet("color: #94a3b8; font-size: 11px; min-width: 70px;")
            lay.addWidget(lbl)

        self._bat_bar = BatteryBar()
        self._bat_bar.setFixedWidth(80)
        lay.addWidget(self._bat_bar)

        lay.addStretch()

        # Per-drone controls
        for label, obj_name, slot in [
            ("ARM",    "btn_success", "arm"),
            ("DISARM", "btn_danger",  "disarm"),
            ("RTL",    "btn_warning", "rtl"),
        ]:
            btn = QPushButton(label)
            btn.setObjectName(obj_name)
            btn.setFixedWidth(70)
            btn.clicked.connect(lambda _, s=slot: self._cmd(s))
            lay.addWidget(btn)

    def _cmd(self, cmd: str):
        if cmd == "arm":
            self._backend.arm()
        elif cmd == "disarm":
            self._backend.disarm()
        elif cmd == "rtl":
            self._backend.rtl()

    def update_telemetry(self, snap: dict):
        mode  = snap.get("flight_mode", "UNKNOWN")
        armed = snap.get("armed", False)
        self._badge.set_state("ARMED" if armed else mode)
        self._lbl_alt.setText(f"Alt: {snap.get('alt_rel', 0):.1f}m")
        self._lbl_speed.setText(f"Spd: {snap.get('groundspeed', 0):.1f}m/s")
        bat = snap.get("battery_pct", -1)
        self._lbl_bat.setText(f"Bat: {bat:.0f}%" if bat >= 0 else "Bat: —")
        if bat >= 0:
            self._bat_bar.set_percent(bat)
        sats = snap.get("satellites", 0)
        fix  = snap.get("gps_fix", 0)
        self._lbl_gps.setText(f"GPS: {sats}sat/{fix}D")


class SwarmTab(QWidget):

    def __init__(self, swarm_backend, parent=None):
        super().__init__(parent)
        self._swarm   = swarm_backend
        self._rows: dict = {}
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        # ── Left: drone list + add ─────────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(10)

        left.addWidget(section_header("Swarm Fleet", "#3b82f6"))

        # Add drone form
        grp_add = QGroupBox("Add Drone")
        add_lay = QGridLayout(grp_add)
        add_lay.addWidget(QLabel("ID:"), 0, 0)
        self._inp_id   = QLineEdit()
        self._inp_id.setPlaceholderText("e.g. D1")
        add_lay.addWidget(self._inp_id, 0, 1)
        add_lay.addWidget(QLabel("Connection:"), 1, 0)
        self._inp_conn = QLineEdit()
        self._inp_conn.setPlaceholderText("tcp:127.0.0.1:5760")
        add_lay.addWidget(self._inp_conn, 1, 1)
        btn_add = QPushButton("＋ Add & Connect")
        btn_add.setObjectName("btn_primary")
        btn_add.clicked.connect(self._add_drone)
        add_lay.addWidget(btn_add, 2, 0, 1, 2)
        left.addWidget(grp_add)

        # SITL quick-add
        grp_sitl = QGroupBox("SITL Quick-Add")
        sitl_lay = QGridLayout(grp_sitl)
        sitl_lay.addWidget(QLabel("Count:"), 0, 0)
        self._spin_sitl = QSpinBox()
        self._spin_sitl.setRange(1, 8)
        self._spin_sitl.setValue(3)
        sitl_lay.addWidget(self._spin_sitl, 0, 1)
        sitl_lay.addWidget(QLabel("Base port:"), 1, 0)
        self._spin_port = QSpinBox()
        self._spin_port.setRange(5760, 5800)
        self._spin_port.setValue(5760)
        sitl_lay.addWidget(self._spin_port, 1, 1)
        btn_sitl = QPushButton("⚡ Add SITL Swarm")
        btn_sitl.setObjectName("btn_warning")
        btn_sitl.clicked.connect(self._add_sitl_swarm)
        sitl_lay.addWidget(btn_sitl, 2, 0, 1, 2)
        left.addWidget(grp_sitl)

        # Global commands
        grp_cmd = QGroupBox("Swarm Commands")
        cmd_lay = QGridLayout(grp_cmd)
        for row, (label, obj, slot) in enumerate([
            ("ARM ALL",     "btn_success", "arm_all"),
            ("DISARM ALL",  "btn_danger",  "disarm_all"),
            ("TAKEOFF ALL", "btn_primary", "takeoff_all"),
            ("LAND ALL",    "btn_warning", "land_all"),
            ("RTL ALL",     "btn_warning", "rtl_all"),
        ]):
            btn = QPushButton(label)
            btn.setObjectName(obj)
            btn.clicked.connect(lambda _, s=slot: self._swarm_cmd(s))
            cmd_lay.addWidget(btn, row, 0)

        # Takeoff altitude
        cmd_lay.addWidget(QLabel("Takeoff Alt:"), 5, 0)
        self._spin_alt = QDoubleSpinBox()
        self._spin_alt.setRange(1.0, 100.0)
        self._spin_alt.setValue(10.0)
        self._spin_alt.setSuffix(" m")
        cmd_lay.addWidget(self._spin_alt, 5, 1)
        left.addWidget(grp_cmd)

        # Formation
        grp_form = QGroupBox("Formation Control")
        form_lay = QGridLayout(grp_form)
        form_lay.addWidget(QLabel("Shape:"), 0, 0)
        self._combo_form = QComboBox()
        self._combo_form.addItems(["circle", "line", "v", "grid"])
        form_lay.addWidget(self._combo_form, 0, 1)
        form_lay.addWidget(QLabel("Spacing:"), 1, 0)
        self._spin_spacing = QDoubleSpinBox()
        self._spin_spacing.setRange(2.0, 50.0)
        self._spin_spacing.setValue(5.0)
        self._spin_spacing.setSuffix(" m")
        form_lay.addWidget(self._spin_spacing, 1, 1)
        form_lay.addWidget(QLabel("Leader:"), 2, 0)
        self._combo_leader = QComboBox()
        form_lay.addWidget(self._combo_leader, 2, 1)
        btn_form = QPushButton("▶ Execute Formation")
        btn_form.setObjectName("btn_primary")
        btn_form.clicked.connect(self._execute_formation)
        form_lay.addWidget(btn_form, 3, 0, 1, 2)
        left.addWidget(grp_form)

        left.addStretch()
        root.addLayout(left, stretch=0)

        # ── Right: drone rows + stats table ───────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(10)

        right.addWidget(section_header("Active Drones", "#22c55e"))

        # Scroll area for drone rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        container = QWidget()
        self._rows_layout = QVBoxLayout(container)
        self._rows_layout.setSpacing(8)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.addStretch()
        scroll.setWidget(container)
        right.addWidget(scroll, stretch=1)

        # Stats table
        right.addWidget(section_header("Swarm Statistics", "#8b5cf6"))
        self._stats_table = QTableWidget(0, 8)
        self._stats_table.setHorizontalHeaderLabels(
            ["ID", "State", "Alt (m)", "Speed (m/s)", "Bat (%)", "Lat", "Lon", "Sats"]
        )
        self._stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._stats_table.setAlternatingRowColors(True)
        self._stats_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._stats_table.setMaximumHeight(200)
        right.addWidget(self._stats_table)

        root.addLayout(right, stretch=1)

    def _connect_signals(self):
        self._swarm.drone_added.connect(self._on_drone_added)
        self._swarm.drone_removed.connect(self._on_drone_removed)
        self._swarm.swarm_telemetry_updated.connect(self._on_telemetry)

    # ── Slots ─────────────────────────────────────────────────────────────

    def _add_and_connect(self, drone_id: str, connection_string: str) -> None:
        backend = self._swarm.add_drone(drone_id, connection_string)
        threading.Thread(target=backend.connect, daemon=True).start()

    def _add_drone(self) -> None:
        did  = self._inp_id.text().strip()
        conn = self._inp_conn.text().strip()
        if not did or not conn:
            return
        self._add_and_connect(did, conn)
        self._inp_id.clear()

    def _add_sitl_swarm(self) -> None:
        base_port = int(self._spin_port.value())
        for i in range(self._spin_sitl.value()):
            self._add_and_connect(f"D{i+1}", f"tcp:127.0.0.1:{base_port + i}")

    def _swarm_cmd(self, cmd: str):
        if cmd == "arm_all":
            self._swarm.arm_all()
        elif cmd == "disarm_all":
            self._swarm.disarm_all()
        elif cmd == "takeoff_all":
            self._swarm.takeoff_all(self._spin_alt.value())
        elif cmd == "land_all":
            self._swarm.land_all()
        elif cmd == "rtl_all":
            self._swarm.rtl_all()

    def _execute_formation(self):
        shape   = self._combo_form.currentText()
        spacing = self._spin_spacing.value()
        leader  = self._combo_leader.currentText() or None
        # Use SkyMeshX Swarm SDK if drones are real
        backends = self._swarm.all_backends()
        try:
            from skymeshx.sdk.swarm_api import Swarm
            swarm = Swarm()
            for did, b in backends.items():
                if b.is_connected and b.drone:
                    swarm._drones[did] = b.drone
            swarm.formation(shape, spacing=spacing, leader=leader)
        except Exception as e:
            print(f"[formation] {e}")

    def _on_drone_added(self, drone_id: str):
        color = DRONE_COLORS[len(self._rows) % len(DRONE_COLORS)]
        b     = self._swarm.get_backend(drone_id)
        row   = DroneRow(drone_id, color, b)
        self._rows[drone_id] = row
        # Insert before stretch
        idx = self._rows_layout.count() - 1
        self._rows_layout.insertWidget(idx, row)
        # Update leader combo
        self._combo_leader.addItem(drone_id)

    def _on_drone_removed(self, drone_id: str):
        row = self._rows.pop(drone_id, None)
        if row:
            row.setParent(None)
            row.deleteLater()
        idx = self._combo_leader.findText(drone_id)
        if idx >= 0:
            self._combo_leader.removeItem(idx)

    def _on_telemetry(self, all_snaps: dict):
        # Update rows
        for did, snap in all_snaps.items():
            if did in self._rows:
                self._rows[did].update_telemetry(snap)

        # Update stats table
        self._stats_table.setRowCount(len(all_snaps))
        for r, (did, snap) in enumerate(all_snaps.items()):
            vals = [
                did,
                "ARMED" if snap.get("armed") else snap.get("flight_mode","—"),
                f"{snap.get('alt_rel',0):.1f}",
                f"{snap.get('groundspeed',0):.1f}",
                f"{snap.get('battery_pct',-1):.0f}" if snap.get('battery_pct',-1)>=0 else "—",
                f"{snap.get('lat',0):.5f}",
                f"{snap.get('lon',0):.5f}",
                str(snap.get("satellites", 0)),
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 1 and snap.get("armed"):
                    item.setForeground(QColor("#22c55e"))
                self._stats_table.setItem(r, c, item)
