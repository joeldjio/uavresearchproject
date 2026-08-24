"""
Replay — deterministic replay of recorded telemetry logs.

Enables:
    - Re-running a recorded flight through the same analysis pipeline
    - Regression testing against known-good data
    - Offline algorithm evaluation without hardware

Supports:
    - SkyMeshX CSV/JSON logs
    - ArduPilot .bin (DataFlash) via pymavlink DFReader
    - rosbag2 (if ros2 available)

Usage:
    from skymeshx.simulation.replay import TelemetryReplay

    replay = TelemetryReplay("logs/flight_2025-01-01.csv")
    for snapshot in replay.play(speed=2.0):
        print(snapshot.lat, snapshot.alt)
        # Feed to analysis / plotting / algorithm

    # Or: replay against running experiment
    replay.attach_experiment(experiment)
    replay.run()
"""
import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generator, Iterator, List, Optional

from skymeshx.autopilot.base import TelemetrySnapshot
from skymeshx.exceptions import DependencyError, InvalidDataFormatError


@dataclass
class ReplayFrame:
    """Single frame of replayed telemetry."""
    timestamp:  float
    snapshot:   TelemetrySnapshot
    raw:        dict    # original row / message


class TelemetryReplay:
    """
    Replays telemetry from a recorded log at configurable speed.
    """

    def __init__(self, path: str):
        self.path   = Path(path)
        self._frames: List[ReplayFrame] = []
        self._loaded = False
        self._on_frame: List[Callable[[ReplayFrame], None]] = []

    def load(self):
        suffix = self.path.suffix.lower()
        if suffix == ".csv":
            self._load_csv()
        elif suffix == ".json":
            self._load_json()
        elif suffix == ".bin":
            self._load_bin()
        else:
            raise InvalidDataFormatError(f"Unsupported log format: {suffix!r}. Supported: .csv, .json, .bin")
        self._loaded = True
        print(f"[replay] Loaded {len(self._frames)} frames from {self.path.name}")

    def on_frame(self, cb: Callable[[ReplayFrame], None]):
        """Register callback fired for every replayed frame."""
        self._on_frame.append(cb)

    def play(
        self,
        speed:    float = 1.0,
        start_t:  Optional[float] = None,
        end_t:    Optional[float] = None,
    ) -> Generator[ReplayFrame, None, None]:
        """
        Generator: yields each frame at wall-clock speed * speed.
        speed=1.0 → realtime, speed=10.0 → 10x faster, speed=0 → no sleep.
        """
        if not self._loaded:
            self.load()
        frames = self._frames
        if start_t is not None:
            frames = [f for f in frames if f.timestamp >= start_t]
        if end_t is not None:
            frames = [f for f in frames if f.timestamp <= end_t]
        if not frames:
            return

        t0_wall = time.monotonic()
        t0_log  = frames[0].timestamp

        for frame in frames:
            if speed > 0:
                target_wall = t0_wall + (frame.timestamp - t0_log) / speed
                sleep = target_wall - time.monotonic()
                if sleep > 0:
                    time.sleep(sleep)
            for cb in self._on_frame:
                try:
                    cb(frame)
                except Exception as e:
                    print(f"[replay] callback error: {e}")
            yield frame

    def run(self, speed: float = 1.0):
        """Run replay to completion (non-generator)."""
        for _ in self.play(speed=speed):
            pass

    @property
    def duration(self) -> float:
        if len(self._frames) < 2:
            return 0.0
        return self._frames[-1].timestamp - self._frames[0].timestamp

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    # ── Loaders ────────────────────────────────────────────────────────────

    def _load_csv(self):
        with open(self.path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                s = TelemetrySnapshot()
                s.timestamp   = float(row.get("timestamp", 0))
                s.lat         = float(row.get("lat", 0))
                s.lon         = float(row.get("lon", 0))
                s.alt         = float(row.get("alt", 0))
                s.alt_rel     = float(row.get("alt_rel", 0))
                s.roll        = float(row.get("roll", 0))
                s.pitch       = float(row.get("pitch", 0))
                s.yaw         = float(row.get("yaw", 0))
                s.groundspeed = float(row.get("groundspeed", 0))
                s.battery_pct = float(row.get("battery_pct", -1))
                s.battery_v   = float(row.get("battery_v", 0))
                s.armed       = row.get("armed", "False") == "True"
                s.flight_mode = row.get("flight_mode", "UNKNOWN")
                self._frames.append(ReplayFrame(s.timestamp, s, dict(row)))

    def _load_json(self):
        with open(self.path) as f:
            data = json.load(f)
        entries = data if isinstance(data, list) else data.get("telemetry", [])
        for row in entries:
            s = TelemetrySnapshot()
            for k in TelemetrySnapshot.__slots__:
                if k in row:
                    object.__setattr__(s, k, row[k])
            self._frames.append(ReplayFrame(s.timestamp, s, row))

    def _load_bin(self):
        """Load ArduPilot DataFlash .bin log via pymavlink DFReader."""
        try:
            from pymavlink import DFReader
        except ImportError:
            raise DependencyError("pymavlink", "pip install pymavlink")
        log = DFReader.DFReader_binary(str(self.path))
        while True:
            msg = log.recv_msg()
            if msg is None:
                break
            t = msg.get_type()
            s = TelemetrySnapshot()
            s.timestamp = getattr(msg, "TimeUS", 0) / 1e6
            if t == "GPS":
                s.lat = getattr(msg, "Lat", 0)
                s.lon = getattr(msg, "Lng", 0)
                s.alt = getattr(msg, "Alt", 0)
            elif t == "ATT":
                s.roll  = getattr(msg, "Roll",  0)
                s.pitch = getattr(msg, "Pitch", 0)
                s.yaw   = getattr(msg, "Yaw",   0)
            elif t == "BATT":
                s.battery_v   = getattr(msg, "Volt", 0)
                s.battery_pct = getattr(msg, "Rem",  -1)
            if s.timestamp > 0:
                self._frames.append(ReplayFrame(s.timestamp, s, {}))
        self._frames.sort(key=lambda f: f.timestamp)
