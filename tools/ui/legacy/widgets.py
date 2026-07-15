"""
Shared custom widgets used across all tabs.
"""
import math
from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy
)
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPolygonF
from PySide6.QtCore import Qt, QPointF, QRectF

from tools.ui.legacy.style import Colors, STATE_COLORS, DRONE_COLORS


# ── Metric Card ───────────────────────────────────────────────────────────────

class MetricCard(QFrame):
    """A single KPI card: icon label + big value + unit + subtitle."""

    def __init__(self, title: str, unit: str = "", icon: str = "", color: str = "#2563eb", parent=None):
        super().__init__(parent)
        self._color = color
        self.setObjectName("MetricCard")
        self.setStyleSheet(f"""
            QFrame#MetricCard {{
                background: {Colors.bg_card};
                border: 1px solid {Colors.border};
                border-left: 3px solid {color};
                border-radius: 10px;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(90)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)

        header = QHBoxLayout()
        lbl_icon = QLabel(icon)
        lbl_icon.setStyleSheet(f"color: {color}; font-size: 16px;")
        lbl_title = QLabel(title.upper())
        lbl_title.setStyleSheet(f"color: {Colors.text_dim}; font-size: 10px; font-weight: 600; letter-spacing: 1px;")
        header.addWidget(lbl_icon)
        header.addWidget(lbl_title)
        header.addStretch()
        lay.addLayout(header)

        self._val_label = QLabel("—")
        self._val_label.setStyleSheet(f"color: {color}; font-size: 26px; font-weight: 700;")
        lay.addWidget(self._val_label)

        self._unit_label = QLabel(unit)
        self._unit_label.setStyleSheet(f"color: {Colors.text_dim}; font-size: 11px;")
        lay.addWidget(self._unit_label)

    def set_value(self, value, fmt: str = "{}"):
        try:
            self._val_label.setText(fmt.format(value))
        except Exception:
            self._val_label.setText(str(value))

    def set_color(self, color: str):
        self._color = color
        self._val_label.setStyleSheet(f"color: {color}; font-size: 26px; font-weight: 700;")


# ── State Badge ───────────────────────────────────────────────────────────────

class StateBadge(QLabel):
    """Colored pill badge for FSM state."""

    def __init__(self, state: str = "UNKNOWN", parent=None):
        super().__init__(parent)
        self.set_state(state)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(28)
        self.setMinimumWidth(90)

    def set_state(self, state: str):
        color = STATE_COLORS.get(state, "#374151")
        self.setText(state)
        self.setStyleSheet(f"""
            QLabel {{
                background: {color}22;
                color: {color};
                border: 1px solid {color};
                border-radius: 14px;
                padding: 2px 14px;
                font-weight: 700;
                font-size: 11px;
                letter-spacing: 1px;
            }}
        """)


# ── Attitude Indicator (Artificial Horizon) ────────────────────────────────────

class AttitudeIndicator(QWidget):
    """Mini artificial horizon widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._roll  = 0.0
        self._pitch = 0.0
        self.setMinimumSize(120, 120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_attitude(self, roll_deg: float, pitch_deg: float):
        self._roll  = roll_deg
        self._pitch = pitch_deg
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 4

        p.setClipRegion(self.visibleRegion())
        clip_path = QPainterPath()
        clip_path.addEllipse(QPointF(cx, cy), r, r)
        p.setClipPath(clip_path)

        p.save()
        p.translate(cx, cy)
        p.rotate(self._roll)

        pitch_px = self._pitch * (r / 45.0)

        # Sky
        p.fillRect(int(-r), int(-r * 2 + pitch_px), int(r * 2), int(r * 2), QColor(Colors.sky))
        # Ground
        p.fillRect(int(-r), int(pitch_px), int(r * 2), int(r * 2), QColor(Colors.earth))

        # Horizon line
        p.setPen(QPen(QColor("white"), 2))
        p.drawLine(int(-r), int(pitch_px), int(r), int(pitch_px))

        p.restore()

        # Border
        p.setPen(QPen(QColor("#2d3748"), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Center cross
        p.setPen(QPen(QColor("white"), 2))
        p.drawLine(int(cx - 20), int(cy), int(cx - 6), int(cy))
        p.drawLine(int(cx + 6), int(cy), int(cx + 20), int(cy))
        p.drawLine(int(cx), int(cy - 6), int(cx), int(cy - 6))
        p.drawEllipse(QPointF(cx, cy), 3, 3)

        p.end()


# ── Compass Rose ─────────────────────────────────────────────────────────────

class CompassWidget(QWidget):
    """Mini compass widget showing heading."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._heading = 0.0
        self.setMinimumSize(100, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_heading(self, deg: float):
        self._heading = deg % 360
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 6

        # Background
        p.setBrush(QBrush(QColor(Colors.bg_card)))
        p.setPen(QPen(QColor(Colors.border), 2))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Cardinal labels
        p.setPen(QColor(Colors.text_muted))
        fnt = QFont("Segoe UI", 8, QFont.Weight.Bold)
        p.setFont(fnt)
        for angle, label in [(0, "N"), (90, "E"), (180, "S"), (270, "W")]:
            rad = math.radians(angle - self._heading - 90)
            tx = cx + (r - 16) * math.cos(rad)
            ty = cy + (r - 16) * math.sin(rad)
            p.drawText(QRectF(tx - 8, ty - 8, 16, 16), Qt.AlignmentFlag.AlignCenter, label)

        # Needle (north = red)
        p.save()
        p.translate(cx, cy)
        p.rotate(-self._heading)
        needle = QPolygonF([
            QPointF(0, -(r - 22)),
            QPointF(5, 0),
            QPointF(0, 10),
            QPointF(-5, 0),
        ])
        p.setBrush(QBrush(QColor(Colors.red)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(needle)
        south = QPolygonF([
            QPointF(0, (r - 22)),
            QPointF(5, 0),
            QPointF(0, -10),
            QPointF(-5, 0),
        ])
        p.setBrush(QBrush(QColor(Colors.text_muted)))
        p.drawPolygon(south)
        p.restore()

        p.setPen(QPen(QColor(Colors.blue), 2))
        p.setBrush(QBrush(QColor(Colors.blue)))
        p.drawEllipse(QPointF(cx, cy), 4, 4)

        # Heading text
        p.setPen(QColor("white"))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(QRectF(cx - 25, cy + r - 18, 50, 16),
                   Qt.AlignmentFlag.AlignCenter, f"{self._heading:.0f}°")
        p.end()


# ── Battery Bar ───────────────────────────────────────────────────────────────

class BatteryBar(QWidget):
    """Horizontal battery indicator with color coding."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pct = 0.0
        self.setFixedHeight(22)
        self.setMinimumWidth(80)

    def set_percent(self, pct: float):
        self._pct = max(0.0, min(100.0, pct))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        if self._pct > 50:
            color = QColor("#22c55e")
        elif self._pct > 20:
            color = QColor("#f59e0b")
        else:
            color = QColor("#ef4444")

        # Background
        p.setBrush(QBrush(QColor(Colors.bg_input)))
        p.setPen(QPen(QColor(Colors.border), 1))
        p.drawRoundedRect(0, 0, w - 6, h, 4, 4)

        # Fill
        fill_w = int((w - 6) * self._pct / 100.0)
        if fill_w > 4:
            p.setBrush(QBrush(color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(0, 0, fill_w, h, 4, 4)

        # Terminal nub
        p.setBrush(QBrush(QColor(Colors.border)))
        p.drawRoundedRect(w - 5, h // 4, 5, h // 2, 2, 2)

        # Text
        p.setPen(QColor("white"))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, w - 6, h),
                   Qt.AlignmentFlag.AlignCenter,
                   f"{self._pct:.0f}%" if self._pct >= 0 else "—")
        p.end()


# ── Section Header ────────────────────────────────────────────────────────────

def section_header(text: str, color: str = Colors.blue) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f"""
        color: {color};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding: 4px 0;
        border-bottom: 1px solid {Colors.border};
    """)
    return lbl


# ── Separator ─────────────────────────────────────────────────────────────────

def h_separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"color: {Colors.border};")
    return sep
