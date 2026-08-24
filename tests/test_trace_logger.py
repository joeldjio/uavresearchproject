from __future__ import annotations

import json
from pathlib import Path

from skymeshx.core.trace_logger import TraceLogger, analyze_trace_bundle
from skymeshx.exceptions import SessionError


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_trace_logger_creates_bundle_and_writes_events(tmp_path):
    logger = TraceLogger(root=tmp_path / "trace_runs")

    session_path = Path(
        logger.start_session(
            "GZ X500 Test",
            {
                "px4": {"model": "gz_x500_gimbal", "world": "default"},
                "vehicles": [{"droneId": "drone1", "namespace": "px4_1", "videoPort": 5600}],
            },
        )
    )

    assert session_path.exists()
    assert (session_path / "manifest.json").exists()
    assert (session_path / "ui_events.jsonl").exists()
    assert (session_path / "mission_trace.jsonl").exists()
    assert (session_path / "ros2_topic_health.json").exists()
    assert (session_path / "video").is_dir()
    assert (session_path / "config" / "sim_config.json").exists()

    manifest = json.loads((session_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["scenario"] == "GZ_X500_Test"
    assert manifest["px4"]["model"] == "gz_x500_gimbal"
    assert manifest["vehicles"][0]["namespace"] == "px4_1"

    logger.log_ui_event("qml_action", {"button": "Start Trace"})
    logger.log_mission_event("mission_start", {"droneId": "drone1"})
    logger.log_wp_tracking(
        "drone1",
        12,
        -35.36352,
        149.16465,
        -35.36360,
        149.16470,
        9.4,
        "GLOBAL_RELATIVE_ALT",
        acceptance_radius_m=2.0,
    )
    logger.log_video_status("drone1", "waiting", 5600)

    stopped_path = Path(logger.stop_session())
    assert stopped_path == session_path
    assert logger.session_active is False

    ui_events = _read_jsonl(session_path / "ui_events.jsonl")
    mission_events = _read_jsonl(session_path / "mission_trace.jsonl")

    assert any(event["type"] == "qml_action" for event in ui_events)
    assert any(event["type"] == "video_status" for event in ui_events)
    assert any(event["type"] == "mission_start" for event in mission_events)
    wp_events = [event for event in mission_events if event["type"] == "wp_tracking"]
    assert wp_events[0]["data"]["distanceToWpM"] == 9.4
    assert wp_events[0]["data"]["acceptanceRadiusM"] == 2.0

    video_status = json.loads(
        (session_path / "video" / "drone1_stream_probe.json").read_text(encoding="utf-8")
    )
    assert video_status["status"] == "waiting"
    assert video_status["url"] == "udp://0.0.0.0:5600"


def test_ros2_health_is_rate_limited_but_snapshot_updates(tmp_path):
    now = [10.0]
    logger = TraceLogger(root=tmp_path / "trace_runs", monotonic=lambda: now[0])
    session_path = Path(logger.start_session("topic_health", {}))

    topic = "/px4_1/fmu/out/vehicle_odometry"
    logger.log_ros2_health(topic, 30.0, 0.02, "sensor_data")
    logger.log_ros2_health(topic, 29.0, 0.03, "sensor_data")
    now[0] += 1.1
    logger.log_ros2_health(topic, 28.5, 0.04, "sensor_data")
    logger.stop_session()

    health = json.loads((session_path / "ros2_topic_health.json").read_text(encoding="utf-8"))
    assert health[topic]["messageCount"] == 3
    assert health[topic]["estimatedHz"] == 28.5

    topic_events = [
        event
        for event in _read_jsonl(session_path / "ui_events.jsonl")
        if event["type"] == "topic_health"
    ]
    assert len(topic_events) == 2


def test_trace_logger_exports_markdown_summary(tmp_path):
    logger = TraceLogger(root=tmp_path / "trace_runs")
    session_path = Path(logger.start_session("summary", {}))
    logger.log_error("test", "boom")
    logger.log_ros2_health("/px4_1/fmu/out/vehicle_status", 5.0, 0.1, "default")
    logger.stop_session()

    summary_path = Path(logger.export_markdown())
    assert summary_path == session_path / "trace_summary.md"
    text = summary_path.read_text(encoding="utf-8")
    assert "# Trace Summary" in text
    assert "Errors: 1" in text
    assert "/px4_1/fmu/out/vehicle_status" in text

    summary = analyze_trace_bundle(session_path)
    assert summary["errorCount"] == 1
    assert summary["topicHealth"]["/px4_1/fmu/out/vehicle_status"]["seen"] is True


def test_trace_logger_blocks_nested_sessions(tmp_path):
    logger = TraceLogger(root=tmp_path / "trace_runs")
    logger.start_session("one", {})

    try:
        logger.start_session("two", {})
    except SessionError as exc:
        assert "already active" in str(exc)
    else:
        raise AssertionError("Expected nested trace session to be rejected")
    finally:
        logger.stop_session()
