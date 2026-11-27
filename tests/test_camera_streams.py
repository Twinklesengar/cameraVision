"""Multi-camera fleet management: CRUD, auth gating, validation, redaction, lifecycle."""

ADD = {
    "camera_id": "cam_site_c",
    "name": "Warehouse Bay C",
    "source": "9999",  # invalid index -> worker starts offline, no real capture in CI
    "type": "productivity",
    "resolution": "640x480",
    "fps_limit": 10,
}


def _find(cameras, camera_id):
    return next((c for c in cameras if c["camera_id"] == camera_id), None)


def test_camera_list_scene_fields(client):
    res = client.get("/api/stream/cameras")
    assert res.status_code == 200
    cams = res.json()["cameras"]
    assert len(cams) == 2
    for cam in cams:
        assert "scene_state" in cam
        assert "motion_score" in cam
        assert "active" in cam
        assert "online" in cam


def test_add_camera_requires_admin(client):
    assert client.post("/api/stream/cameras", json=ADD).status_code in (401, 403)
    assert client.delete("/api/stream/cameras/cam_site_c").status_code in (401, 403)


def test_add_and_read_camera(client, admin_headers):
    res = client.post("/api/stream/cameras", json=ADD, headers=admin_headers)
    assert res.status_code == 201
    cam = res.json()["camera"]
    assert cam["camera_id"] == ADD["camera_id"]
    assert cam["type"] == "productivity"
    assert cam["active"] is True

    listed = client.get("/api/stream/cameras").json()["cameras"]
    assert _find(listed, "cam_site_c") is not None

    detail = client.get("/api/stream/cameras/cam_site_c").json()["camera"]
    assert detail["name"] == "Warehouse Bay C"


def test_add_camera_validation(client, admin_headers):
    bad_id = dict(ADD, camera_id="bad id!")  # invalid characters
    assert client.post("/api/stream/cameras", json=bad_id, headers=admin_headers).status_code == 422

    bad_scheme = dict(ADD, camera_id="cam_dup_validation", source="gopher://127.0.0.1")
    res = client.post("/api/stream/cameras", json=bad_scheme, headers=admin_headers)
    assert res.status_code == 400

    bad_type = dict(ADD, camera_id="cam_type_validation", type="spy")
    assert client.post("/api/stream/cameras", json=bad_type, headers=admin_headers).status_code == 400

    bad_res = dict(ADD, camera_id="cam_res_validation", resolution="bogus")
    assert client.post("/api/stream/cameras", json=bad_res, headers=admin_headers).status_code == 400


def test_add_duplicate_conflict(client, admin_headers):
    first = client.post("/api/stream/cameras", json=ADD, headers=admin_headers)
    assert first.status_code == 201
    dup = client.post("/api/stream/cameras", json=dict(ADD, name="Dupe"), headers=admin_headers)
    assert dup.status_code == 409


def test_update_and_restart(client, admin_headers):
    client.post("/api/stream/cameras", json=ADD, headers=admin_headers)

    upd = client.patch(
        "/api/stream/cameras/cam_site_c",
        json={"name": "Warehouse Bay D", "fps_limit": 5},
        headers=admin_headers,
    )
    assert upd.status_code == 200
    assert upd.json()["camera"]["name"] == "Warehouse Bay D"
    assert upd.json()["camera"]["fps_limit"] == 5

    res = client.post("/api/stream/cameras/cam_site_c/restart", headers=admin_headers)
    assert res.status_code == 409

    started = client.post("/api/stream/monitoring/start", headers=admin_headers)
    assert started.status_code == 200

    res = client.post("/api/stream/cameras/cam_site_c/restart", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["camera"]["camera_id"] == "cam_site_c"

    unknown = client.post("/api/stream/cameras/cam_nope/restart", headers=admin_headers)
    assert unknown.status_code == 404


def test_disable_and_reenable(client, admin_headers):
    client.post("/api/stream/cameras", json=ADD, headers=admin_headers)
    off = client.patch(
        "/api/stream/cameras/cam_site_c", json={"active": False}, headers=admin_headers
    )
    assert off.status_code == 200
    assert off.json()["camera"]["active"] is False

    listed = client.get("/api/stream/cameras").json()["cameras"]
    cam = _find(listed, "cam_site_c")
    assert cam is not None and cam["active"] is False

    on = client.patch(
        "/api/stream/cameras/cam_site_c", json={"active": True}, headers=admin_headers
    )
    assert on.json()["camera"]["active"] is True


def test_remove_camera(client, admin_headers):
    client.post("/api/stream/cameras", json=ADD, headers=admin_headers)
    res = client.delete("/api/stream/cameras/cam_site_c", headers=admin_headers)
    assert res.status_code == 200
    assert _find(client.get("/api/stream/cameras").json()["cameras"], "cam_site_c") is None

    gone = client.delete("/api/stream/cameras/cam_never_existed", headers=admin_headers)
    assert gone.status_code == 404


def test_baseline_camera_remove_soft_disables(client, admin_headers):
    """Removing a baseline (env-defined) camera must not resurrect it on the next
    list call — it becomes a durable disabled override."""
    res = client.delete("/api/stream/cameras/cam_entrance", headers=admin_headers)
    assert res.status_code == 200
    cam = _find(client.get("/api/stream/cameras").json()["cameras"], "cam_entrance")
    assert cam is not None and cam["active"] is False

    on = client.patch("/api/stream/cameras/cam_entrance", json={"active": True}, headers=admin_headers)
    assert on.status_code == 200 and on.json()["camera"]["active"] is True


def test_source_credentials_redacted(client, admin_headers):
    cam = dict(
        ADD,
        camera_id="cam_rtsp",
        source="rtsp://admin:secret@192.168.10.20:554/Streaming/Channel/1",
    )
    client.post("/api/stream/cameras", json=cam, headers=admin_headers)
    listed = client.get("/api/stream/cameras").json()["cameras"]
    source = _find(listed, "cam_rtsp")["source"]
    assert "secret" not in source
    assert "***" in source
    assert source.startswith("rtsp://admin:***@")


def test_dashboard_occupancy_still_stable(client):
    res = client.get("/api/analytics/occupancy")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_camera_history_endpoint(client):
    res = client.get("/api/stream/cameras/cam_entrance/history?limit=60")
    assert res.status_code == 200
    body = res.json()
    assert body["camera_id"] == "cam_entrance"
    assert isinstance(body["history"], list)


def test_fleet_summary_shape(client):
    res = client.get("/api/stream/fleet/summary")
    assert res.status_code == 200
    body = res.json()
    for key in ("total", "online", "active_cameras", "busy", "analysis_budget_available", "analysis_queue"):
        assert key in body
    assert body["total"] >= 2


def test_camera_list_includes_history(client):
    cams = client.get("/api/stream/cameras").json()["cameras"]
    for cam in cams:
        assert isinstance(cam["history"], list)
        assert "scene_state" in cam