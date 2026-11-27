"""Baseline API smoke tests for AegisVision v3."""


def test_root(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert '<title>AegisVision' in res.text


def test_dashboard_summary_shape(client):
    res = client.get("/api/analytics/dashboard")
    assert res.status_code == 200
    summary = res.json()["summary"]
    for key in (
        "total_personnel",
        "today_attendance",
        "unresolved_alerts",
        "total_assets",
        "theft_threats",
        "productive_sessions",
        "phone_distractions",
        "bunking_incidents",
        "health_warnings",
    ):
        assert key in summary


def test_analytics_endpoints_empty(client):
    assert client.get("/api/analytics/attendance").status_code == 200
    assert client.get("/api/analytics/productivity").status_code == 200
    assert client.get("/api/analytics/health").status_code == 200
    assert client.get("/api/analytics/assets").status_code == 200
    assert client.get("/api/personnel/").status_code == 200
    assert client.get("/api/personnel").status_code == 200


def test_personnel_list_returns_enrolled_people_without_trailing_slash(client):
    from app.db.models import Personnel
    from app.db.sqlite_db import SessionLocal

    db = SessionLocal()
    try:
        db.add(Personnel(person_id="EMP_API", name="API Test", role="Student", department="Test"))
        db.commit()
    finally:
        db.close()

    response = client.get("/api/personnel")
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["data"][0]["person_id"] == "EMP_API"


def test_alert_lifecycle(client, admin_headers):
    from app.services.alert_service import emit_alert

    alert = emit_alert(
        alert_type="UNKNOWN_FACE",
        severity="WARNING",
        description="Smoke test unknown face",
        camera_id="cam_entrance",
        person_id="UNKNOWN",
    )
    assert alert is not None and alert.id

    res = client.get("/api/alerts/")
    body = res.json()
    assert body["count"] >= 1
    assert any(a["alert_type"] == "UNKNOWN_FACE" for a in body["data"])

    resolve = client.post(f"/api/alerts/resolve/{alert.id}", headers=admin_headers)
    assert resolve.status_code == 200
    assert resolve.json()["is_resolved"] is True

    unauthorized = client.post(f"/api/alerts/resolve/{alert.id}")
    assert unauthorized.status_code == 401


def test_copilot_fallback_without_key(client):
    res = client.post("/api/copilot/query", json={"query": "who entered today?"})
    assert res.status_code == 200
    assert "response" in res.json()


def test_camera_status(client):
    res = client.get("/api/stream/cameras")
    assert res.status_code == 200
    cameras = res.json()["cameras"]
    assert len(cameras) == 2
    assert {c["camera_id"] for c in cameras} == {"cam_entrance", "cam_workspace"}


def test_asset_registration_lifecycle(client, admin_headers):
    res = client.post(
        "/api/assets/",
        json={
            "asset_name": "laptop-001",
            "owner_person_id": "EMP1",
            "bbox": [100, 100, 260, 180],
            "camera_id": "cam_workspace",
        },
        headers=admin_headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "NORMAL"

    listed = client.get("/api/assets/").json()
    assert listed["count"] == 1
    assert listed["data"][0]["asset_name"] == "laptop-001"

    deleted = client.delete("/api/assets/laptop-001", headers=admin_headers)
    assert deleted.status_code == 200
    assert client.get("/api/assets/").json()["count"] == 0


def test_occupancy_endpoint(client):
    res = client.get("/api/analytics/occupancy")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_auth_login_and_me(client):
    bad = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401

    ok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert ok.status_code == 200
    token = ok.json()["token"]
    assert ok.json()["role"] == "admin"

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"

    no_token = client.get("/api/auth/me")
    assert no_token.status_code == 401


def test_system_health_open(client):
    res = client.get("/api/system/health")
    assert res.status_code == 200
    body = res.json()
    assert "uptime_seconds" in body
    assert isinstance(body["cameras"], list)
    assert "personnel" in body["counts"]
    assert "vector_stats" in body


def test_system_admin_routes_gated(client):
    logs = client.get("/api/system/logs")
    assert logs.status_code == 401
    cfg = client.get("/api/system/config")
    assert cfg.status_code == 401