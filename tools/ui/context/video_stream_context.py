"""
VideoStreamContext — QML-exposed video stream probe / status context.

Phase 1 (MVP): probe / status / per-drone config — no live decoded video.
Phase 2:       GStreamer/QtMultimedia decoding (separate implementation).

Status state machine
--------------------
  unconfigured → waiting → receiving
                         → stalled
                         → error
  Any state    → unconfigured  (on stopStream / reconfigure)

Registered in ServiceLocator as "videoStream".
Exposed to QML as context property "videoStream".

QML Properties (per-selected-drone)
------------------------------------
  streamActive : bool        — True when status == "receiving"
  streamStatus : str         — unconfigured | waiting | receiving | stalled | error
  streamUrl    : str         — current configured URL
  droneId      : str         — currently selected drone
  fps          : real        — last measured fps (0 if not receiving)
  latencyMs    : real        — estimated latency in ms

QML Slots
---------
  setVideoSource(droneId, host, port, protocol)
  startStream(url, droneId)
  stopStream(droneId)
  startVideoProbe(droneId)
  stopVideoProbe(droneId)
  getVideoStatus(droneId) -> dict

QML Signals
-----------
  videoStatusChanged(droneId, statusDict)
  streamError(droneId, message)
"""

from __future__ import annotations

import importlib
import socket
import threading
import time
from typing import Dict, Optional

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, QMetaObject, Qt, Q_ARG
from PySide6.QtGui import QColor, QImage
from PySide6.QtCore import QSize
from PySide6.QtQuick import QQuickImageProvider

# Video status constants
STATUS_UNCONFIGURED = "unconfigured"
STATUS_WAITING      = "waiting"
STATUS_RECEIVING    = "receiving"
STATUS_STALLED      = "stalled"
STATUS_ERROR        = "error"

# PX4 Gazebo default video ports per drone index
_DEFAULT_PORTS = {0: 5600, 1: 5601, 2: 5602, 3: 5603, 4: 5604}
_PROBE_TIMEOUT  = 2.0   # seconds
_MAX_RENDER_FPS = 15.0
_MAX_FRAME_WIDTH = 960
_STALL_TIMEOUT  = 5.0   # seconds without data → stalled


class _DroneVideoState:
    """Internal per-drone video state."""

    def __init__(self) -> None:
        self.status: str = STATUS_UNCONFIGURED
        self.host: str = "0.0.0.0"
        self.port: int = 5600
        self.protocol: str = "rtp-h264-udp"
        self.url: str = ""
        self.fps: float = 0.0
        self.latency_ms: float = 0.0
        self.last_frame_ts: float = 0.0
        self.frame_revision: int = 0
        self.has_frame: bool = False
        self.frame: Optional[QImage] = None
        self.frame_lock = threading.Lock()
        self.probe_thread: Optional[threading.Thread] = None
        self.probe_stop = threading.Event()
        self.decoder_thread: Optional[threading.Thread] = None
        self.decoder_stop = threading.Event()
        self.target: str = ""
        self.last_error: str = ""


class VideoFrameProvider(QQuickImageProvider):
    """QML image provider backed by the latest decoded frame per drone."""

    def __init__(self, context: "VideoStreamContext") -> None:
        super().__init__(QQuickImageProvider.Image)
        self._context = context

    def requestImage(self, image_id: str, size: QSize, requested_size: QSize) -> QImage:
        drone_id = image_id.split("?", 1)[0]
        image = self._context.frame_image(drone_id)
        if image is None or image.isNull():
            image = QImage(320, 180, QImage.Format.Format_RGB32)
            image.fill(QColor("#05070d"))
        if requested_size.isValid() and requested_size.width() > 0 and requested_size.height() > 0:
            image = image.scaled(requested_size)
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image


