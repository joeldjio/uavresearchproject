"""
Safety Tab — APF filter visualizer, geofence editor, violation monitor.
"""
import math

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QDoubleSpinBox,
    QFormLayout, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont

from tools.ui.legacy.widgets import section_header, h_separator, MetricCard
from tools.ui.legacy.style import Colors, DRONE_COLORS

try:
    from skymeshx.safety.apf import APFSafetyFilter as _APFSafetyFilter, Pose3D as _Pose3D
except ImportError:  # pragma: no cover
    _APFSafetyFilter = None  # type: ignore
    _Pose3D = None           # type: ignore


class SwarmTopView(QWidget):
    """2D top-down canvas showing drone positions, geofence, APF vectors."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drones:    dict = {}   # {id: (x, y, armed)}
        self._geofence_r = 50.0
        self._violations: list = []
        self.setMinimumSize(400, 400)
        self.setStyleSheet("background: #0d1117; border: 1px solid #2d3748; border-radius: 8px;")

    def update_drones(self, positions: dict, violations: list):
        self._drones     = positions
        self._violations = violations
        self.update()

    def set_geofence(self, radius: float):
        self._geofence_r = radius
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        scale = min(w, h) / 2 / (self._geofence_r * 1.2)

        # Grid
        p.setPen(QPen(QColor("#1e2535"), 1))
        step = max(5, int(self._geofence_r / 5))
        for d in range(step, int(self._geofence_r * 2), step):
            px_d = d * scale
            p.drawEllipse(
                int(cx - px_d), int(cy - px_d),
                int(px_d * 2), int(px_d * 2)
            )

        # Axes
        p.setPen(QPen(QColor("#2d3748"), 1))
        p.drawLine(0, int(cy), w, int(cy))
        p.drawLine(int(cx), 0, int(cx), h)

        # Geofence circle
        r_px = self._geofence_r * scale
        p.setPen(QPen(QColor("#ef4444"), 2, Qt.PenStyle.DashLine))
        p.setBrush(QBrush(QColor("#ef444411")))
        p.drawEllipse(int(cx - r_px), int(cy - r_px), int(r_px * 2), int(r_px * 2))

        # Violation pairs
        for (id_a, id_b, dist) in self._violations:
            if id_a in self._drones and id_b in self._drones:
                ax, ay, _ = self._drones[id_a]
                bx, by, _ = self._drones[id_b]
                p.setPen(QPen(QColor("#ef4444"), 2))
                p.drawLine(
                    int(cx + ax * scale), int(cy - ay * scale),
                    int(cx + bx * scale), int(cy - by * scale),
                )

        # Drones
        for i, (did, (x, y, armed)) in enumerate(self._drones.items()):
            color = QColor(DRONE_COLORS[i % len(DRONE_COLORS)])
            px = int(cx + x * scale)
            py = int(cy - y * scale)

            # Body
            p.setBrush(QBrush(color if armed else QColor("#374151")))
            p.setPen(QPen(color, 2))
            p.drawEllipse(px - 8, py - 8, 16, 16)

            # Label
            p.setPen(QColor("white"))
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.drawText(px + 10, py + 4, did)

            # Coordinates
            p.setPen(QColor("#64748b"))
            p.setFont(QFont("Consolas", 7))
            p.drawText(px - 20, py + 20, f"({x:.1f},{y:.1f})")

        # Origin marker
        p.setBrush(QBrush(QColor("#f59e0b")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(cx) - 4, int(cy) - 4, 8, 8)
        p.setPen(QColor("#f59e0b"))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(int(cx) + 6, int(cy) - 6, "HOME")

        p.end()


class SafetyTab(QWidget):

    log_message = Signal(str, str)

    def __init__(self, swarm_backend, parent=None):
        super().__init__(parent)
        self._swarm          = swarm_backend
        self._apf            = None
        self._last_positions: dict = {}
        self._ref_lat: float = 0.0
        self._ref_lon: float = 0.0
        self._ref_set:  bool = False
        self._build_ui()
        self._connect_signals()

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._poll_apf)
        self._poll_timer.start()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        # ── Left: controls ────────────────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(10)

        left.addWidget(section_header("APF Filter Config", "#ef4444"))

        grp_apf = QGroupBox("APF Parameters")
        form = QFormLayout(grp_apf)

        self._spin_sep = QDoubleSpinBox()
        self._spin_sep.setRange(0.5, 20.0)
        self._spin_sep.setValue(2.0)
        self._spin_sep.setSuffix(" m")
        form.addRow("Min Separation:", self._spin_sep)

        self._spin_maxspd = QDoubleSpinBox()
        self._spin_maxspd.setRange(0.5, 15.0)
        self._spin_maxspd.setValue(3.0)
        self._spin_maxspd.setSuffix(" m/s")
        form.addRow("Max Speed:", self._spin_maxspd)

        self._spin_rep = QDoubleSpinBox()
        self._spin_rep.setRange(0.1, 10.0)
        self._spin_rep.setValue(2.0)
        form.addRow("Repulsion Gain:", self._spin_rep)

        self._spin_att = QDoubleSpinBox()
        self._spin_att.setRange(0.1, 5.0)
        self._spin_att.setValue(1.0)
        form.addRow("Attraction Gain:", self._spin_att)

        self._spin_obs_r = QDoubleSpinBox()
        self._spin_obs_r.setRange(1.0, 20.0)
        self._spin_obs_r.setValue(4.0)
        self._spin_obs_r.setSuffix(" m")
        form.addRow("Obstacle Radius:", self._spin_obs_r)

        left.addWidget(grp_apf)

        grp_gf = QGroupBox("Geofence")
        gf_form = QFormLayout(grp_gf)

        self._spin_gf_r = QDoubleSpinBox()
        self._spin_gf_r.setRange(10, 2000)
        self._spin_gf_r.setValue(50.0)
        self._spin_gf_r.setSuffix(" m")
        gf_form.addRow("Radius:", self._spin_gf_r)

        self._spin_alt_min = QDoubleSpinBox()
        self._spin_alt_min.setRange(0.5, 10.0)
        self._spin_alt_min.setValue(1.0)
        self._spin_alt_min.setSuffix(" m")
        gf_form.addRow("Min Alt:", self._spin_alt_min)

        self._spin_alt_max = QDoubleSpinBox()
        self._spin_alt_max.setRange(5.0, 200.0)
        self._spin_alt_max.setValue(30.0)
        self._spin_alt_max.setSuffix(" m")
        gf_form.addRow("Max Alt:", self._spin_alt_max)

        left.addWidget(grp_gf)

        self._btn_apply = QPushButton("⚡ Apply APF Config")
        self._btn_apply.setObjectName("btn_primary")
        self._btn_apply.clicked.connect(self._apply_apf)
        left.addWidget(self._btn_apply)

        # Violation log
        left.addWidget(section_header("Violations", "#ef4444"))
        self._viol_table = QTableWidget(0, 3)
        self._viol_table.setHorizontalHeaderLabels(["Drone A", "Drone B", "Distance"])
        self._viol_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._viol_table.setMaximumHeight(150)
        left.addWidget(self._viol_table)

        # Metrics
        kpi_row = QHBoxLayout()
        self._card_viol   = MetricCard("Violations",  "", "⚠", "#ef4444")
        self._card_active = MetricCard("Active Drones","","🚁", "#22c55e")
        kpi_row.addWidget(self._card_viol)
        kpi_row.addWidget(self._card_active)
        left.addLayout(kpi_row)

        left.addStretch()
        root.addLayout(left, stretch=0)

        # ── Right: visualization ──────────────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(10)

        right.addWidget(section_header("Swarm Top-View (Local NED)", "#3b82f6"))
        self._canvas = SwarmTopView()
        right.addWidget(self._canvas, stretch=1)

        right.addWidget(section_header("Safety Log", "#94a3b8"))
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(100)
        self._log.setStyleSheet(
            "background:#0d1117; color:#8be9fd; font-family:Consolas; font-size:11px;"
        )
        right.addWidget(self._log)

        root.addLayout(right, stretch=1)

    def _connect_signals(self):
        self._swarm.swarm_telemetry_updated.connect(self._on_telemetry)

    def _apply_apf(self) -> None:
        if _APFSafetyFilter is None:
            self._log.append("[APF] skymeshx SDK not installed.")
            return
        try:
            self._apf = _APFSafetyFilter(
                min_separation  = self._spin_sep.value(),
                max_speed       = self._spin_maxspd.value(),
                geofence_radius = self._spin_gf_r.value(),
                geofence_alt    = (self._spin_alt_min.value(), self._spin_alt_max.value()),
                repulsion_gain  = self._spin_rep.value(),
                attraction_gain = self._spin_att.value(),
                obstacle_radius = self._spin_obs_r.value(),
            )
            self._canvas.set_geofence(self._spin_gf_r.value())
            self._log.append("[APF] Filter configured and active.")
            self.log_message.emit("INFO", "[APF] Filter configured.")
        except Exception as exc:
            self._log.append(f"[APF] Error: {exc}")

    def _on_telemetry(self, all_snaps: dict) -> None:
        positions: dict = {}
        for did, snap in all_snaps.items():
            lat   = snap.get("lat", 0.0)
            lon   = snap.get("lon", 0.0)
            armed = snap.get("armed", False)
            if not self._ref_set:
                self._ref_lat = lat
                self._ref_lon = lon
                self._ref_set = True
            x = (lat - self._ref_lat) * 111_320.0
            y = (lon - self._ref_lon) * 111_320.0 * math.cos(math.radians(self._ref_lat))
            positions[did] = (x, y, armed)
        self._last_positions = positions

    def _poll_apf(self):
        if not self._last_positions:
            return

        violations = []
        if self._apf and _Pose3D is not None:
            poses = {
                did: _Pose3D(x, y, 10)
                for did, (x, y, _) in self._last_positions.items()
            }
            violations = self._apf.check_separation(poses)

        self._canvas.update_drones(self._last_positions, violations)
        self._card_active.set_value(len(self._last_positions))
        self._card_viol.set_value(len(violations))

        # Update violation table
        self._viol_table.setRowCount(len(violations))
        for r, (a, b, dist) in enumerate(violations):
            for c, v in enumerate([a, b, f"{dist:.2f}m"]):
                item = QTableWidgetItem(v)
                item.setForeground(QColor("#ef4444"))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._viol_table.setItem(r, c, item)

        if violations:
            msg = f"[APF] ⚠ {len(violations)} separation violation(s)!"
            self._log.append(f'<span style="color:#ef4444;">{msg}</span>')
            self.log_message.emit("WARN", msg)
