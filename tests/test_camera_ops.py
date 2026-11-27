"""Fleet ops: offline alerting, activity persistence, evidence clips, adaptive FPS."""

import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from app.config import config
from app.db.models import CameraActivityLog, IncidentAlert
from app.db.sqlite_db import SessionLocal
from app.services.camera_manager import CameraWorker, camera_manager
from app.services.camera_ops_service import camera_ops_service


def _worker(camera_id="cam_entrance"):
    camera_manager.start_monitoring()
    return camera_manager.workers[camera_id]


def test_monitoring_is_dashboard_controlled(client, admin_headers):
    status = client.get("/api/stream/monitoring")
    assert status.status_code == 200
    assert status.json()["running"] is False
    assert status.json()["worker_count"] == 0

    started = client.post("/api/stream/monitoring/start", headers=admin_headers)
    assert started.status_code == 200
    assert started.json()["running"] is True
    assert started.json()["worker_count"] == len(camera_manager.list_cameras())

    stopped = client.post("/api/stream/monitoring/stop", headers=admin_headers)
    assert stopped.status_code == 200
    assert stopped.json()["running"] is False
    assert stopped.json()["worker_count"] == 0


def test_offline_alert_emitted_and_resolved(client):
    worker = _worker()
    worker._offline_since = 1.0
    worker._last_frame_time = 0.0
    camera_ops_service._last_offline_alert.pop(worker.camera_id, None)

    camera_ops_service.sweep_once()

    db = SessionLocal()
    try:
        alerts = (
            db.query(IncidentAlert)
            .filter(IncidentAlert.alert_type == "CAMERA_OFFLINE", IncidentAlert.camera_id == worker.camera_id)
            .all()
        )
        assert len(alerts) >= 1, "offline camera should raise a CAMERA_OFFLINE alert"
        assert all(not a.is_resolved for a in alerts)
    finally:
        db.close()

    camera_ops_service.sweep_once()
    db = SessionLocal()
    try:
        count = (
            db.query(IncidentAlert)
            .filter(
                IncidentAlert.alert_type == "CAMERA_OFFLINE",
                IncidentAlert.camera_id == worker.camera_id,
                IncidentAlert.is_resolved == False,
            )
            .count()
        )
        assert count == len(alerts), "dedupe must not raise duplicate unresolved alerts"
    finally:
        db.close()

    worker._offline_since = None
    worker._last_frame_time = time.time()
    camera_ops_service.sweep_once()

    db = SessionLocal()
    try:
        pending = (
            db.query(IncidentAlert)
            .filter(
                IncidentAlert.alert_type == "CAMERA_OFFLINE",
                IncidentAlert.camera_id == worker.camera_id,
                IncidentAlert.is_resolved == False,
            )
            .count()
        )
        assert pending == 0, "recovered camera should auto-resolve its offline alerts"
    finally:
        db.close()


def test_offline_since_sticky_across_retries():
    """Re-publishing offline during a reconnect loop must not reset the clock."""
    worker = _worker()
    worker._offline_since = None
    worker._publish_offline("first")
    first = worker._offline_since
    time.sleep(0.02)
    worker._publish_offline("retry")
    assert worker._offline_since == first
    assert worker.is_offline(time.time()) is False  # grace not yet elapsed


def test_camera_status_reports_startup_and_redacted_connection_error():
    source = "rtsp://operator:secret@example.invalid/live"
    worker = CameraWorker("cam_test", {"name": "Test camera", "source": source})

    assert worker.get_latest().offline is True
    assert worker.get_status()["last_error"] == "Waiting for the first frame"

    worker._publish_offline(f"unable to open source {source!r}")
    status = worker.get_status()

    assert status["last_error"] == "unable to open source 'rtsp://operator:***@example.invalid/live'"
    assert "secret" not in status["last_error"]

    worker._publish_frame(np.zeros((24, 24, 3), dtype=np.uint8), time.time(), force=True)
    assert worker.get_latest().offline is False
    assert worker.get_status()["last_error"] is None
    assert worker.get_status()["offline_since"] is None


