#!/usr/bin/env python3
"""
Gazebo → ArduPilot MAVLink Sensor-Bridge (ohne ROS 2).

Eingänge (Gazebo Topics):
  /flow_camera/image   (gz.msgs.Image)
  /lidar/scan          (gz.msgs.LaserScan)

Ausgaben an ArduPilot (MAVLink):
  OPTICAL_FLOW_RAD     — berechneter Optical Flow (Farneback)
  DISTANCE_SENSOR      — Bodenabstand (aus GLOBAL_POSITION_INT.relative_alt)
  OBSTACLE_DISTANCE    — 72 Sektoren aus dem 360°-LiDAR für Hinderniserkennung

Hinweise:
  - ArduPilot-Parameter für die Bridge: FLOW_TYPE=5, RNGFND1_TYPE=10,
    RNGFND1_ORIENT=25, PRX1_TYPE=2, AVOID_ENABLE=7, AVOID_MARGIN=2
  - Kameraausrichtung: Standard = nach unten, X/Y-Richtung per FLOW_SWAP_XY /
    FLOW_X_SIGN / FLOW_Y_SIGN anpassbar
  - Hardware-kompatibel: --mavlink kann auf echte FC-Verbindung zeigen,
    z. B. udpin:0.0.0.0:14550 (UDP) oder /dev/ttyACM0:57600 (Serial)

Verwendung:
    python3 gazebo_mavlink_sensor_bridge.py [--mavlink CONN] [--no-display]
    python3 gazebo_mavlink_sensor_bridge.py --no-display          # headless
    python3 gazebo_mavlink_sensor_bridge.py --mavlink /dev/ttyACM0:115200
"""

from __future__ import annotations

import argparse
import math
import signal
import sys
import threading
import time
from typing import Optional

import cv2
import numpy as np
from pymavlink import mavutil

# Lazy imports aus gz — damit läuft das Skript auch auf Maschinen ohne
# gz.transport (Import-Fehler wird klar gemeldet).
try:
    from gz.msgs10.image_pb2 import Image as GzImage
    from gz.msgs10.laserscan_pb2 import LaserScan as GzLaserScan
    from gz.transport13 import Node as GzNode
    _GZ_AVAILABLE = True
except ImportError as _gz_err:
    _GZ_AVAILABLE = False
    _gz_import_error = str(_gz_err)

# ─── Konfiguration ───────────────────────────────────────────────────────────

DEFAULT_CAMERA_TOPIC  = "/flow_camera/image"
DEFAULT_LIDAR_TOPIC   = "/lidar/scan"
DEFAULT_MAVLINK       = "udpin:0.0.0.0:14550"

# Kamera-FOV (horizontal, Bogenmass)
CAMERA_H_FOV_RAD      = math.radians(60.0)

# Kameraausrichtung — nach unten zeigend:
# Y-Verschiebung im Bild → Flow in Sensor-X-Richtung
# X-Verschiebung im Bild → Flow in Sensor-Y-Richtung
FLOW_SWAP_XY          = True
FLOW_X_SIGN           = -1.0
FLOW_Y_SIGN           =  1.0

FLOW_SENSOR_ID        = 0
RANGEFINDER_ID        = 0

FLOW_MIN_DT_S         = 0.01   # unter 10 ms: überspringen
FLOW_MAX_DT_S         = 0.20   # über 200 ms: überspringen (Sprung)
FLOW_MAX_RAD_S        = 4.0    # EKF-Grenze

# LiDAR → OBSTACLE_DISTANCE: 72 gleichmäßige Sektoren à 5°
LIDAR_BIN_COUNT       = 72
LIDAR_INCREMENT_DEG   = 360.0 / LIDAR_BIN_COUNT
LIDAR_ANGLE_OFFSET_DEG = -180.0    # Startwinkel des ersten Sektors (FRD)

# Zeitabstand zwischen OBSTACLE_DISTANCE-Paketen (Netz entlasten)
LIDAR_SEND_INTERVAL_S = 0.10   # ~10 Hz

# ─── Gemeinsamer Zustand ─────────────────────────────────────────────────────