class VideoStreamContext(QObject):
    """QML-callable video stream probe and status manager."""

    # Signals
    videoStatusChanged = Signal(str, "QVariant", arguments=["droneId", "statusDict"])
    frameChanged       = Signal(str, str,         arguments=["droneId", "frameUrl"])
    activeTargetChanged = Signal(str,             arguments=["target"])
    streamError        = Signal(str, str,         arguments=["droneId", "message"])
    logMessage         = Signal(str, str,         arguments=["level", "text"])

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._states: Dict[str, _DroneVideoState] = {}
        self._selected_drone: str = ""
        self._active_drone_id: str = ""
        self._active_target: str = ""
        self._provider = VideoFrameProvider(self)

        # Stall detection timer — runs every 2s
        self._stall_timer = QTimer(self)
        self._stall_timer.setInterval(2000)
        self._stall_timer.timeout.connect(self._check_stalls)
        self._stall_timer.start()

    # ── QML Properties ────────────────────────────────────────────────────

    @Property(bool, notify=videoStatusChanged)
    def streamActive(self) -> bool:
        s = self._states.get(self._selected_drone)
        return s is not None and s.status == STATUS_RECEIVING

    @Property(str, notify=videoStatusChanged)
    def streamStatus(self) -> str:
        s = self._states.get(self._selected_drone)
        return s.status if s else STATUS_UNCONFIGURED

    @Property(str, notify=videoStatusChanged)
    def streamUrl(self) -> str:
        s = self._states.get(self._selected_drone)
        return s.url if s else ""

    @Property(str, notify=videoStatusChanged)
    def droneId(self) -> str:
        return self._selected_drone

    @Property(str, notify=activeTargetChanged)
    def activeTarget(self) -> str:
        return self._active_target

    @Property(str, notify=activeTargetChanged)
    def activeDroneId(self) -> str:
        return self._active_drone_id

    @Property(int, notify=frameChanged)
    def frameRevision(self) -> int:
        s = self._states.get(self._selected_drone)
        return s.frame_revision if s else 0

    @Property(float, notify=videoStatusChanged)
    def fps(self) -> float:
        s = self._states.get(self._selected_drone)
        return s.fps if s else 0.0

    @Property(float, notify=videoStatusChanged)
    def latencyMs(self) -> float:
        s = self._states.get(self._selected_drone)
        return s.latency_ms if s else 0.0

    # ── Slots ─────────────────────────────────────────────────────────────

    @Slot(str)
    def selectDrone(self, drone_id: str) -> None:
        """Set the currently selected drone for QML property bindings."""
        self._selected_drone = drone_id
        self.videoStatusChanged.emit(drone_id, self._status_dict(drone_id))

    @Slot(str, str)
    @Slot(str, str, int, str)
    def setVideoSource(self, drone_id: str, host: str, port: Optional[int] = None, protocol: str = "rtp-h264-udp") -> None:
        """
        Configure video source for a drone without starting a probe.

        protocol: "rtp-h264-udp" | "rtsp" | "mjpeg-http"
        """
        state = self._ensure_state(drone_id)
        if port is None:
            host, port, protocol = _parse_url(host)
        state.host = host
        state.port = int(port)
        state.protocol = protocol
        state.url = _build_url(host, port, protocol)
        self.logMessage.emit("INFO", f"[VIDEO] {drone_id}: source = {state.url}")

    @Slot(str, result="QVariant")
    def getVideoStatus(self, drone_id: str) -> dict:
        """Return status dict for a drone."""
        return self._status_dict(drone_id)

    @Slot(str, result=str)
    def frameUrl(self, drone_id: str) -> str:
        state = self._states.get(drone_id)
        rev = state.frame_revision if state else 0
        return f"image://videoStream/{drone_id}?rev={rev}"

    @Slot(str)
    def setActiveTarget(self, target: str) -> None:
        target = target if target in {"map", "gimbal", ""} else ""
        if target == self._active_target:
            return
        self._active_target = target
        self.activeTargetChanged.emit(target)
        if self._active_drone_id:
            self._emit_status(self._active_drone_id)

    @Slot(str, str, str, result=bool)
    @Slot(str, str, result=bool)
    def startStream(self, url: str, drone_id: str, target: str = "gimbal") -> bool:
        """
        Configure and start decoding a stream URL.

        url examples: "udp://0.0.0.0:5600", "rtsp://192.168.1.1:554/stream"
        target: "map" or "gimbal". Only one target renders frames at a time.
        """
        target = target if target in {"map", "gimbal"} else "gimbal"
        if self._active_drone_id and self._active_drone_id != drone_id:
            self.stopStream(self._active_drone_id)
        elif self._active_drone_id == drone_id:
            self._stop_decoder(drone_id)
            self.stopVideoProbe(drone_id)

        host, port, protocol = _parse_url(url)
        self.setVideoSource(drone_id, host, port, protocol)
        self.stopVideoProbe(drone_id)
        state = self._ensure_state(drone_id)
        state.target = target
        state.status = STATUS_WAITING
        state.last_error = ""
        self._active_drone_id = drone_id
        self.setActiveTarget(target)
        self._emit_status(drone_id)
        return self._start_decoder(drone_id, state)

    @Slot()
    @Slot(str)
    def stopStream(self, drone_id: str = "") -> None:
        """Stop decoder/probe and reset status to unconfigured."""
        if not drone_id:
            drone_id = self._active_drone_id
        if not drone_id:
            return
        self._stop_decoder(drone_id)
        self.stopVideoProbe(drone_id)
        state = self._states.get(drone_id)
        if state:
            state.status = STATUS_UNCONFIGURED
            state.fps = 0.0
            state.target = ""
            state.has_frame = False
            state.last_error = ""
            self._emit_status(drone_id)
        if self._active_drone_id == drone_id:
            self._active_drone_id = ""
            self.setActiveTarget("")
        self.logMessage.emit("INFO", f"[VIDEO] {drone_id}: stream stopped")

    @Slot(str)
    def startVideoProbe(self, drone_id: str) -> None:
        """
        Start a background probe for the configured drone video source.

        Phase 1 MVP: tests UDP socket reachability.
        """
        state = self._ensure_state(drone_id)
        # Stop any existing probe
        if state.probe_thread and state.probe_thread.is_alive():
            state.probe_stop.set()
            state.probe_thread.join(timeout=1.0)

        state.probe_stop = threading.Event()
        state.status = STATUS_WAITING
        self._emit_status(drone_id)
        self.logMessage.emit("INFO", f"[VIDEO] {drone_id}: probing {state.url} …")

        t = threading.Thread(
            target=self._probe_loop,
            args=(drone_id, state),
            daemon=True,
        )
        state.probe_thread = t
        t.start()

    @Slot(str)
    def stopVideoProbe(self, drone_id: str) -> None:
        """Stop the background probe for a drone."""
        state = self._states.get(drone_id)
        if state and state.probe_thread:
            state.probe_stop.set()
            if state.probe_thread.is_alive():
                state.probe_thread.join(timeout=1.0)
            state.probe_thread = None

    def image_provider(self) -> VideoFrameProvider:
        """Return the QML image provider registered as image://videoStream."""
        return self._provider

    def frame_image(self, drone_id: str) -> Optional[QImage]:
        """Return a copy of the latest decoded frame for QML."""
        state = self._states.get(drone_id)
        if not state:
            return None
        with state.frame_lock:
            if state.frame is None or state.frame.isNull():
                return None
            return state.frame.copy()

    # ── Internal ──────────────────────────────────────────────────────────

    def _ensure_state(self, drone_id: str) -> _DroneVideoState:
        if drone_id not in self._states:
            state = _DroneVideoState()
            # Auto-assign default PX4 Gazebo port based on drone index suffix
            idx = _drone_index(drone_id)
            state.port = _DEFAULT_PORTS.get(idx, 5600 + idx)
            state.url = _build_url(state.host, state.port, state.protocol)
            self._states[drone_id] = state
        return self._states[drone_id]

    def _start_decoder(self, drone_id: str, state: _DroneVideoState) -> bool:
        self._stop_decoder(drone_id)
        state.decoder_stop = threading.Event()
        thread = threading.Thread(
            target=self._decoder_loop,
            args=(drone_id, state),
            daemon=True,
            name=f"video-decoder-{drone_id}",
        )
        state.decoder_thread = thread
        thread.start()
        self.logMessage.emit("INFO", f"[VIDEO] {drone_id}: decoder starting for {state.target}")
        return True

    def _stop_decoder(self, drone_id: str) -> None:
        state = self._states.get(drone_id)
        if not state:
            return
        if state.decoder_thread and state.decoder_thread.is_alive():
            state.decoder_stop.set()
            state.decoder_thread.join(timeout=1.5)
        state.decoder_thread = None

    def _decoder_loop(self, drone_id: str, state: _DroneVideoState) -> None:
        # Prefer native GStreamer-Python (python3-gst-1.0) for RTP/H.264 —
        # it works without OpenCV and is always available alongside GStreamer.
        if state.protocol == "rtp-h264-udp":
            if _gst_available():
                self._decoder_loop_gst(drone_id, state)
            else:
                self._set_error(
                    drone_id, state,
                    "GStreamer Python bindings (python3-gst-1.0) not found.\n"
                    "Fix: sudo apt install python3-gst-1.0 gstreamer1.0-plugins-good "
                    "gstreamer1.0-plugins-bad gstreamer1.0-libav",
                )
            return

        # RTSP / MJPEG fallback: use OpenCV
        cv2 = _load_cv2()
        if cv2 is None:
            self._set_error(
                drone_id, state,
                "OpenCV (cv2) not installed.\n"
                "Fix: sudo apt install python3-opencv",
            )
            return

        cap = cv2.VideoCapture(state.url)
        if not cap or not cap.isOpened():
            self._set_error(drone_id, state,
                            f"Could not open video stream: {state.url}")
            return

        frame_count = 0
        fps_window_start = time.monotonic()
        min_frame_interval = 1.0 / _MAX_RENDER_FPS
        last_emit = 0.0
        try:
            while not state.decoder_stop.is_set():
                ok, frame = cap.read()
                now = time.monotonic()
                if not ok or frame is None:
                    if state.status == STATUS_RECEIVING and now - state.last_frame_ts > _STALL_TIMEOUT:
                        state.status = STATUS_STALLED
                        QMetaObject.invokeMethod(
                            self, "_emit_status_queued",
                            Qt.ConnectionType.QueuedConnection,
                            Q_ARG(str, drone_id),
                        )
                    state.decoder_stop.wait(timeout=0.03)
                    continue

                if now - last_emit < min_frame_interval:
                    continue
                last_emit = now

                image = _frame_to_qimage(cv2, frame)
                if image is None or image.isNull():
                    continue

                self._push_frame(drone_id, state, image, now, frame_count, fps_window_start)
                frame_count += 1
                elapsed = max(0.001, now - fps_window_start)
                if elapsed >= 1.0:
                    frame_count = 0
                    fps_window_start = now
        except Exception as exc:
            err_msg = str(exc)
            state.status = STATUS_ERROR
            state.last_error = err_msg
            QMetaObject.invokeMethod(
                self, "_set_error_from_main",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, drone_id), Q_ARG(str, err_msg),
            )
        finally:
            try:
                cap.release()
            except Exception:
                pass

    def _decoder_loop_gst(self, drone_id: str, state: _DroneVideoState) -> None:
        """GStreamer-Python decoder for RTP/H.264 streams (PX4 Gazebo default)."""
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst, GLib

        Gst.init(None)

        pipeline_desc = (
            f"udpsrc port={state.port} "
            f"caps=\"application/x-rtp,media=video,encoding-name=H264,payload=96\" "
            f"! rtph264depay ! h264parse ! avdec_h264 "
            f"! videoconvert ! video/x-raw,format=RGB "
            f"! appsink name=sink drop=true sync=false max-buffers=1"
        )

        pipeline = Gst.parse_launch(pipeline_desc)
        sink = pipeline.get_by_name("sink")
        sink.set_property("emit-signals", False)  # we use pull_sample()

        pipeline.set_state(Gst.State.PLAYING)
        self.logMessage.emit(
            "INFO", f"[VIDEO] {drone_id}: GStreamer pipeline started on udp://0.0.0.0:{state.port}"
        )

        frame_count = 0
        fps_window_start = time.monotonic()
        min_frame_interval = 1.0 / _MAX_RENDER_FPS
        last_emit = 0.0

        try:
            while not state.decoder_stop.is_set():
                sample = sink.emit("pull-sample")
                if sample is None:
                    # No frame yet — brief wait then retry
                    state.decoder_stop.wait(timeout=0.03)
                    continue

                buf = sample.get_buffer()
                caps = sample.get_caps()
                structure = caps.get_structure(0)
                width  = structure.get_value("width")
                height = structure.get_value("height")

                ok, map_info = buf.map(Gst.MapFlags.READ)
                if not ok:
                    continue
                try:
                    raw = bytes(map_info.data)
                finally:
                    buf.unmap(map_info)

                if not raw or width <= 0 or height <= 0:
                    continue

                now = time.monotonic()
                if now - last_emit < min_frame_interval:
                    continue
                last_emit = now

                # Scale down if wider than max
                if width > _MAX_FRAME_WIDTH:
                    scale = _MAX_FRAME_WIDTH / width
                    new_w = _MAX_FRAME_WIDTH
                    new_h = max(1, int(height * scale))
                    image = QImage(raw, width, height,
                                   width * 3, QImage.Format.Format_RGB888)
                    image = image.scaled(new_w, new_h,
                                         Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation).copy()
                else:
                    image = QImage(raw, width, height,
                                   width * 3, QImage.Format.Format_RGB888).copy()

                if image.isNull():
                    continue

                self._push_frame(drone_id, state, image, now, frame_count, fps_window_start)
                frame_count += 1
                elapsed = max(0.001, now - fps_window_start)
                if elapsed >= 1.0:
                    frame_count = 0
                    fps_window_start = now

        except Exception as exc:
            err_msg = str(exc)
            QMetaObject.invokeMethod(
                self, "_set_error_from_main",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, drone_id), Q_ARG(str, err_msg),
            )
        finally:
            pipeline.set_state(Gst.State.NULL)
            self.logMessage.emit("INFO", f"[VIDEO] {drone_id}: GStreamer pipeline stopped")

    def _push_frame(self, drone_id: str, state: _DroneVideoState,
                    image: "QImage", now: float,
                    frame_count: int, fps_window_start: float) -> None:
        """Store a decoded frame and schedule a QML update from the main thread."""
        elapsed = max(0.001, now - fps_window_start)
        if elapsed >= 1.0:
            state.fps = frame_count / elapsed

        with state.frame_lock:
            state.frame = image
            state.has_frame = True
            state.frame_revision += 1
        state.last_frame_ts = now

        if state.status != STATUS_RECEIVING:
            state.status = STATUS_RECEIVING
            self.logMessage.emit("INFO", f"[VIDEO] {drone_id}: live frames receiving")

        frame_url = self.frameUrl(drone_id)
        QMetaObject.invokeMethod(
            self, "_emit_frame_from_main",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, drone_id), Q_ARG(str, frame_url),
        )

    @Slot(str, str)
    def _emit_frame_from_main(self, drone_id: str, frame_url: str) -> None:
        """Relay frameChanged and status update on the main thread."""
        self.frameChanged.emit(drone_id, frame_url)
        self._emit_status(drone_id)

    @Slot(str)
    def _emit_status_queued(self, drone_id: str) -> None:
        """Relay _emit_status to the main thread (safe to call from any thread)."""
        self._emit_status(drone_id)

    @Slot(str, str)
    def _log_queued(self, level: str, message: str) -> None:
        """Relay logMessage to the main thread (safe to call from any thread)."""
        self.logMessage.emit(level, message)

    @Slot(str, str)
    def _set_error_from_main(self, drone_id: str, message: str) -> None:
        """Relay error signal to the main thread."""
        self._emit_status(drone_id)
        self.streamError.emit(drone_id, message)
        self.logMessage.emit("WARN", f"[VIDEO] {drone_id}: {message}")

    def _set_error(self, drone_id: str, state: _DroneVideoState, message: str) -> None:
        state.status = STATUS_ERROR
        state.last_error = message
        self._emit_status(drone_id)
        self.streamError.emit(drone_id, message)
        self.logMessage.emit("WARN", f"[VIDEO] {drone_id}: {message}")

    def _probe_loop(self, drone_id: str, state: _DroneVideoState) -> None:
        """
        Phase-1 UDP probe: tries to bind to the port and listen for data.
        Sets status to receiving if any bytes arrive within _PROBE_TIMEOUT,
        otherwise stays waiting (port open) or sets error.
        """
        while not state.probe_stop.is_set():
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.settimeout(_PROBE_TIMEOUT)

                # Bind to listen port
                bind_host = "0.0.0.0"
                try:
                    sock.bind((bind_host, state.port))
                except OSError:
                    # Port already in use by GStreamer etc. — assume stream active
                    sock.close()
                    sock = None
                    state.status = STATUS_RECEIVING
                    # Do NOT update last_frame_ts here — stall detection must
                    # remain able to transition to STATUS_STALLED if no real
                    # frames arrive after the port-in-use assumption.
                    QMetaObject.invokeMethod(
                        self, "_emit_status_queued",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(str, drone_id),
                    )
                    QMetaObject.invokeMethod(
                        self, "_log_queued",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(str, "INFO"), Q_ARG(str, f"[VIDEO] {drone_id}: port {state.port} in use — assuming stream active"),
                    )
                    state.probe_stop.wait(timeout=3.0)
                    continue

                data, _ = sock.recvfrom(65535)
                sock.close()
                sock = None

                state.status = STATUS_RECEIVING
                state.last_frame_ts = time.monotonic()
                state.fps = 0.0   # Phase 2 will decode and measure fps
                QMetaObject.invokeMethod(
                    self, "_emit_status_queued",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, drone_id),
                )
                QMetaObject.invokeMethod(
                    self, "_log_queued",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, "INFO"), Q_ARG(str, f"[VIDEO] {drone_id}: stream receiving on port {state.port}"),
                )

                # Keep checking every 3s to detect stalls
                state.probe_stop.wait(timeout=3.0)

            except socket.timeout:
                if state.status != STATUS_WAITING:
                    state.status = STATUS_WAITING
                    QMetaObject.invokeMethod(
                        self, "_emit_status_queued",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(str, drone_id),
                    )
                state.probe_stop.wait(timeout=1.0)

            except Exception as exc:
                # Close the socket to prevent FD leak
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass
                    sock = None
                exc_msg = str(exc)
                state.status = STATUS_ERROR
                QMetaObject.invokeMethod(
                    self, "_set_error_from_main",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, drone_id), Q_ARG(str, exc_msg),
                )
                QMetaObject.invokeMethod(
                    self, "_log_queued",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, "WARN"), Q_ARG(str, f"[VIDEO] {drone_id}: probe error — {exc_msg}"),
                )
                state.probe_stop.wait(timeout=3.0)

    def _check_stalls(self) -> None:
        """Called every 2s — transition receiving→stalled if no data recently."""
        now = time.monotonic()
        # Snapshot keys to avoid RuntimeError if the dict is modified during iteration
        for drone_id, state in list(self._states.items()):
            if state.status == STATUS_RECEIVING:
                if state.last_frame_ts > 0 and now - state.last_frame_ts > _STALL_TIMEOUT:
                    state.status = STATUS_STALLED
                    self._emit_status(drone_id)
                    self.logMessage.emit("WARN", f"[VIDEO] {drone_id}: stream stalled")

    def _emit_status(self, drone_id: str) -> None:
        d = self._status_dict(drone_id)
        self.videoStatusChanged.emit(drone_id, d)
        # Notify TraceLogger
        try:
            from skymeshx.core.trace_logger import TraceLogger

            TraceLogger.get().log_video_status(drone_id, d.get("status", ""), d.get("port"))
        except Exception:
            pass

    def _status_dict(self, drone_id: str) -> dict:
        state = self._states.get(drone_id)
        if not state:
            return {
                "status": STATUS_UNCONFIGURED,
                "url": "",
                "host": "0.0.0.0",
                "port": 5600,
                "protocol": "rtp-h264-udp",
                "fps": 0.0,
                "latencyMs": 0.0,
                "activeTarget": self._active_target,
                "target": "",
                "hasFrame": False,
                "frameRevision": 0,
                "frameUrl": self.frameUrl(drone_id),
                "lastError": "",
            }
        return {
            "status": state.status,
            "url": state.url,
            "host": state.host,
            "port": state.port,
            "protocol": state.protocol,
            "fps": state.fps,
            "latencyMs": state.latency_ms,
            # activeTarget reflects the target of THIS drone's stream so QML
            # checks like `activeTarget === "gimbal"` work per-drone.
            "activeTarget": state.target if state.target else self._active_target,
            "target": state.target,
            "hasFrame": state.has_frame,
            "frameRevision": state.frame_revision,
            "frameUrl": self.frameUrl(drone_id),
            "lastError": state.last_error,
        }

    def shutdown(self) -> None:
        """Stop background workers on application shutdown."""
        for drone_id in list(self._states):
            self.stopStream(drone_id)


