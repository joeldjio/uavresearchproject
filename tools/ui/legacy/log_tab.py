"""
Log Tab — System log viewer + telemetry data export.
"""
import csv
import json
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QTextEdit, QFormLayout, QFileDialog, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QFont

from tools.ui.legacy.widgets import section_header, h_separator


class LogTab(QWidget):

    def __init__(self, swarm_backend, parent=None):
        super().__init__(parent)
        self._swarm    = swarm_backend
        self._log_entries: list = []
        self._snap_buffer: list = []
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # Top bar
        top = QHBoxLayout()
        top.addWidget(section_header("System Log", "#3b82f6"))
        top.addStretch()

        self._combo_filter = QComboBox()
        self._combo_filter.addItems(["ALL", "INFO", "WARN", "ERROR"])
        self._combo_filter.currentTextChanged.connect(self._apply_filter)
        top.addWidget(QLabel("Filter:"))
        top.addWidget(self._combo_filter)

        self._inp_search = QLineEdit()
        self._inp_search.setPlaceholderText("Search…")
        self._inp_search.setMaximumWidth(200)
        self._inp_search.textChanged.connect(self._apply_filter)
        top.addWidget(self._inp_search)

        btn_clear = QPushButton("🗑 Clear")
        btn_clear.clicked.connect(self._clear_log)
        top.addWidget(btn_clear)

        btn_export = QPushButton("💾 Export Log")
        btn_export.clicked.connect(self._export_log)
        top.addWidget(btn_export)

        root.addLayout(top)

        # Main log display
        self._log_txt = QTextEdit()
        self._log_txt.setReadOnly(True)
        self._log_txt.setStyleSheet("""
            QTextEdit {
                background: #0d1117;
                color: #e2e8f0;
                border: 1px solid #2d3748;
                border-radius: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                padding: 8px;
            }
        """)
        root.addWidget(self._log_txt, stretch=1)

        # Telemetry export section
        root.addWidget(h_separator())
        root.addWidget(section_header("Telemetry Export", "#22c55e"))

        export_row = QHBoxLayout()

        grp_export = QGroupBox("Export Recorded Telemetry")
        ex_form = QFormLayout(grp_export)

        self._combo_drone_export = QComboBox()
        ex_form.addRow("Drone:", self._combo_drone_export)

        self._combo_fmt = QComboBox()
        self._combo_fmt.addItems(["CSV", "JSON"])
        ex_form.addRow("Format:", self._combo_fmt)

        btn_exp_tel = QPushButton("💾 Export Telemetry")
        btn_exp_tel.setObjectName("btn_success")
        btn_exp_tel.clicked.connect(self._export_telemetry)
        ex_form.addRow(btn_exp_tel)

        export_row.addWidget(grp_export)

        # Recent files
        grp_files = QGroupBox("Recent Logs")
        files_lay = QVBoxLayout(grp_files)
        self._files_list = QTextEdit()
        self._files_list.setReadOnly(True)
        self._files_list.setMaximumHeight(100)
        self._files_list.setStyleSheet(
            "background:#0d1117; color:#64748b; font-family:Consolas; font-size:11px;"
        )
        files_lay.addWidget(self._files_list)
        btn_refresh_files = QPushButton("🔄 Refresh")
        btn_refresh_files.clicked.connect(self._refresh_files)
        files_lay.addWidget(btn_refresh_files)
        export_row.addWidget(grp_files)

        root.addLayout(export_row)
        self._refresh_files()

    def _connect_signals(self):
        self._swarm.log_message.connect(self.append_log)
        self._swarm.drone_added.connect(self._refresh_drone_combo)
        self._swarm.drone_removed.connect(self._refresh_drone_combo)

    # ── Public API ────────────────────────────────────────────────────────

    def append_log(self, level: str, message: str):
        ts    = time.strftime("%H:%M:%S")
        entry = {"ts": ts, "level": level, "msg": message}
        self._log_entries.append(entry)
        self._render_entry(entry)

    # ── Internal ──────────────────────────────────────────────────────────

    def _render_entry(self, entry: dict):
        level = entry["level"]
        color_map = {
            "INFO":  "#94a3b8",
            "WARN":  "#f59e0b",
            "ERROR": "#ef4444",
            "DEBUG": "#64748b",
        }
        color = color_map.get(level, "#94a3b8")
        badge_colors = {
            "INFO":  "#1e3a5f",
            "WARN":  "#451a03",
            "ERROR": "#450a0a",
        }
        bg = badge_colors.get(level, "#1e2535")
        html = (
            f'<span style="color:#4a5568;">[{entry["ts"]}]</span> '
            f'<span style="background:{bg};color:{color};padding:1px 6px;'
            f'border-radius:3px;font-weight:700;font-size:10px;">{level}</span> '
            f'<span style="color:#e2e8f0;">{entry["msg"]}</span>'
        )
        self._log_txt.append(html)

    def _apply_filter(self):
        level_filter = self._combo_filter.currentText()
        search       = self._inp_search.text().lower()
        self._log_txt.clear()
        for entry in self._log_entries:
            if level_filter != "ALL" and entry["level"] != level_filter:
                continue
            if search and search not in entry["msg"].lower():
                continue
            self._render_entry(entry)

    def _clear_log(self):
        self._log_entries.clear()
        self._log_txt.clear()

    def _export_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Log", "logs/", "Text (*.txt);;JSON (*.json)")
        if not path:
            return
        if path.endswith(".json"):
            with open(path, "w") as f:
                json.dump(self._log_entries, f, indent=2)
        else:
            with open(path, "w") as f:
                for e in self._log_entries:
                    f.write(f"[{e['ts']}] {e['level']}: {e['msg']}\n")
        self.append_log("INFO", f"Log exported to {path}")

    def _export_telemetry(self):
        did = self._combo_drone_export.currentText()
        b   = self._swarm.get_backend(did)
        if not b or not b.drone:
            self.append_log("WARN", "No connected drone selected.")
            return
        fmt = self._combo_fmt.currentText()
        ext = ".csv" if fmt == "CSV" else ".json"
        path, _ = QFileDialog.getSaveFileName(self, "Export Telemetry", f"logs/{did}_telemetry{ext}", f"{fmt} (*{ext})")
        if not path:
            return
        try:
            if fmt == "CSV":
                result = b.drone.export_csv()
                with open(path, "w") as f:
                    f.write(result)
            else:
                history = b.drone.get_history(last_n=10000)
                with open(path, "w") as f:
                    json.dump(history, f, indent=2)
            self.append_log("INFO", f"Telemetry exported: {path}")
        except Exception as e:
            self.append_log("ERROR", f"Export failed: {e}")

    def _refresh_drone_combo(self, _=None):
        current = self._combo_drone_export.currentText()
        self._combo_drone_export.clear()
        for did in self._swarm.all_backends().keys():
            self._combo_drone_export.addItem(did)
        idx = self._combo_drone_export.findText(current)
        if idx >= 0:
            self._combo_drone_export.setCurrentIndex(idx)

    def _refresh_files(self):
        log_dir = Path("logs")
        if not log_dir.exists():
            self._files_list.setPlainText("logs/ directory not found")
            return
        files = sorted(log_dir.rglob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)[:10]
        if files:
            self._files_list.setPlainText("\n".join(str(f) for f in files))
        else:
            self._files_list.setPlainText("No log files found.")