class _State:
    """Geteilter Zustand — alle Felder unter self.lock schützen."""

    def __init__(self) -> None:
        self.lock                   = threading.Lock()
        self.mav: Optional[mavutil.mavfile] = None
        self.mav_ready              = False
        self.relative_alt_m         = 0.20
        self.rollspeed              = 0.0
        self.pitchspeed             = 0.0
        self.yawspeed               = 0.0
        self.previous_gray: Optional[np.ndarray] = None
        self.previous_camera_time: Optional[float] = None
        self.latest_flow_view: Optional[np.ndarray] = None
        self.latest_lidar_view: Optional[np.ndarray] = None
        self.flow_count             = 0
        self.lidar_count            = 0
        self.last_lidar_send_time   = 0.0
        self.running                = True


_state = _State()


# ─── Hilfsfunktionen ─────────────────────────────────────────────────────────

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _image_to_bgr(msg: "GzImage") -> Optional[np.ndarray]:
    w, h = int(msg.width), int(msg.height)
    if w <= 0 or h <= 0 or not msg.data:
        return None
    raw = np.frombuffer(msg.data, dtype=np.uint8)
    gray_n, rgb_n, rgba_n = w * h, w * h * 3, w * h * 4
    try:
        if raw.size >= rgba_n:
            return cv2.cvtColor(raw[:rgba_n].reshape((h, w, 4)), cv2.COLOR_RGBA2BGR)
        if raw.size >= rgb_n:
            return cv2.cvtColor(raw[:rgb_n].reshape((h, w, 3)),  cv2.COLOR_RGB2BGR)
        if raw.size >= gray_n:
            return cv2.cvtColor(raw[:gray_n].reshape((h, w)),    cv2.COLOR_GRAY2BGR)
    except ValueError:
        pass
    return None


def _flow_quality(gray: np.ndarray, roi_flow: np.ndarray) -> int:
    """Qualitätswert 0–255: Textur × Anteil endlicher, kleiner Flow-Vektoren."""
    texture = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    t_score = _clamp(texture / 250.0, 0.0, 1.0)
    mag     = np.linalg.norm(roi_flow, axis=2)
    finite  = float(np.mean(np.isfinite(mag)))
    small   = float(np.mean(mag < 20.0))
    return int(_clamp(255.0 * t_score * finite * small, 0.0, 255.0))


