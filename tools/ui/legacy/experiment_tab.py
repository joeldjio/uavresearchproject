"""
Experiment Tab — Scenario runner, metrics, results viewer.
"""
import json
import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QLineEdit,
    QComboBox, QDoubleSpinBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QCheckBox, QListWidget,
    QListWidgetItem, QFormLayout, QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QColor

from tools.ui.legacy.widgets import section_header, h_separator, MetricCard

try:
    from skymeshx.experiment.scenario import Scenario as _Scenario, ScenarioRunner as _ScenarioRunner
except ImportError:  # pragma: no cover
    _Scenario = None        # type: ignore
    _ScenarioRunner = None  # type: ignore


class ExperimentWorker(QObject):
    """Runs ScenarioRunner in background thread and emits progress."""
    result_ready  = Signal(dict)
    log_message   = Signal(str)
    finished      = Signal()

    def __init__(self, scenario_dict: dict, use_sitl: bool):
        super().__init__()
        self._scenario_dict = scenario_dict
        self._use_sitl      = use_sitl

    def run(self) -> None:
        if _Scenario is None or _ScenarioRunner is None:
            self.log_message.emit("[experiment] skymeshx SDK not installed.")
            self.finished.emit()
            return
        try:
            scenario = _Scenario(**self._scenario_dict)
            runner   = _ScenarioRunner(
                scenario,
                results_dir="results",
                on_result=lambda r: self.result_ready.emit(r.to_dict()),
                use_sitl=self._use_sitl,
            )
            self.log_message.emit(f"[experiment] Starting: {scenario.name}")
            runner.run()
            self.log_message.emit(f"[experiment] Done. {len(runner.results)} run(s) completed.")
        except Exception as exc:
            self.log_message.emit(f"[experiment] ERROR: {exc}")
        finally:
            self.finished.emit()


