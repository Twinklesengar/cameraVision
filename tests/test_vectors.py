"""VectorDB multi-embedding semantics: one vector per photo, grouped by person."""

import pytest


def test_add_and_query_single():
    from app.db.vector_db import vector_db

    vector_db.add_face_embedding("EMP1::a.jpg", "EMP1", [1.0, 0.0] * 64, {"name": "Alice"})
    result = vector_db.query_face([1.0, 0.0] * 64)
    assert result["match_id"] == "EMP1"
    assert result["metadata"]["name"] == "Alice"
    assert result["distance"] < 0.01


def test_multiple_photos_do_not_overwrite():
    from app.db.vector_db import vector_db

    vector_db.add_face_embedding("EMP1::a.jpg", "EMP1", [1.0, 0.0] * 64, {"name": "Alice"})
    vector_db.add_face_embedding("EMP1::b.jpg", "EMP1", [0.9, 0.1] * 64, {"name": "Alice"})
    assert vector_db.count_embeddings() == 2

    result = vector_db.query_face([0.9, 0.1] * 64)
    assert result["match_id"] == "EMP1"
    assert result["distance"] < 0.01


def test_delete_person_removes_all_vectors():
    from app.db.vector_db import vector_db

    vector_db.add_face_embedding("EMP1::a.jpg", "EMP1", [1.0, 0.0] * 64, {"name": "Alice"})
    vector_db.add_face_embedding("EMP1::b.jpg", "EMP1", [0.9, 0.1] * 64, {"name": "Alice"})
    vector_db.add_face_embedding("EMP2::a.jpg", "EMP2", [0.0, 1.0] * 64, {"name": "Bob"})

    vector_db.delete_person_embeddings("EMP1")
    assert vector_db.count_embeddings() == 1
    assert vector_db.count_persons() == 1


def test_empty_db_returns_no_match():
    from app.db.vector_db import vector_db

    assert vector_db.count_embeddings() == 0
    result = vector_db.query_face([0.5] * 128)
    assert result["match_id"] is None


def test_rebuilds_collection_when_embedding_dim_changes():
    """Backend swap (dlib 128-d -> insightface 512-d) must not leave the index unusable."""
    from app.db.vector_db import vector_db

    vector_db.add_face_embedding("EMP1::a.jpg", "EMP1", [0.1] * 4, {"name": "Alice"})
    assert vector_db.count_embeddings() == 1

    # Authoring writes vectors with a different dimensionality: dim mismatch is
    # detected on first write of the new shape and the collection is rebuilt.
    vector_db.add_face_embedding("EMP2::a.jpg", "EMP2", [0.2] * 8, {"name": "Bob"})
    assert vector_db.count_embeddings() == 1
    result = vector_db.query_face([0.2] * 8)
    assert result["match_id"] == "EMP2"