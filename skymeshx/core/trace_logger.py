"""Structured trace bundles for offline PX4/Gazebo simulation analysis."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import sys
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional


JsonDict = dict[str, Any]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    slug = re.sub(r"_+", "_", slug).strip("._-")
    return slug or "trace_session"


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _iter_jsonl(path: Path) -> list[JsonDict]:
    rows: list[JsonDict] = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except OSError:
        return rows
    return rows


def analyze_trace_bundle(bundle_path: str | Path) -> JsonDict:
    """Return a compact summary for a trace bundle."""

    root = Path(bundle_path)
    manifest = _read_json(root / "manifest.json", {})
    ui_events = _iter_jsonl(root / "ui_events.jsonl")
    mission_events = _iter_jsonl(root / "mission_trace.jsonl")
    topic_health = _read_json(root / "ros2_topic_health.json", {})

    all_events = ui_events + mission_events
    type_counts = Counter(str(event.get("type", "unknown")) for event in all_events)
    errors = [
        event
        for event in all_events
        if str(event.get("type", "")).lower() == "error"
        or str(event.get("data", {}).get("level", "")).upper() == "ERROR"
    ]
    warnings = [
        event
        for event in all_events
        if str(event.get("type", "")).lower() == "warning"
        or str(event.get("data", {}).get("level", "")).upper() in {"WARN", "WARNING"}
    ]

    video_status: dict[str, Any] = {}
    video_dir = root / "video"
    if video_dir.exists():
        for path in sorted(video_dir.glob("*_stream_probe.json")):
            video_status[path.stem.replace("_stream_probe", "")] = _read_json(path, {})

    return {
        "bundlePath": str(root),
        "manifest": manifest,
        "eventCounts": dict(type_counts),
        "uiEventCount": len(ui_events),
        "missionEventCount": len(mission_events),
        "errorCount": len(errors),
        "warningCount": len(warnings),
        "errors": errors[:20],
        "warnings": warnings[:20],
        "topicHealth": topic_health,
        "videoStatus": video_status,
    }


def format_markdown_report(summary: JsonDict) -> str:
    """Format ``analyze_trace_bundle`` output as a Markdown report."""

    manifest = summary.get("manifest") or {}
    lines = [
        "# Trace Summary",
        "",
        f"- Bundle: `{summary.get('bundlePath', '')}`",
        f"- Scenario: `{manifest.get('scenario', '')}`",
        f"- Created: `{manifest.get('createdAt', '')}`",
        f"- UI events: {summary.get('uiEventCount', 0)}",
        f"- Mission events: {summary.get('missionEventCount', 0)}",
        f"- Errors: {summary.get('errorCount', 0)}",
        f"- Warnings: {summary.get('warningCount', 0)}",
        "",
        "## Event Counts",
        "",
    ]

    event_counts = summary.get("eventCounts") or {}
    if event_counts:
        for event_type, count in sorted(event_counts.items()):
            lines.append(f"- `{event_type}`: {count}")
    else:
        lines.append("- No events recorded.")

    lines.extend(["", "## ROS2 Topic Health", ""])
    topic_health = summary.get("topicHealth") or {}
    if topic_health:
        for topic, health in sorted(topic_health.items()):
            hz = health.get("estimatedHz", health.get("hz", ""))
            age = health.get("lastMessageAgeSec", health.get("lastAgeSec", ""))
            qos = health.get("qos", "")
            lines.append(f"- `{topic}`: hz={hz}, age={age}, qos=`{qos}`")
    else:
        lines.append("- No ROS2 topic health captured.")

    lines.extend(["", "## Video Status", ""])
    video_status = summary.get("videoStatus") or {}
    if video_status:
        for drone_id, status in sorted(video_status.items()):
            state = status.get("status", "")
            url = status.get("url", "")
            port = status.get("port", "")
            lines.append(f"- `{drone_id}`: {state} `{url or port}`")
    else:
        lines.append("- No video status captured.")

    lines.extend(["", "## Errors", ""])
    errors = summary.get("errors") or []
    if errors:
        for event in errors:
            lines.append(f"- `{event.get('ts', '')}` {event.get('source', '')}: {event.get('data', {})}")
    else:
        lines.append("- No errors recorded.")

    lines.append("")
    return "\n".join(lines)


class TraceLogger:
    """Thread-safe JSON trace writer with session/bundle management."""

    _instance: Optional["TraceLogger"] = None
    _instance_lock = threading.Lock()

    def __init__(
        self,
        root: str | Path | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        trace_root = root or os.environ.get("SKYMESHX_TRACE_ROOT") or "trace_runs"
        self.root = Path(trace_root)
        self._monotonic = monotonic or time.monotonic
        self._lock = threading.RLock()
        self._session_path: Optional[Path] = None
        self._last_session_path: Optional[Path] = None
        self._scenario = ""
        self._manifest: JsonDict = {}
        self._topic_health: dict[str, JsonDict] = {}
        self._last_ros2_event_at: dict[str, float] = {}
        self._last_telem_event_at: dict[str, float] = {}
        self._active = False
        # Open file handles kept alive for the duration of a session to avoid
        # the overhead of re-opening on every logged event.
        self._jsonl_handles: dict[str, Any] = {}

    @classmethod
    def get(cls) -> "TraceLogger":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_for_tests(cls) -> None:
        with cls._instance_lock:
            cls._instance = None

    @property
    def session_active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def session_path(self) -> str:
        with self._lock:
            return str(self._session_path or "")

    @property
    def session_scenario(self) -> str:
        with self._lock:
            return self._scenario

    def start_session(self, scenario: str, sim_config: dict | None = None) -> str:
        with self._lock:
            if self._active:
                raise RuntimeError("Trace session already active")

            sim_config = dict(sim_config or {})
            self.root.mkdir(parents=True, exist_ok=True)
            self._scenario = _safe_slug(scenario)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_path = self._unique_session_path(f"{stamp}_{self._scenario}")
            session_path.mkdir(parents=True, exist_ok=False)
            (session_path / "video").mkdir()
            (session_path / "config").mkdir()

            self._session_path = session_path
            self._last_session_path = session_path
            self._topic_health = {}
            self._last_ros2_event_at = {}
            self._active = True

            self._write_json(session_path / "config" / "sim_config.json", sim_config)
            self._manifest = self._build_manifest(sim_config)
            self._write_manifest()
            self._touch("ui_events.jsonl")
            self._touch("mission_trace.jsonl")
            self._touch("apf_events.jsonl")
            self._write_topic_health()
            self._copy_latest_syslog()
            self.log_ui_event("app/session", {"action": "started", "scenario": self._scenario})
            return str(session_path)

    def stop_session(self) -> str:
        with self._lock:
            if not self._active or self._session_path is None:
                return str(self._last_session_path or "")

            # Snapshot values needed for log_ui_event before releasing the lock.
            scenario = self._scenario
            session_path = self._session_path

        # Call log_ui_event OUTSIDE the lock to avoid deadlock (it acquires
        # _lock internally via _append_jsonl).
        self.log_ui_event("app/session", {"action": "stopped", "scenario": scenario})

        with self._lock:
            if not self._active or self._session_path is None:
                return str(self._last_session_path or "")
            self._manifest["stoppedAt"] = _now_iso()
            self._write_manifest()
            self._write_topic_health()
            # Close all open JSONL file handles for this session.
            for handle in self._jsonl_handles.values():
                try:
                    handle.close()
                except Exception:
                    pass
            self._jsonl_handles.clear()
            path = self._session_path
            self._active = False
            self._session_path = None
            return str(path)

    def log_ui_event(self, event_type: str, data: dict | None = None) -> None:
        self._append_jsonl("ui_events.jsonl", event_type, "ui", data or {})

    def log_mission_event(self, event_type: str, data: dict | None = None) -> None:
        self._append_jsonl("mission_trace.jsonl", event_type, "mission", data or {})

    def log_apf_event(self, event_type: str, data: dict | None = None) -> None:
        self._append_jsonl("apf_events.jsonl", event_type, "safety", data or {})

    def log_tab_change(self, tab_index: int, tab_id: str) -> None:
        self._append_jsonl(
            "ui_events.jsonl",
            "ui/tab_change",
            "ui",
            {"tabIndex": int(tab_index), "tabId": str(tab_id)},
        )

    def log_drone_command(self, drone_id: str, command: str, **kwargs: Any) -> None:
        data: JsonDict = {"droneId": str(drone_id), "command": str(command)}
        data.update({k: v for k, v in kwargs.items()})
        self._append_jsonl("ui_events.jsonl", "drone/command", "ui", data)

    def log_telemetry_snapshot(
        self,
        drone_id: str,
        lat: float,
        lon: float,
        alt_rel: float,
        heading: float,
        armed: bool,
        fsm_state: str,
        throttle_s: float = 5.0,
    ) -> None:
        """Write a position snapshot to mission_trace at most every *throttle_s* seconds."""
        now = self._monotonic()
        key = f"telem:{drone_id}"
        with self._lock:
            if now - self._last_telem_event_at.get(key, -9999.0) < throttle_s:
                return
            self._last_telem_event_at[key] = now
        self._append_jsonl(
            "mission_trace.jsonl",
            "drone/position",
            "telemetry",
            {
                "droneId": str(drone_id),
                "lat": round(float(lat), 7),
                "lon": round(float(lon), 7),
                "altRel": round(float(alt_rel), 2),
                "heading": round(float(heading), 1),
                "armed": bool(armed),
                "fsmState": str(fsm_state),
            },
        )

    def log_wp_tracking(
        self,
        drone_id: str,
        seq: int,
        drone_lat: float,
        drone_lon: float,
        target_lat: float,
        target_lon: float,
        distance_m: float,
        frame: str,
        acceptance_radius_m: float | None = None,
    ) -> None:
        data: JsonDict = {
            "droneId": drone_id,
            "currentSeq": int(seq),
            "droneLat": float(drone_lat),
            "droneLon": float(drone_lon),
            "targetLat": float(target_lat),
            "targetLon": float(target_lon),
            "distanceToWpM": float(distance_m),
            "frame": str(frame),
        }
        if acceptance_radius_m is not None:
            data["acceptanceRadiusM"] = float(acceptance_radius_m)
        self.log_mission_event("wp_tracking", data)

    def log_ros2_health(self, topic: str, hz: float, last_age_s: float, qos: str = "") -> None:
        with self._lock:
            if not self._active or self._session_path is None:
                return

            topic_key = str(topic)
            previous = self._topic_health.get(topic_key, {})
            message_count = int(previous.get("messageCount", 0)) + 1
            health = {
                "seen": True,
                "messageCount": message_count,
                "estimatedHz": float(hz),
                "lastMessageAgeSec": float(last_age_s),
                "qos": str(qos or ""),
                "lastUpdated": _now_iso(),
            }
            self._topic_health[topic_key] = health
            self._write_topic_health()

            now = self._monotonic()
            if now - self._last_ros2_event_at.get(topic_key, -9999.0) >= 1.0:
                self._last_ros2_event_at[topic_key] = now
                self._append_jsonl_unlocked(
                    "ui_events.jsonl",
                    "topic_health",
                    "ros2",
                    {"topic": topic_key, **health},
                )

    def log_video_status(self, drone_id: str, status: str, port: int | None = None) -> None:
        data: JsonDict = {
            "droneId": str(drone_id),
            "status": str(status),
            "updatedAt": _now_iso(),
        }
        if port is not None:
            data["port"] = int(port)
            data["url"] = f"udp://0.0.0.0:{int(port)}"

        with self._lock:
            if not self._active or self._session_path is None:
                return
            safe_drone_id = _safe_slug(str(drone_id))
            self._write_json(self._session_path / "video" / f"{safe_drone_id}_stream_probe.json", data)
            self._append_jsonl_unlocked("ui_events.jsonl", "video_status", "video", data)

    def log_error(self, source: str, msg: str) -> None:
        self._append_jsonl("ui_events.jsonl", "error", str(source), {"message": str(msg)})

    def export_markdown(self, path: str | Path | None = None) -> str:
        with self._lock:
            bundle = self._session_path or self._last_session_path
            if bundle is None:
                raise RuntimeError("No trace session available")
            output = Path(path) if path else bundle / "trace_summary.md"

        summary = analyze_trace_bundle(bundle)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(format_markdown_report(summary), encoding="utf-8")
        return str(output)

    def _unique_session_path(self, folder_name: str) -> Path:
        candidate = self.root / folder_name
        if not candidate.exists():
            return candidate
        index = 2
        while True:
            next_candidate = self.root / f"{folder_name}_{index}"
            if not next_candidate.exists():
                return next_candidate
            index += 1

    def _build_manifest(self, sim_config: dict) -> JsonDict:
        px4 = dict(sim_config.get("px4") or {})
        for key in ("model", "world", "simMode", "px4Dir", "gitCommit"):
            if key in sim_config and key not in px4:
                px4[key] = sim_config[key]

        vehicles = sim_config.get("vehicles") or []
        gazebo_world = sim_config.get("gazeboWorld") or {}
        if not gazebo_world and ("worldProfile" in sim_config or "world" in sim_config):
            gazebo_world = {
                "profile": sim_config.get("worldProfile", ""),
                "world": sim_config.get("world", ""),
                "modelPose": sim_config.get("modelPose", ""),
                "env": sim_config.get("worldEnv", {}),
            }

        return {
            "schemaVersion": 1,
            "scenario": self._scenario,
            "createdAt": _now_iso(),
            "host": {
                "os": platform.system().lower(),
                "platform": platform.platform(),
                "release": platform.release(),
                "python": sys.version.split()[0],
                "machine": platform.machine(),
                "rosDistro": os.environ.get("ROS_DISTRO", ""),
            },
            "px4": px4,
            "vehicles": vehicles,
            "gazeboWorld": gazebo_world,
            "artifacts": {
                "appLog": "app.log",
                "uiEvents": "ui_events.jsonl",
                "missionTrace": "mission_trace.jsonl",
                "apfEvents": "apf_events.jsonl",
                "topicHealth": "ros2_topic_health.json",
                "video": "video/",
                "config": "config/",
            },
        }

    def _append_jsonl(self, filename: str, event_type: str, source: str, data: dict) -> None:
        with self._lock:
            self._append_jsonl_unlocked(filename, event_type, source, data)

    def _append_jsonl_unlocked(self, filename: str, event_type: str, source: str, data: dict) -> None:
        if not self._active or self._session_path is None:
            return
        event = {
            "ts": _now_iso(),
            "type": str(event_type),
            "source": str(source),
            "data": data,
        }
        # Re-use a persistent file handle for the session lifetime to avoid
        # the syscall overhead of opening the file on every logged event.
        handle = self._jsonl_handles.get(filename)
        if handle is None:
            path = self._session_path / filename
            handle = path.open("a", encoding="utf-8")
            self._jsonl_handles[filename] = handle
        handle.write(json.dumps(event, ensure_ascii=False, default=_json_default) + "\n")
        handle.flush()

    def _touch(self, filename: str) -> None:
        if self._session_path is not None:
            (self._session_path / filename).touch()

    def _write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=_json_default) + "\n",
            encoding="utf-8",
        )

    def _write_manifest(self) -> None:
        if self._session_path is not None:
            self._write_json(self._session_path / "manifest.json", self._manifest)

    def _write_topic_health(self) -> None:
        if self._session_path is not None:
            self._write_json(self._session_path / "ros2_topic_health.json", self._topic_health)

    def _copy_latest_syslog(self) -> None:
        if self._session_path is None:
            return
        try:
            project_root = self.root.parent if self.root.name == "trace_runs" else Path.cwd()
            syslog_dir = project_root / "logs" / "syslogs"
            candidates = sorted(syslog_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
            if candidates:
                shutil.copy2(candidates[0], self._session_path / "app.log")
        except OSError:
            return