def _draw_flow(
    frame: np.ndarray,
    flow: np.ndarray,
    ix: float, iy: float,
    quality: int, dt: float,
) -> np.ndarray:
    view = frame.copy()
    h, w = frame.shape[:2]
    step, scale = 20, 4.0
    for y in range(step // 2, h, step):
        for x in range(step // 2, w, step):
            dx, dy = float(flow[y, x, 0]), float(flow[y, x, 1])
            if not (math.isfinite(dx) and math.isfinite(dy)):
                continue
            cv2.arrowedLine(view, (x, y),
                            (int(round(x + dx * scale)), int(round(y + dy * scale))),
                            (0, 255, 0), 1, tipLength=0.3)
    cv2.putText(view, f"Flow X={ix:+.4f} rad  Y={iy:+.4f} rad",
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(view, f"dt={dt * 1000:.1f} ms  Qualitaet={quality}",
                (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 255), 2, cv2.LINE_AA)
    return view


# ─── gz.transport Callbacks ──────────────────────────────────────────────────

def _camera_callback(msg: "GzImage") -> None:
    frame = _image_to_bgr(msg)
    if frame is None:
        return

    now  = time.monotonic()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    with _state.lock:
        prev_gray  = _state.previous_gray
        prev_time  = _state.previous_camera_time
        _state.previous_gray        = gray
        _state.previous_camera_time = now
        mav        = _state.mav
        mav_ready  = _state.mav_ready
        alt_m      = max(0.05, _state.relative_alt_m)
        rollspeed  = _state.rollspeed
        pitchspeed = _state.pitchspeed
        yawspeed   = _state.yawspeed

    if prev_gray is None or prev_time is None:
        return
    dt = now - prev_time
    if not (FLOW_MIN_DT_S <= dt <= FLOW_MAX_DT_S):
        return

    flow = cv2.calcOpticalFlowFarneback(
        prev_gray, gray, None,
        pyr_scale=0.5, levels=3, winsize=21,
        iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
    )

    h, w = gray.shape
    my, mx = max(5, h // 10), max(5, w // 10)
    roi = flow[my:h - my, mx:w - mx]

    med_dx = float(np.median(roi[..., 0]))
    med_dy = float(np.median(roi[..., 1]))

    fx = w / (2.0 * math.tan(CAMERA_H_FOV_RAD / 2.0))
    fy = fx

    if FLOW_SWAP_XY:
        ix = FLOW_X_SIGN * (med_dy / fy)
        iy = FLOW_Y_SIGN * (med_dx / fx)
    else:
        ix = FLOW_X_SIGN * (med_dx / fx)
        iy = FLOW_Y_SIGN * (med_dy / fy)

    max_int = FLOW_MAX_RAD_S * dt
    ix = _clamp(ix, -max_int, max_int)
    iy = _clamp(iy, -max_int, max_int)

    quality  = _flow_quality(gray, roi)
    int_us   = int(dt * 1_000_000)
    ts_us    = int(time.time() * 1_000_000)

    if mav_ready and mav is not None:
        # OPTICAL_FLOW_RAD — ArduPilot erwartet FLOW_TYPE=5 (MAVLink)
        mav.mav.optical_flow_rad_send(
            ts_us,
            FLOW_SENSOR_ID,
            int_us,
            float(ix),
            float(iy),
            float(rollspeed  * dt),
            float(pitchspeed * dt),
            float(yawspeed   * dt),
            0,          # gyro_x_rate_integral (nicht genutzt)
            quality,
            0,          # time_delta_distance_us
            float(alt_m),
        )
        # DISTANCE_SENSOR (nach unten, ORIENT=25) — Bodenabstand aus relative_alt
        # Hardware-Hinweis: Für echte Hardware einen echten Downward-Rangefinder
        # anschließen und diesen Block entfernen oder mit echten Messwerten füllen.
        min_cm = 5
        max_cm = 3000
        cur_cm = int(_clamp(alt_m * 100.0, min_cm, max_cm))
        mav.mav.distance_sensor_send(
            int(time.monotonic() * 1000) & 0xFFFFFFFF,
            min_cm, max_cm, cur_cm,
            mavutil.mavlink.MAV_DISTANCE_SENSOR_LASER,
            RANGEFINDER_ID,
            mavutil.mavlink.MAV_SENSOR_ROTATION_PITCH_270,   # ORIENT=25 → nach unten
            255,    # covariance
            0.0, 0.0,
            [0.0, 0.0, 0.0, 0.0],
            100,    # signal_quality
        )

    with _state.lock:
        _state.latest_flow_view = _draw_flow(frame, flow, ix, iy, quality, dt)
        _state.flow_count += 1


def _lidar_callback(msg: "GzLaserScan") -> None:
    ranges = np.asarray(msg.ranges, dtype=np.float32)
    min_m  = max(0.01, float(msg.range_min))
    max_m  = max(min_m + 0.01, float(msg.range_max))
    min_cm = int(_clamp(round(min_m * 100), 1, 65534))
    max_cm = int(_clamp(round(max_m * 100), min_cm + 1, 65534))
    empty  = min(max_cm + 1, 65534)   # kein Hindernis in diesem Sektor

    bins: np.ndarray = np.full(LIDAR_BIN_COUNT, empty, dtype=np.uint16)

    if ranges.size > 0:
        step = float(msg.angle_step)
        if abs(step) > 1e-12:
            angles = float(msg.angle_min) + np.arange(ranges.size, dtype=np.float32) * step
        else:
            angles = np.linspace(float(msg.angle_min), float(msg.angle_max),
                                 ranges.size, dtype=np.float32)

        for ang_rad, dist_m in zip(angles, ranges):
            ang_rad, dist_m = float(ang_rad), float(dist_m)
            if not math.isfinite(dist_m) or dist_m < min_m or dist_m > max_m:
                continue
            # Gazebo: positiv = gegen Uhrzeigersinn → umrechnen in MAVLink FRD
            cw_deg = -math.degrees(ang_rad)
            while cw_deg < -180.0: cw_deg += 360.0
            while cw_deg >= 180.0: cw_deg -= 360.0
            idx = int(math.floor((cw_deg - LIDAR_ANGLE_OFFSET_DEG) / LIDAR_INCREMENT_DEG))
            idx = max(0, min(LIDAR_BIN_COUNT - 1, idx))
            d_cm = int(_clamp(round(dist_m * 100), min_cm, max_cm))
            bins[idx] = min(int(bins[idx]), d_cm)

    dist_list = bins.tolist()

    now = time.monotonic()
    with _state.lock:
        mav       = _state.mav
        mav_ready = _state.mav_ready
        last_send = _state.last_lidar_send_time

    # Rate-Limiting: OBSTACLE_DISTANCE nicht schneller als ~10 Hz senden
    if mav_ready and mav is not None and (now - last_send) >= LIDAR_SEND_INTERVAL_S:
        mav.mav.obstacle_distance_send(
            int(time.time() * 1_000_000),
            mavutil.mavlink.MAV_DISTANCE_SENSOR_LASER,
            dist_list,
            int(round(LIDAR_INCREMENT_DEG)),
            min_cm, max_cm,
            float(LIDAR_INCREMENT_DEG),
            float(LIDAR_ANGLE_OFFSET_DEG),
            mavutil.mavlink.MAV_FRAME_BODY_FRD,
        )
        with _state.lock:
            _state.last_lidar_send_time = now

    # Visualisierung vorbereiten
    view = _draw_lidar(dist_list, min_m, max_m)
    with _state.lock:
        _state.latest_lidar_view = view
        _state.lidar_count += 1


def _draw_lidar(
    bins: list[int],
    min_m: float,
    max_m: float,
) -> np.ndarray:
    S = 650
    view   = np.zeros((S, S, 3), dtype=np.uint8)
    cx, cy = S // 2, S // 2
    radius = int(S * 0.44)
    disp_max = min(max_m, 30.0)

    for frac in (0.25, 0.5, 0.75, 1.0):
        cv2.circle(view, (cx, cy), int(radius * frac), (70, 70, 70), 1)
    cv2.line(view, (cx - radius, cy), (cx + radius, cy), (70, 70, 70), 1)
    cv2.line(view, (cx, cy - radius), (cx, cy + radius), (70, 70, 70), 1)
    cv2.circle(view, (cx, cy), 7, (0, 255, 255), -1)
    cv2.arrowedLine(view, (cx, cy), (cx + 45, cy), (0, 255, 255), 2, tipLength=0.25)

    max_cm_val = int(max_m * 100)
    valid_count = 0
    nearest_m: Optional[float] = None

    for i, d_cm in enumerate(bins):
        if d_cm > max_cm_val:
            continue
        d_m = d_cm / 100.0
        if d_m < min_m or d_m > disp_max:
            continue
        cw_deg     = LIDAR_ANGLE_OFFSET_DEG + (i + 0.5) * LIDAR_INCREMENT_DEG
        gz_rad     = math.radians(-cw_deg)
        x = d_m * math.cos(gz_rad)
        y = d_m * math.sin(gz_rad)
        scale = radius / disp_max
        px = int(cx + x * scale)
        py = int(cy - y * scale)
        cv2.circle(view, (px, py), 3, (0, 255, 0), -1)
        valid_count += 1
        nearest_m = d_m if nearest_m is None else min(nearest_m, d_m)

    label = f"Sektoren: {valid_count}"
    if nearest_m is not None:
        label += f"  Naechstes: {nearest_m:.2f} m"
    cv2.putText(view, label, (15, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2, cv2.LINE_AA)
    return view


# ─── MAVLink Empfänger ───────────────────────────────────────────────────────

def _mavlink_reader(conn: mavutil.mavfile) -> None:
    """Dauerschleife: liest GLOBAL_POSITION_INT und ATTITUDE für Bridge."""
    while _state.running:
        try:
            msg = conn.recv_match(blocking=True, timeout=1.0)
        except Exception:
            break
        if msg is None:
            continue
        t = msg.get_type()
        with _state.lock:
            if t == "GLOBAL_POSITION_INT":
                _state.relative_alt_m = max(0.05, float(msg.relative_alt) / 1000.0)
            elif t == "ATTITUDE":
                _state.rollspeed  = float(msg.rollspeed)
                _state.pitchspeed = float(msg.pitchspeed)
                _state.yawspeed   = float(msg.yawspeed)


# ─── Einstiegspunkt ──────────────────────────────────────────────────────────

def main() -> None:
    if not _GZ_AVAILABLE:
        print(
            f"FEHLER: gz.transport13 / gz.msgs10 nicht verfügbar:\n  {_gz_import_error}\n"
            "Bitte installieren: pip install gz-transport13 gz-msgs10",
            file=sys.stderr,
        )
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Gazebo → ArduPilot MAVLink Sensor-Bridge",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--mavlink",       default=DEFAULT_MAVLINK,
                        help=f"MAVLink-Verbindung (Standard: {DEFAULT_MAVLINK})\n"
                             "  SITL:     udpin:0.0.0.0:14550\n"
                             "  Hardware: /dev/ttyACM0:115200  oder  tcp:192.168.1.10:5760")
    parser.add_argument("--camera-topic",  default=DEFAULT_CAMERA_TOPIC)
    parser.add_argument("--lidar-topic",   default=DEFAULT_LIDAR_TOPIC)
    parser.add_argument("--no-display",    action="store_true",
                        help="Keine OpenCV-Fenster (headless / vom GCS aus starten)")
    args = parser.parse_args()

    # Sauberes Beenden mit Ctrl+C / SIGTERM
    def _sighandler(*_):
        _state.running = False
    signal.signal(signal.SIGINT,  _sighandler)
    signal.signal(signal.SIGTERM, _sighandler)

    print(f"[Bridge] Verbinde MAVLink: {args.mavlink}")
    try:
        conn = mavutil.mavlink_connection(
            args.mavlink,
            source_system=200,
            source_component=mavutil.mavlink.MAV_COMP_ID_VISUAL_INERTIAL_ODOMETRY,
        )
    except Exception as exc:
        print(f"[Bridge] FEHLER bei MAVLink-Verbindung: {exc}", file=sys.stderr)
        sys.exit(1)

    print("[Bridge] Warte auf ArduPilot-Heartbeat ...")
    try:
        conn.wait_heartbeat(timeout=30)
    except Exception as exc:
        print(f"[Bridge] Kein Heartbeat empfangen: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"[Bridge] ArduPilot gefunden: system={conn.target_system}, "
        f"component={conn.target_component}"
    )
    with _state.lock:
        _state.mav       = conn
        _state.mav_ready = True

    reader = threading.Thread(target=_mavlink_reader, args=(conn,), daemon=True)
    reader.start()

    node = GzNode()
    if not node.subscribe(GzImage, args.camera_topic, _camera_callback):
        print(f"[Bridge] FEHLER: Kamera-Topic nicht verfügbar: {args.camera_topic}",
              file=sys.stderr)
        sys.exit(1)
    if not node.subscribe(GzLaserScan, args.lidar_topic, _lidar_callback):
        print(f"[Bridge] FEHLER: LiDAR-Topic nicht verfügbar: {args.lidar_topic}",
              file=sys.stderr)
        sys.exit(1)

    print(f"[Bridge] Kamera:  {args.camera_topic}")
    print(f"[Bridge] LiDAR:   {args.lidar_topic}")
    print("[Bridge] Sende: OPTICAL_FLOW_RAD | DISTANCE_SENSOR | OBSTACLE_DISTANCE")
    if not args.no_display:
        print("[Bridge] Beenden mit Q, ESC oder Ctrl+C")
    else:
        print("[Bridge] Headless-Modus aktiv — kein Fenster. Beenden mit Ctrl+C / SIGTERM")

    try:
        while _state.running:
            if not args.no_display:
                with _state.lock:
                    fv = None if _state.latest_flow_view is None else _state.latest_flow_view.copy()
                    lv = None if _state.latest_lidar_view is None else _state.latest_lidar_view.copy()
                if fv is not None:
                    cv2.imshow("Gazebo → MAVLink Optical Flow", fv)
                if lv is not None:
                    cv2.imshow("Gazebo → MAVLink LiDAR", lv)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
            time.sleep(0.005)
    finally:
        _state.running = False
        if not args.no_display:
            cv2.destroyAllWindows()
        print("[Bridge] Beendet.")


if __name__ == "__main__":
    main()
