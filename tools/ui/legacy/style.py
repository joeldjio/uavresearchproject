"""
Dark modern Qt6 stylesheet for the skymeshx gcs.

Usage
-----
from tools.ui.legacy.style import Colors, DARK_THEME, TAB_STYLESHEET, STATE_COLORS, DRONE_COLORS
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class _Colors:
    """Single source of truth for all UI colour values - improved contrast and accessibility."""

    # Backgrounds (darker for better contrast)
    bg_app: str = "#0a0e1a"
    bg_panel: str = "#0f1420"
    bg_card: str = "#141b2d"
    bg_input: str = "#1a2332"
    bg_hover: str = "#1e2a3f"
    bg_console: str = "#0a0e1a"
    bg_elevated: str = "#141b2d"
    
    # Borders (improved visibility)
    border: str = "#2d3748"
    border_muted: str = "#1e293b"
    border_strong: str = "#3d4d65"
    border_focus: str = "#3b82f6"
    
    # Accent (brighter, more vibrant)
    blue: str = "#3b82f6"
    blue_light: str = "#60a5fa"
    blue_dark: str = "#2563eb"
    blue_dim: str = "#4a6fa5"
    
    # Semantic (improved accessibility)
    green: str = "#10b981"
    green_light: str = "#34d399"
    green_dark: str = "#059669"
    yellow: str = "#f59e0b"
    yellow_light: str = "#fbbf24"
    yellow_dark: str = "#d97706"
    orange: str = "#f97316"
    orange_light: str = "#fb923c"
    orange_dark: str = "#ea580c"
    red: str = "#ef4444"
    red_light: str = "#f87171"
    red_dark: str = "#dc2626"
    purple: str = "#8b5cf6"
    purple_light: str = "#a78bfa"
    purple_dark: str = "#7c3aed"
    teal: str = "#14b8a6"
    cyan: str = "#06b6d4"
    lime: str = "#84cc16"
    pink: str = "#ec4899"
    
    # Text (improved hierarchy)
    text_primary: str = "#f1f5f9"
    text_secondary: str = "#a0aec0"
    text_muted: str = "#6b7280"
    text_dim: str = "#4b5563"
    text_disabled: str = "#374151"
    
    # Sky / Ground (attitude indicator)
    sky: str = "#1e40af"
    earth: str = "#78350f"


Colors = _Colors()


TAB_STYLESHEET = f"""
    QTabWidget::pane {{ 
        border: none; 
        background: {Colors.bg_app}; 
    }}
    QTabBar::tab {{
        background: {Colors.bg_panel};
        color: {Colors.text_dim};
        padding: 12px 24px;
        font-weight: 500;
        font-size: 13px;
        border: none;
        border-bottom: 3px solid transparent;
        margin-right: 2px;
        transition: all 0.2s ease;
    }}
    QTabBar::tab:selected {{
        color: {Colors.text_primary};
        border-bottom: 3px solid {Colors.blue};
        background: {Colors.bg_app};
    }}
    QTabBar::tab:hover:!selected {{
        color: {Colors.text_secondary};
        background: {Colors.bg_hover};
        border-bottom: 3px solid {Colors.blue_dim};
    }}
"""

STATUSBAR_STYLESHEET = f"""
    QStatusBar {{
        background: {Colors.bg_panel};
        color: {Colors.text_dim};
        border-top: 1px solid {Colors.border};
        font-size: 11px;
        padding: 4px 8px;
    }}
"""

DARK_THEME = f"""
QMainWindow, QDialog, QWidget {{
    background-color: {Colors.bg_app};
    color: {Colors.text_primary};
    font-family: 'Segoe UI', 'SF Pro Text', 'Inter', 'Ubuntu', 'Noto Sans', Arial, sans-serif;
    font-size: 13px;
}}

/* ── Tabs (improved visual hierarchy) ── */
QTabWidget::pane {{
    border: 1px solid {Colors.border};
    background-color: {Colors.bg_panel};
    border-radius: 10px;
}}
QTabBar::tab {{
    background: {Colors.bg_input};
    color: {Colors.text_muted};
    padding: 12px 24px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    margin-right: 3px;
    font-weight: 500;
    font-size: 13px;
    min-width: 100px;
}}
QTabBar::tab:selected {{
    background: {Colors.blue};
    color: white;
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    background: {Colors.bg_hover};
    color: {Colors.text_primary};
}}