def test_activity_minutes_merge_and_persist(client):
    worker = _worker()
    worker._last_history_ts = 0.0
    worker._motion_level = 0.5
    worker._scene_state = "CROWDED"
    worker._people_count = 4
    now = time.time()

    worker._record_history(now, analyzed=True)
    worker._record_history(now + 1.0, analyzed=True)
    entries = worker.drain_activity()
    assert len(entries) == 1
    camera_ops_service.save_activity(entries)

    worker._motion_level = 0.3
    worker._scene_state = "ACTIVE"
    worker._people_count = 2
    worker._record_history(now + 2.0, analyzed=False)
    worker._record_history(now + 3.0, analyzed=True)
    entries2 = worker.drain_activity()
    assert len(entries2) == 1
    camera_ops_service.save_activity(entries2)

    db = SessionLocal()
    try:
        rows = db.query(CameraActivityLog).filter(CameraActivityLog.camera_id == worker.camera_id).all()
        assert len(rows) == 1, "two partial minutes must upsert into a single bucket row"
        row = rows[0]
        assert row.samples == 4
        assert row.peak_motion == 50.0
        assert row.crowd_seconds == 2
        assert row.people_seen == 4
        assert row.analyzed_count == 3
    finally:
        db.close()


def test_camera_activity_endpoint(client):
    worker = _worker()
    worker._last_history_ts = 0.0
    worker._motion_level = 0.4
    worker._scene_state = "BUSY"
    worker._people_count = 3
    worker._record_history(time.time(), analyzed=True)
    camera_ops_service.save_activity(worker.drain_activity())

    ok = client.get(f"/api/analytics/camera-activity?camera_id={worker.camera_id}&hours=24")
    assert ok.status_code == 200
    body = ok.json()
    assert body["camera_id"] == worker.camera_id
    assert body["granularity"] == "minute"
    assert len(body["data"]) >= 1
    assert body["data"][0]["people_seen"] == 3

    bad_hours = client.get(f"/api/analytics/camera-activity?camera_id={worker.camera_id}&hours=0")
    assert bad_hours.status_code == 400
    missing = client.get("/api/analytics/camera-activity?camera_id=does_not_exist&hours=24")
    assert missing.status_code == 404
    empty = client.get("/api/analytics/camera-activity?camera_id=cam_workspace&hours=24")
    assert empty.status_code == 200 and empty.json()["data"] == []


def test_clips_save_list_serve_and_guard(client, tmp_path):
    worker = _worker()
    jpeg = cv2.imencode(".jpg", np.zeros((120, 160, 3), np.uint8))[1].tobytes()
    worker._clip_buf = deque([(time.time() - 1, jpeg) for _ in range(10)])
    saved = worker._save_clip("feed-lost")

    listing = client.get(f"/api/stream/clips?camera_id={worker.camera_id}")
    assert listing.status_code == 200
    clips = listing.json()["clips"]

    if saved is not None:
        assert saved and Path(saved).exists()
        name = Path(saved).name
        assert any(c["filename"] == name for c in clips)
        served = client.get(f"/api/stream/clips/{name}")
        assert served.status_code == 200
        assert served.headers["content-type"].startswith("video/mp4")

    bogus = client.get("/api/stream/clips/..%2Fsurveillance.db")
    assert bogus.status_code in (400, 404)
    nonclip = client.get("/api/stream/clips/notes.txt")
    assert nonclip.status_code in (400, 404)


def test_adaptive_fps_throttles_and_recovers():
    worker = _worker()
    worker._defer_stamps = deque([time.time() - 10, time.time() - 9, time.time() - 8, time.time() - 5])
    worker._adaptive_fps = 25
    worker._update_adaptive_fps(time.time())
    assert worker._adaptive_fps == max(config.CAMERA_MIN_FPS, 25 // 2)

    worker._defer_stamps = deque([time.time() - 60])
    worker._update_adaptive_fps(time.time())
    assert worker._adaptive_fps == 25


def test_fleet_health_serialized(client):
    cams = client.get("/api/stream/cameras").json()["cameras"]
    for cam in cams:
        for key in ("analysis_latency_ms", "adaptive_fps", "scheduler_deferred", "offline_since", "clip_buffered_frames"):
            assert key in cam


def test_metrics_endpoint(client):
    res = client.get("/api/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    for line in ("aegis_cameras_total", "aegis_cameras_online", "aegis_analysis_budget_available", "aegis_uptime_seconds"):
        assert any(l.startswith(line) for l in res.text.splitlines())