import os
import sys
import tempfile

# Hermetic runtime: point all data + camera streams into a temp sandbox BEFORE importing the app.
_TEST_ROOT = tempfile.mkdtemp(prefix="aegis-tests-")
os.environ["BASE_DIR"] = _TEST_ROOT
os.environ["CAMERA_STREAMS"] = (
    '{"cam_entrance": {"name": "Test Cam", "source": 9999, "type": "gate"},'
    ' "cam_workspace": {"name": "Test Workspace", "source": 9999, "type": "productivity"}}'
)
os.environ["SQLITE_URL"] = f"sqlite:///{_TEST_ROOT}/surveillance.db"
# Hermetic tests: keep the fast dlib pipeline (no ONNX model load / downloads).
os.environ["FACE_BACKEND"] = "legacy"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

import pytest
from fastapi.testclient import TestClient

from app.config import config
from main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_headers(client):
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200
    token = res.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clean_db(client):
    """Reset SQLite + Chroma/Vector state between tests for determinism."""
    from app.services.camera_manager import camera_manager

    camera_manager.stop_monitoring()
    yield
    camera_manager.stop_monitoring()
    from app.db.sqlite_db import SessionLocal, Base

    session = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
    finally:
        session.close()

    from app.db.vector_db import vector_db
    try:
        ids = vector_db.collection.get(include=[])["ids"]
        if ids:
            vector_db.collection.delete(ids=ids)
    except Exception:
        pass