/* ── GroupBox (improved styling) ── */
QGroupBox {{
    border: 1px solid {Colors.border};
    border-radius: 12px;
    margin-top: 16px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
    color: {Colors.text_secondary};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    background: {Colors.bg_panel};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
    background: {Colors.bg_panel};
}}

/* ── Buttons (modern with smooth transitions) ── */
QPushButton {{
    background-color: {Colors.bg_input};
    color: {Colors.text_primary};
    border: 1px solid {Colors.border};
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: 500;
    font-size: 13px;
    min-height: 36px;
}}
QPushButton:hover {{
    background-color: {Colors.bg_hover};
    border-color: {Colors.border_strong};
    color: white;
}}
QPushButton:pressed {{
    background-color: {Colors.blue_dark};
    transform: scale(0.98);
}}
QPushButton:disabled {{
    color: {Colors.text_disabled};
    border-color: {Colors.border_muted};
    background-color: {Colors.bg_panel};
}}

/* ── Primary Button ── */
QPushButton#btn_primary {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 {Colors.blue_light}, 
                                stop:1 {Colors.blue});
    border-color: {Colors.blue};
    color: white;
    font-weight: 600;
    box-shadow: 0 4px 6px rgba(59, 130, 246, 0.3);
}}
QPushButton#btn_primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 {Colors.blue}, 
                                stop:1 {Colors.blue_dark});
    box-shadow: 0 6px 8px rgba(59, 130, 246, 0.4);
}}
QPushButton#btn_primary:pressed {{
    background: {Colors.blue_dark};
}}

/* ── Danger Button ── */
QPushButton#btn_danger {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 {Colors.red_light}, 
                                stop:1 {Colors.red});
    border-color: {Colors.red};
    color: white;
    font-weight: 600;
    box-shadow: 0 4px 6px rgba(239, 68, 68, 0.3);
}}
QPushButton#btn_danger:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 {Colors.red}, 
                                stop:1 {Colors.red_dark});
    box-shadow: 0 6px 8px rgba(239, 68, 68, 0.4);
}}

/* ── Success Button ── */
QPushButton#btn_success {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 {Colors.green_light}, 
                                stop:1 {Colors.green});
    border-color: {Colors.green};
    color: white;
    font-weight: 600;
    box-shadow: 0 4px 6px rgba(16, 185, 129, 0.3);
}}
QPushButton#btn_success:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 {Colors.green}, 
                                stop:1 {Colors.green_dark});
    box-shadow: 0 6px 8px rgba(16, 185, 129, 0.4);
}}

/* ── Warning Button ── */
QPushButton#btn_warning {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 {Colors.yellow_light}, 
                                stop:1 {Colors.yellow});
    border-color: {Colors.yellow};
    color: white;
    font-weight: 600;
    box-shadow: 0 4px 6px rgba(245, 158, 11, 0.3);
}}
QPushButton#btn_warning:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 {Colors.yellow}, 
                                stop:1 {Colors.yellow_dark});
    box-shadow: 0 6px 8px rgba(245, 158, 11, 0.4);
}}

/* ── Table (improved readability) ── */
QTableWidget {{
    background-color: {Colors.bg_panel};
    alternate-background-color: {Colors.bg_card};
    border: 1px solid {Colors.border};
    border-radius: 10px;
    gridline-color: {Colors.border_muted};
    selection-background-color: {Colors.blue};
    selection-color: white;
}}
QTableWidget::item {{
    padding: 8px 12px;
    border: none;
}}
QTableWidget::item:hover {{
    background-color: {Colors.bg_hover};
}}
QHeaderView::section {{
    background-color: {Colors.bg_input};
    color: {Colors.text_secondary};
    padding: 10px 12px;
    border: none;
    border-bottom: 2px solid {Colors.blue};
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}}

/* ── Input / Combo / Spin (improved focus states) ── */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {Colors.bg_input};
    color: {Colors.text_primary};
    border: 2px solid {Colors.border};
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 32px;
    font-size: 13px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {Colors.border_focus};
    background-color: {Colors.bg_hover};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border-color: {Colors.border_strong};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
    padding-right: 4px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {Colors.text_muted};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {Colors.bg_input};
    border: 1px solid {Colors.border};
    border-radius: 8px;
    selection-background-color: {Colors.blue};
    padding: 4px;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: {Colors.bg_hover};
    border: none;
    width: 20px;
    border-radius: 4px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {Colors.blue_dim};
}}