# ── URL helpers ────────────────────────────────────────────────────────────

def _build_url(host: str, port: int, protocol: str) -> str:
    if protocol == "rtsp":
        return f"rtsp://{host}:{port}/stream"
    if protocol == "mjpeg-http":
        return f"http://{host}:{port}/stream"
    # default: rtp-h264-udp
    return f"udp://{host}:{port}"


def _parse_url(url: str):
    """Parse url → (host, port, protocol). Returns defaults on failure.

    Logs a warning when falling back to the default so misconfigured URLs
    are not silently ignored.
    """
    import logging as _logging
    try:
        if url.startswith("udp://"):
            rest = url[6:]
            host, port_s = rest.rsplit(":", 1)
            return host, int(port_s), "rtp-h264-udp"
        if url.startswith("rtsp://"):
            rest = url[7:].split("/")[0]
            if ":" in rest:
                host, port_s = rest.rsplit(":", 1)
                return host, int(port_s), "rtsp"
            return rest, 554, "rtsp"
        if url.startswith("http://"):
            rest = url[7:].split("/")[0]
            if ":" in rest:
                host, port_s = rest.rsplit(":", 1)
                return host, int(port_s), "mjpeg-http"
            return rest, 8080, "mjpeg-http"
    except Exception:
        pass
    _logging.getLogger(__name__).warning(
        "[VIDEO] _parse_url: unrecognised URL %r — falling back to 0.0.0.0:5600 rtp-h264-udp", url
    )
    return "0.0.0.0", 5600, "rtp-h264-udp"


def _drone_index(drone_id: str) -> int:
    """Return 0-based index from drone_id like 'px4_1', 'uav_2', 'drone3'."""
    import re
    m = re.search(r"(\d+)$", drone_id)
    if m:
        return max(0, int(m.group(1)) - 1)
    return 0


def _load_cv2():
    try:
        return importlib.import_module("cv2")
    except Exception:
        return None


def _gst_available() -> bool:
    """Return True if python3-gst-1.0 (GObject Introspection) is importable."""
    try:
        import gi  # noqa: F401
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst  # noqa: F401
        return True
    except Exception:
        return False


def _frame_to_qimage(cv2, frame) -> Optional[QImage]:
    try:
        height, width = frame.shape[:2]
        if width <= 0 or height <= 0:
            return None
        if width > _MAX_FRAME_WIDTH:
            scale = _MAX_FRAME_WIDTH / float(width)
            frame = cv2.resize(frame, (_MAX_FRAME_WIDTH, max(1, int(height * scale))))
            height, width = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        bytes_per_line = 3 * width
        return QImage(rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).copy()
    except Exception:
        return None
