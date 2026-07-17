#!/usr/bin/env python3
"""Gazebo optical-flow camera viewer (OpenCV window).

Subscribes to /flow_camera/image via gz.transport13, renders the live camera
image and overlays dense Farneback optical-flow vectors computed frame-to-frame.

Close the window with Q or ESC.

Usage:
    python3 flow_viewer.py [--topic TOPIC]
"""
import argparse
import sys
import threading
import time

import cv2
import numpy as np

from gz.msgs10.image_pb2 import Image
from gz.transport13 import Node

_lock = threading.Lock()
_latest_frame: "np.ndarray | None" = None
_message_count = 0


def image_callback(msg: Image) -> None:
    global _latest_frame, _message_count

    width  = int(msg.width)
    height = int(msg.height)

    if width <= 0 or height <= 0 or not msg.data:
        return

    raw = np.frombuffer(msg.data, dtype=np.uint8)

    rgb_size  = width * height * 3
    rgba_size = width * height * 4
    gray_size = width * height

    try:
        if raw.size >= rgba_size:
            rgba  = raw[:rgba_size].reshape((height, width, 4))
            frame = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
        elif raw.size >= rgb_size:
            rgb   = raw[:rgb_size].reshape((height, width, 3))
            frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        elif raw.size >= gray_size:
            gray  = raw[:gray_size].reshape((height, width))
            frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        else:
            print(
                f"Unbekannte Bildgröße: {raw.size} Bytes "
                f"für {width}x{height}",
                file=sys.stderr,
            )
            return
    except ValueError as exc:
        print(f"Bild konnte nicht konvertiert werden: {exc}", file=sys.stderr)
        return

    with _lock:
        _latest_frame  = frame.copy()
        _message_count += 1


def draw_flow_vectors(
    frame: np.ndarray,
    flow: np.ndarray,
    step: int = 20,
    scale: float = 4.0,
) -> np.ndarray:
    output = frame.copy()
    height, width = frame.shape[:2]
    for y in range(step // 2, height, step):
        for x in range(step // 2, width, step):
            dx, dy = flow[y, x]
            end_x = int(round(x + dx * scale))
            end_y = int(round(y + dy * scale))
            cv2.arrowedLine(output, (x, y), (end_x, end_y),
                            (0, 255, 0), 1, tipLength=0.3)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Gazebo Flow-Camera viewer")
    parser.add_argument("--topic", default="/flow_camera/image")
    args = parser.parse_args()

    topic = args.topic

    node = Node()
    if not node.subscribe(Image, topic, image_callback):
        raise RuntimeError(f"Topic konnte nicht abonniert werden: {topic}")

    print(f"Empfange Gazebo-Kamerastream: {topic}")
    print("Beenden mit Q oder ESC")

    previous_gray: "np.ndarray | None" = None
    previous_frame_time: "float | None" = None

    last_count     = 0
    last_rate_time = time.monotonic()
    camera_fps     = 0.0

    while True:
        with _lock:
            frame = None if _latest_frame is None else _latest_frame.copy()
            count = _message_count

        now = time.monotonic()
        if now - last_rate_time >= 1.0:
            camera_fps     = (count - last_count) / (now - last_rate_time)
            last_count     = count
            last_rate_time = now

        if frame is None:
            waiting = np.zeros((240, 320, 3), dtype=np.uint8)
            cv2.putText(waiting, "Waiting for Strean ...",
                        (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow("Gazebo Optical Flow", waiting)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
            time.sleep(0.01)
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if previous_gray is None:
            previous_gray       = gray
            previous_frame_time = now
            display = frame.copy()
            cv2.putText(display, "Initialising Optical Flow ...",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 255), 2, cv2.LINE_AA)
        else:
            dt = (now - previous_frame_time) if previous_frame_time is not None else 0.0

            flow = cv2.calcOpticalFlowFarneback(
                previous_gray, gray, None,
                pyr_scale=0.5, levels=3, winsize=21,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
            )

            display = draw_flow_vectors(frame, flow)

            flow_x_px_frame = float(np.median(flow[..., 0]))
            flow_y_px_frame = float(np.median(flow[..., 1]))

            if dt > 0:
                flow_x_px_s = flow_x_px_frame / dt
                flow_y_px_s = flow_y_px_frame / dt
            else:
                flow_x_px_s = flow_y_px_s = 0.0

            median_magnitude = float(np.median(
                np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)))

            cv2.putText(display, f"Camera: {camera_fps:.1f} FPS",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.58,
                        (0, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(display,
                        f"Flow/frame: x={flow_x_px_frame:+.3f}  y={flow_y_px_frame:+.3f} px",
                        (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.52,
                        (0, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(display,
                        f"Flow/s:     x={flow_x_px_s:+.1f}  y={flow_y_px_s:+.1f} px/s",
                        (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.52,
                        (0, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(display,
                        f"Median magnitude: {median_magnitude:.3f} px/frame",
                        (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.52,
                        (0, 255, 255), 2, cv2.LINE_AA)

            previous_gray       = gray
            previous_frame_time = now

        cv2.imshow("Gazebo Optical Flow", display)
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            break
        time.sleep(0.001)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