/* ── ScrollBar (modern minimal design) ── */
QScrollBar:vertical {{
    background: {Colors.bg_panel};
    width: 10px;
    border-radius: 6px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {Colors.border_strong};
    border-radius: 6px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {Colors.blue_dim};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{
    background: {Colors.bg_panel};
    height: 10px;
    border-radius: 6px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {Colors.border_strong};
    border-radius: 6px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ 
    background: {Colors.blue_dim}; 
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── TextEdit (improved console styling) ── */
QTextEdit, QPlainTextEdit {{
    background-color: {Colors.bg_console};
    color: #8be9fd;
    border: 1px solid {Colors.border};
    border-radius: 10px;
    font-family: 'Cascadia Code', 'JetBrains Mono', 'Fira Code', 'SF Mono', 'Consolas', 'Menlo', 'DejaVu Sans Mono', 'Courier New', monospace;
    font-size: 12px;
    padding: 8px;
    line-height: 1.5;
}}

/* ── Slider (modern design) ── */
QSlider::groove:horizontal {{
    height: 6px;
    background: {Colors.border};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {Colors.blue};
    width: 18px;
    height: 18px;
    border-radius: 10px;
    margin: -6px 0;
    border: 2px solid white;
}}
QSlider::handle:horizontal:hover {{
    background: {Colors.blue_light};
    width: 20px;
    height: 20px;
    border-radius: 10px;
    margin: -7px 0;
}}
QSlider::sub-page:horizontal {{
    background: {Colors.blue};
    border-radius: 3px;
}}

/* ── Label (improved typography) ── */
QLabel#label_title {{
    font-size: 24px;
    font-weight: 700;
    color: {Colors.text_primary};
    letter-spacing: 0.5px;
}}
QLabel#label_subtitle {{
    font-size: 13px;
    color: {Colors.text_muted};
    font-weight: 500;
}}
QLabel#status_ok   {{ color: {Colors.green}; font-weight: 600; }}
QLabel#status_warn {{ color: {Colors.yellow}; font-weight: 600; }}
QLabel#status_err  {{ color: {Colors.red}; font-weight: 600; }}

/* ── Separator ── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {Colors.border};
}}

/* ── Tooltip (improved styling) ── */
QToolTip {{
    background-color: {Colors.bg_input};
    color: {Colors.text_primary};
    border: 1px solid {Colors.blue};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ── Progress (modern design) ── */
QProgressBar {{
    background-color: {Colors.bg_input};
    border: 1px solid {Colors.border};
    border-radius: 8px;
    text-align: center;
    color: white;
    font-weight: 600;
    height: 20px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 {Colors.blue_light}, 
                                stop:1 {Colors.blue});
    border-radius: 8px;
}}

/* ── CheckBox (improved styling) ── */
QCheckBox {{
    spacing: 8px;
    color: {Colors.text_primary};
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid {Colors.border};
    background: {Colors.bg_input};
}}
QCheckBox::indicator:hover {{
    border-color: {Colors.blue};
}}
QCheckBox::indicator:checked {{
    background: {Colors.blue};
    border-color: {Colors.blue};
}}

/* ── RadioButton (improved styling) ── */
QRadioButton {{
    spacing: 8px;
    color: {Colors.text_primary};
}}
QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 10px;
    border: 2px solid {Colors.border};
    background: {Colors.bg_input};
}}
QRadioButton::indicator:hover {{
    border-color: {Colors.blue};
}}
QRadioButton::indicator:checked {{
    background: {Colors.blue};
    border-color: {Colors.blue};
}}
"""

# Status badge colors (improved accessibility)
STATE_COLORS = {
    "IDLE": "#64748b",
    "ARMING": "#f59e0b",
    "ARMED": "#f97316",
    "TAKEOFF": "#3b82f6",
    "FLYING": "#10b981",
    "MISSION": "#8b5cf6",
    "LANDING": "#f59e0b",
    "RTL": "#f97316",
    "EMERGENCY": "#ef4444",
    "UNKNOWN": "#374151",
}

# Drone colors (vibrant and distinct)
DRONE_COLORS = [
    "#3b82f6",  # Blue
    "#10b981",  # Green
    "#f59e0b",  # Yellow
    "#ec4899",  # Pink
    "#8b5cf6",  # Purple
    "#14b8a6",  # Teal
    "#f97316",  # Orange
    "#06b6d4",  # Cyan
    "#84cc16",  # Lime
    "#a855f7",  # Violet
]

