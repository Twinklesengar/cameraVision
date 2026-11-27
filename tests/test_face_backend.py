"""Recognition backend selection and the insightface/ONNX fast path."""

import numpy as np
import pytest


def test_legacy_backend_chosen_when_forced():
    import app.services.face_backend as mod

    mod._backend = None
    original = mod._build_backend
    mod._build_backend = lambda: mod.LegacyBackend()
    try:
        assert mod.get_backend().name == "legacy"
    finally:
        mod._build_backend = original
        mod._backend = None


def test_insightface_backend_never_raises_when_probed():
    """Whether insightface loads or falls back, selection must not crash."""
    import app.services.face_backend as mod

    mod._backend = None
    original = mod._build_backend
    mod._build_backend = original  # real builder (probes model availability)
    try:
        backend = mod.get_backend()
        assert backend.name in ("insightface", "legacy")
    finally:
        mod._backend = None


def test_insightface_real_photo_produces_512d_embedding(tmp_path):
    """End-to-end on a real face photo when the ONNX model is present. Skips otherwise."""
    import glob
    import os
    import cv2

    photos = (
        glob.glob(os.path.join(os.path.dirname(__file__), "..", "photos", "*"))
        or glob.glob(os.path.join(os.path.dirname(__file__), "..", "backend", "data", "known_persons", "**", "*"), recursive=True)
    )
    photos = [p for p in photos if p.lower().endswith((".jpg", ".jpeg", ".png"))]

    from app.services import face_backend as mod

    candidacy = mod.InsightFaceBackend()
    try:
        candidacy._ensure_app()
    except Exception as e:
        pytest.skip(f"insightface model unavailable: {e}")

    hit = None
    for p in photos:
        img = cv2.imread(p)
        if img is None:
            continue
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        hit = candidacy.embed_photo(rgb)
        if hit is not None:
            break

    if hit is None:
        pytest.skip("no photo with a detectable face found")

    assert len(hit) == 512
    assert all(np.isfinite(hit))