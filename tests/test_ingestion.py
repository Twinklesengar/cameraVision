"""Plug-and-play ingestion: folder meta JSON + photo -> VectorDB + SQLite, per-photo vectors."""

import os
import json
import numpy as np

from app.db.sqlite_db import SessionLocal
from app.db.models import Personnel


def _fake_embeddings(rgb_image, known_face_locations=None):
    return [np.random.default_rng(0).normal(size=128)]


def _fake_locations(rgb_image):
    return [(10, 90, 90, 10)]


def _write_img(path):
    import cv2

    img = np.full((100, 100, 3), 200, dtype=np.uint8)
    cv2.imwrite(str(path), img)


def test_folder_registration_persists_multiple_photos(monkeypatch, tmp_path):
    from app.db.vector_db import vector_db
    from app.services.ingestion_service import ingestion_service

    monkeypatch.setattr("face_recognition.face_locations", _fake_locations)
    monkeypatch.setattr("face_recognition.face_encodings", _fake_embeddings)

    folder = tmp_path / "EMP100_Rahul"
    folder.mkdir()
    (folder / "info.json").write_text(
        json.dumps({"name": "Rahul", "role": "Engineer", "department": "Lab", "email": "r@org.com"})
    )
    _write_img(folder / "one.jpg")
    _write_img(folder / "two.png")

    ingestion_service.register_person_from_folder(str(folder))

    assert vector_db.count_embeddings() == 2

    db = SessionLocal()
    try:
        person = db.query(Personnel).filter(Personnel.person_id == "EMP100").first()
        assert person is not None
        assert person.name == "Rahul"
        assert person.role == "Engineer"
    finally:
        db.close()


def test_single_file_registration(monkeypatch, tmp_path):
    from app.db.vector_db import vector_db
    from app.services.ingestion_service import ingestion_service

    monkeypatch.setattr("face_recognition.face_locations", _fake_locations)
    monkeypatch.setattr("face_recognition.face_encodings", _fake_embeddings)

    img = tmp_path / "EMP200_Bob.jpg"
    _write_img(img)
    ingestion_service.register_single_file(str(img))

    assert vector_db.count_embeddings() == 1
    assert vector_db.query_face(_fake_embeddings(None)[0])["match_id"] == "EMP200"


def test_enroll_endpoint_rejects_photo_without_face(client, admin_headers, monkeypatch):
    from app.services.ingestion_service import ingestion_service

    monkeypatch.setattr(ingestion_service, "register_person_from_folder", lambda *args, **kwargs: False)
    response = client.post(
        "/api/personnel/enroll",
        data={"person_id": "EMP_NO_FACE", "name": "No Face"},
        files={"photo": ("no-face.jpg", b"not-an-image", "image/jpeg")},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert "No face could be indexed" in response.json()["detail"]
    assert client.get("/api/personnel").json()["data"] == []