class ExperimentTab(QWidget):

    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker_thread = None
        self._results: list = []
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        # ── Left: Scenario builder ─────────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(10)

        left.addWidget(section_header("Scenario Builder", "#8b5cf6"))

        grp_basic = QGroupBox("Scenario")
        form = QFormLayout(grp_basic)

        self._inp_name = QLineEdit("hover_stability_test")
        form.addRow("Name:", self._inp_name)

        self._combo_ap = QComboBox()
        self._combo_ap.addItems(["ardupilot", "px4"])
        form.addRow("Autopilot:", self._combo_ap)

        self._combo_veh = QComboBox()
        self._combo_veh.addItems(["copter", "plane", "rover"])
        form.addRow("Vehicle:", self._combo_veh)

        self._spin_lat = QDoubleSpinBox()
        self._spin_lat.setDecimals(6)
        self._spin_lat.setRange(-90, 90)
        self._spin_lat.setValue(48.1374)
        form.addRow("Home Lat:", self._spin_lat)

        self._spin_lon = QDoubleSpinBox()
        self._spin_lon.setDecimals(6)
        self._spin_lon.setRange(-180, 180)
        self._spin_lon.setValue(11.5754)
        form.addRow("Home Lon:", self._spin_lon)

        self._spin_speedup = QDoubleSpinBox()
        self._spin_speedup.setRange(1.0, 10.0)
        self._spin_speedup.setValue(1.0)
        self._spin_speedup.setSuffix("×")
        form.addRow("SITL Speedup:", self._spin_speedup)

        self._spin_timeout = QDoubleSpinBox()
        self._spin_timeout.setRange(10, 3600)
        self._spin_timeout.setValue(300)
        self._spin_timeout.setSuffix(" s")
        form.addRow("Timeout:", self._spin_timeout)

        self._chk_sitl = QCheckBox("Use SITL (simulation)")
        self._chk_sitl.setChecked(True)
        form.addRow(self._chk_sitl)

        left.addWidget(grp_basic)

        # Mission steps
        grp_mission = QGroupBox("Mission Steps (JSON)")
        m_lay = QVBoxLayout(grp_mission)
        self._txt_mission = QTextEdit()
        self._txt_mission.setMinimumHeight(120)
        self._txt_mission.setPlaceholderText(
            'e.g.\n[\n  {"cmd": "takeoff", "alt": 10},\n  {"cmd": "hover", "duration": 30},\n  {"cmd": "land"}\n]'
        )
        self._txt_mission.setPlainText(json.dumps([
            {"cmd": "takeoff", "alt": 10},
            {"cmd": "hover",   "duration": 30},
            {"cmd": "land"},
        ], indent=2))
        m_lay.addWidget(self._txt_mission)
        left.addWidget(grp_mission)

        # Params (grid search)
        grp_params = QGroupBox("Parameter Grid (JSON)")
        p_lay = QVBoxLayout(grp_params)
        self._txt_params = QTextEdit()
        self._txt_params.setMinimumHeight(60)
        self._txt_params.setPlaceholderText('e.g. {"speed": [1, 3, 5], "alt": [10, 20]}')
        self._txt_params.setPlainText('{}')
        p_lay.addWidget(self._txt_params)
        left.addWidget(grp_params)

        # Metrics
        grp_metrics = QGroupBox("Metrics to Collect")
        met_lay = QVBoxLayout(grp_metrics)
        self._metrics_list = QListWidget()
        self._metrics_list.setMaximumHeight(100)
        for m in ["position_error", "battery_drain", "flight_time",
                  "max_speed", "mean_altitude", "path_length"]:
            item = QListWidgetItem(m)
            item.setCheckState(Qt.CheckState.Checked if m in ["position_error","flight_time","battery_drain"] else Qt.CheckState.Unchecked)
            self._metrics_list.addItem(item)
        met_lay.addWidget(self._metrics_list)
        left.addWidget(grp_metrics)

        btn_row = QHBoxLayout()
        self._btn_run = QPushButton("▶ Run Experiment")
        self._btn_run.setObjectName("btn_primary")
        self._btn_run.clicked.connect(self._run_experiment)
        btn_row.addWidget(self._btn_run)

        btn_save = QPushButton("💾 Save Scenario")
        btn_save.clicked.connect(self._save_scenario)
        btn_row.addWidget(btn_save)

        btn_load = QPushButton("📂 Load Scenario")
        btn_load.clicked.connect(self._load_scenario)
        btn_row.addWidget(btn_load)
        left.addLayout(btn_row)

        left.addStretch()
        root.addLayout(left, stretch=0)

        # ── Right: results + metrics ──────────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(10)

        right.addWidget(section_header("Experiment Results", "#22c55e"))

        # KPI row
        kpi_row = QHBoxLayout()
        self._card_runs    = MetricCard("Runs",       "", "🔁", "#3b82f6")
        self._card_success = MetricCard("Success",    "", "✅", "#22c55e")
        self._card_fail    = MetricCard("Failed",     "", "❌", "#ef4444")
        self._card_time    = MetricCard("Total Time", "s","⏱",  "#f59e0b")
        for c in [self._card_runs, self._card_success, self._card_fail, self._card_time]:
            kpi_row.addWidget(c)
        right.addLayout(kpi_row)

        # Results table
        self._results_table = QTableWidget(0, 6)
        self._results_table.setHorizontalHeaderLabels(
            ["Run ID", "Params", "Success", "Duration(s)", "Metrics", "Log"]
        )
        self._results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._results_table.setAlternatingRowColors(True)
        self._results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._results_table.clicked.connect(self._on_result_selected)
        right.addWidget(self._results_table, stretch=1)

        # Detail panel
        right.addWidget(section_header("Run Detail", "#f59e0b"))
        self._detail_txt = QTextEdit()
        self._detail_txt.setReadOnly(True)
        self._detail_txt.setMaximumHeight(160)
        self._detail_txt.setStyleSheet(
            "background: #0d1117; color: #8be9fd; font-family: Consolas; font-size: 12px;"
        )
        right.addWidget(self._detail_txt)

        # Live log
        right.addWidget(section_header("Experiment Log", "#94a3b8"))
        self._log_txt = QTextEdit()
        self._log_txt.setReadOnly(True)
        self._log_txt.setMaximumHeight(120)
        self._log_txt.setStyleSheet(
            "background: #0d1117; color: #8be9fd; font-family: Consolas; font-size: 11px;"
        )
        right.addWidget(self._log_txt)

        root.addLayout(right, stretch=1)

    # ── Slots ─────────────────────────────────────────────────────────────

    def _build_scenario_dict(self) -> dict:
        try:
            mission = json.loads(self._txt_mission.toPlainText())
        except Exception:
            mission = []
        try:
            params = json.loads(self._txt_params.toPlainText())
        except Exception:
            params = {}
        metrics = [
            self._metrics_list.item(i).text()
            for i in range(self._metrics_list.count())
            if self._metrics_list.item(i).checkState() == Qt.CheckState.Checked
        ]
        return {
            "name":      self._inp_name.text(),
            "autopilot": self._combo_ap.currentText(),
            "vehicle":   self._combo_veh.currentText(),
            "home_lat":  self._spin_lat.value(),
            "home_lon":  self._spin_lon.value(),
            "speedup":   self._spin_speedup.value(),
            "timeout_s": self._spin_timeout.value(),
            "mission":   mission,
            "params":    params,
            "metrics":   metrics,
        }

    def _run_experiment(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return
        worker = ExperimentWorker(self._build_scenario_dict(), self._chk_sitl.isChecked())
        worker.result_ready.connect(self._on_result)
        worker.log_message.connect(self._append_log)
        worker.finished.connect(self._on_finished)
        self._btn_run.setEnabled(False)
        self._btn_run.setText("⏳ Running…")
        self._worker_thread = threading.Thread(target=worker.run, daemon=True)
        self._worker_thread.start()

    def _on_result(self, result: dict):
        self._results.append(result)
        self._refresh_table()
        self._refresh_kpis()

    def _on_finished(self):
        self._btn_run.setEnabled(True)
        self._btn_run.setText("▶ Run Experiment")

    def _append_log(self, msg: str):
        self._log_txt.append(msg)
        self.log_message.emit("INFO", msg)

    def _refresh_table(self):
        self._results_table.setRowCount(len(self._results))
        for r, res in enumerate(self._results):
            vals = [
                res.get("run_id", "—"),
                json.dumps(res.get("params", {})),
                "✅" if res.get("success") else "❌",
                f"{res.get('end_time',0)-res.get('start_time',0):.1f}",
                str(res.get("metrics", {})),
                res.get("log_path", "—"),
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 2:
                    item.setForeground(QColor("#22c55e" if res.get("success") else "#ef4444"))
                self._results_table.setItem(r, c, item)

    def _refresh_kpis(self):
        total   = len(self._results)
        success = sum(1 for r in self._results if r.get("success"))
        fail    = total - success
        t_total = sum(r.get("end_time",0)-r.get("start_time",0) for r in self._results)
        self._card_runs.set_value(total)
        self._card_success.set_value(success)
        self._card_fail.set_value(fail)
        self._card_time.set_value(t_total, "{:.0f}")

    def _on_result_selected(self, index):
        r = index.row()
        if r < len(self._results):
            self._detail_txt.setPlainText(json.dumps(self._results[r], indent=2))

    def _save_scenario(self) -> None:
        if _Scenario is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Scenario", "scenarios/", "JSON (*.json)")
        if path:
            _Scenario(**self._build_scenario_dict()).save(path)

    def _load_scenario(self) -> None:
        if _Scenario is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load Scenario", "scenarios/", "JSON (*.json)")
        if path:
            s = _Scenario.load(path)
            self._inp_name.setText(s.name)
            self._txt_mission.setPlainText(json.dumps(s.mission, indent=2))
            self._txt_params.setPlainText(json.dumps(s.params, indent=2))
