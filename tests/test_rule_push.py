import json
import threading
import http.server

from app.config import config
from app.services.rule_engine import rule_engine
from app.services.notify import push_alert


def _seed_productivity(db_session, person_id, count, status="PHONE_DISTRACTED"):
    from app.db.models import ProductivityLog

    rows = [
        ProductivityLog(person_id=person_id, status=status, duration_seconds=60, camera_id="cam_workspace")
        for _ in range(count)
    ]
    db_session.add_all(rows)
    db_session.commit()


def test_rule_engine_phone_overuse_sweep(client):
    from app.db.sqlite_db import SessionLocal
    from app.db.models import IncidentAlert

    db = SessionLocal()
    _seed_productivity(db, "EMP2", config.PHONE_OVERUSE_COUNT + 1)
    db.close()
    rule_engine._last_emitted.clear()

    emitted = rule_engine.sweep()
    assert emitted >= 1

    db = SessionLocal()
    matches = (
        db.query(IncidentAlert)
        .filter(IncidentAlert.alert_type == "PHONE_OVERUSE", IncidentAlert.person_id == "EMP2")
        .all()
    )
    db.close()
    assert len(matches) == 1

    again = rule_engine.sweep()
    assert again == 0


def test_rule_engine_unknown_gate_escalation(client):
    from app.db.sqlite_db import SessionLocal
    from app.db.models import IncidentAlert, AttendanceLog

    db = SessionLocal()
    for _ in range(config.UNKNOWN_GATE_COUNT):
        db.add(AttendanceLog(person_id=None, name="UNKNOWN", event_type="ENTRY", camera_id="cam_entrance"))
    db.commit()
    db.close()
    rule_engine._last_emitted.clear()

    emitted = rule_engine.sweep()
    assert emitted >= 1

    db = SessionLocal()
    match = (
        db.query(IncidentAlert)
        .filter(IncidentAlert.alert_type == "UNKNOWN_REPEATED", IncidentAlert.severity == "CRITICAL")
        .first()
    )
    db.close()
    assert match is not None


def test_timeseries(client):
    from app.db.sqlite_db import SessionLocal
    from app.db.models import AttendanceLog

    db = SessionLocal()
    db.add_all([
        AttendanceLog(person_id="T1", name="T1", event_type="ENTRY", camera_id="cam_entrance"),
        AttendanceLog(person_id="T2", name="T2", event_type="EXIT", camera_id="cam_entrance"),
    ])
    db.commit()
    db.close()

    res = client.get("/api/analytics/timeseries", params={"metric": "attendance", "hours": 24})
    assert res.status_code == 200
    body = res.json()
    assert body["metric"] == "attendance"
    assert len(body["data"]) >= 1
    last = body["data"][-1]
    assert last["count"] == 2
    assert last["by_label"]["ENTRY"] == 1
    assert last["by_label"]["EXIT"] == 1


def test_timeseries_invalid_metric(client):
    res = client.get("/api/analytics/timeseries", params={"metric": "nope"})
    assert res.status_code == 400


class _Handler(http.server.BaseHTTPRequestHandler):
    captured = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.captured.append(self.rfile.read(length))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_webhook_notify_gated_by_severity(client, monkeypatch):
    _Handler.captured.clear()
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()

    from app.config import config as cfg

    monkeypatch.setattr(cfg, "NOTIFY_WEBHOOK_URL", f"http://127.0.0.1:{port}/hook")
    monkeypatch.setattr(cfg, "NOTIFY_MIN_SEVERITY", "WARNING")

    push_alert({"severity": "INFO", "alert_type": "TEST", "description": "should be filtered"})
    push_alert({
        "severity": "CRITICAL",
        "alert_type": "THEFT_ATTEMPT",
        "description": "theft detected",
        "camera_id": "cam_workspace",
        "person_id": "UNKNOWN",
    })

    srv.shutdown()
    thread.join()

    assert len(_Handler.captured) == 1
    payload = json.loads(_Handler.captured[0])
    assert payload["alert_type"] == "THEFT_ATTEMPT"
    assert payload["person_id"] == "UNKNOWN"