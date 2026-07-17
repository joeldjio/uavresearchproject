#!/usr/bin/env python3
"""Gazebo LiDAR polar-plot viewer (OpenCV window).

Subscribes to a LaserScan topic via gz.transport13 and renders a live 2-D
polar point-cloud.  Close the window with Q or ESC.

Usage:
    python3 lidar_viewer.py [--topic TOPIC] [--range RANGE_M]
"""
import argparse
import math
import threading
import time

import cv2
import numpy as np

from gz.msgs10.laserscan_pb2 import LaserScan
from gz.transport13 import Node

_lock = threading.Lock()
_latest_angles = None
_latest_ranges = None
_message_count = 0

# Set by main() from CLI args — used as module-level constants like the
# working version the user tested locally.
WINDOW_SIZE     = 700
DISPLAY_RANGE_M = 30.0


def lidar_callback(msg: LaserScan) -> None:
    global _latest_angles, _latest_ranges, _message_count

    ranges = np.asarray(msg.ranges, dtype=np.float32)
    if ranges.size == 0:
        return

    angle_min  = float(msg.angle_min)
    angle_max  = float(msg.angle_max)
    angle_step = float(msg.angle_step)

    if abs(angle_step) > 1e-12:
        angles = angle_min + np.arange(ranges.size, dtype=np.float32) * angle_step
    else:
        angles = np.linspace(angle_min, angle_max, ranges.size, dtype=np.float32)

    range_min = float(msg.range_min)
    range_max = float(msg.range_max)
    valid = (
        np.isfinite(ranges)
        & (ranges >= range_min)
        & (ranges <= range_max)
    )

    with _lock:
        _latest_angles = angles[valid]
        _latest_ranges = ranges[valid]
        _message_count += 1


def draw_grid(canvas: np.ndarray, center: tuple, radius: int) -> None:
    cx, cy = center
    for fraction in (0.25, 0.5, 0.75, 1.0):
        r = int(radius * fraction)
        cv2.circle(canvas, center, r, (70, 70, 70), 1)
        label = f"{DISPLAY_RANGE_M * fraction:.0f} m"
        cv2.putText(canvas, label, (cx + 8, cy - r + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
    cv2.line(canvas, (cx - radius, cy), (cx + radius, cy), (70, 70, 70), 1)
    cv2.line(canvas, (cx, cy - radius), (cx, cy + radius), (70, 70, 70), 1)


def main() -> None:
    global DISPLAY_RANGE_M

    parser = argparse.ArgumentParser(description="Gazebo LiDAR viewer")
    parser.add_argument("--topic", default="/lidar/scan")
    parser.add_argument("--range", type=float, default=30.0, dest="display_range")
    args = parser.parse_args()

    topic           = args.topic
    DISPLAY_RANGE_M = args.display_range  # update module-level constant

    node = Node()
    if not node.subscribe(LaserScan, topic, lidar_callback):
        raise RuntimeError(f"Topic konnte nicht abonniert werden: {topic}")

    print(f"Empfange Gazebo-LiDAR: {topic}")
    print("Beenden mit Q oder ESC")

    last_count     = 0
    last_rate_time = time.monotonic()
    hz             = 0.0

    while True:
        with _lock:
            angles = None if _latest_angles is None else _latest_angles.copy()
            ranges = None if _latest_ranges is None else _latest_ranges.copy()
            count  = _message_count

        now = time.monotonic()
        if now - last_rate_time >= 1.0:
            hz         = (count - last_count) / (now - last_rate_time)
            last_count = count
            last_rate_time = now

        canvas = np.zeros((WINDOW_SIZE, WINDOW_SIZE, 3), dtype=np.uint8)
        center = (WINDOW_SIZE // 2, WINDOW_SIZE // 2)
        radius = int(WINDOW_SIZE * 0.44)
        draw_grid(canvas, center, radius)

        # Drone marker at centre, arrow pointing forward (+X)
        cv2.circle(canvas, center, 7, (0, 255, 255), -1)
        cv2.arrowedLine(canvas, center, (center[0] + 45, center[1]),
                        (0, 255, 255), 2, tipLength=0.25)

        if angles is None or ranges is None:
            cv2.putText(canvas, "Waiting for signal ...",
                        (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (255, 255, 255), 2, cv2.LINE_AA)
        else:
            within_display = ranges <= DISPLAY_RANGE_M
            shown_angles   = angles[within_display]
            shown_ranges   = ranges[within_display]
            scale          = radius / DISPLAY_RANGE_M

            # Gazebo convention: +X forward, +Y left
            x  = shown_ranges * np.cos(shown_angles)
            y  = shown_ranges * np.sin(shown_angles)
            px = center[0] + (x * scale).astype(np.int32)
            py = center[1] - (y * scale).astype(np.int32)

            for point_x, point_y in zip(px, py):
                if 0 <= point_x < WINDOW_SIZE and 0 <= point_y < WINDOW_SIZE:
                    cv2.circle(canvas, (int(point_x), int(point_y)), 2, (0, 255, 0), -1)

            if shown_ranges.size > 0:
                ni     = int(np.argmin(shown_ranges))
                status = (f"{hz:.1f} Hz | Punkte: {shown_ranges.size} | "
                          f"Naechstes Hindernis: {shown_ranges[ni]:.2f} m "
                          f"bei {math.degrees(float(shown_angles[ni])):+.1f} Grad")
            else:
                status = (f"{hz:.1f} Hz | Kein Hindernis innerhalb "
                          f"{DISPLAY_RANGE_M:.0f} m")
            cv2.putText(canvas, status, (15, 28), cv2.FONT_HERSHEY_SIMPLEX,
                        0.52, (255, 255, 255), 1, cv2.LINE_AA)

        cv2.imshow("Gazebo LiDAR", canvas)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break
        time.sleep(0.001)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
