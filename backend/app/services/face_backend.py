"""Recognition backend: lightweight SCRFD+ArcFace (insightface/ONNX) with fallback.

`get_backend()` returns a singleton chosen from `FACE_BACKEND`:

- `insightface` / `auto`: SCRFD detector + ArcFace embedder (aligned 512-d) from
  the insightface model zoo, running on `onnxruntime` CPU/GPU execution
  providers. This is the lightweight-and-accurate replacement for dlib.
- `legacy`: the original dlib `face_recognition` hog detector + OpenFace
  128-d embedder (or a Haar cascade fallback).

Both expose the same `detect(rgb, gray)` -> [FaceHit] contract and a
`embed_photo(rgb)` helper used at enrollment/sync time, so the rest of the
pipeline never cares which backend it is.
"""

import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from app.config import config


@dataclass
class FaceHit:
    box: Tuple[int, int, int, int]          # (top, right, bottom, left)
    embedding: Optional[List[float]] = None
    keypoints: Optional[np.ndarray] = None  # (5, 2) aligned landmarks


class LegacyBackend:
    name = "legacy"
    dim = 128  # dlib OpenFace
    embeds_in_detect = False

    def __init__(self):
        self.haar_cascade = None
        try:
            import cv2  # type: ignore
            self.haar_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
        except Exception:
            pass

    def detect(self, rgb: np.ndarray, gray: Optional[np.ndarray] = None) -> List[FaceHit]:
        try:
            import face_recognition

            locs = face_recognition.face_locations(rgb, model="hog")
            return [FaceHit(box=(t, r, b, l)) for (t, r, b, l) in locs]
        except Exception:
            if self.haar_cascade is None or gray is None:
                return []
            faces = self.haar_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            return [FaceHit(box=(y, x + w, y + h, x)) for (x, y, w, h) in faces]

    def embed_photo(self, rgb: np.ndarray) -> Optional[List[float]]:
        try:
            import face_recognition

            locs = face_recognition.face_locations(rgb)
            if not locs:
                return None
            encs = face_recognition.face_encodings(rgb, known_face_locations=locs)
            if not encs:
                return None
            largest = max(range(len(locs)), key=lambda i: (locs[i][2] - locs[i][0]) * (locs[i][1] - locs[i][3]))
            return encs[largest].tolist()
        except Exception:
            return None


class InsightFaceBackend:
    name = "insightface"
    dim = 512  # ArcFace (w600k) aligned embedding
    embeds_in_detect = True  # each detected face already carries its embedding

    def __init__(self):
        self._app = None
        self._lock = threading.Lock()

    def _ensure_app(self):
        if self._app is not None:
            return self._app
        with self._lock:
            if self._app is not None:
                return self._app
            from insightface.app import FaceAnalysis  # deferred: heavy import

            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if config.FACE_USE_GPU else ["CPUExecutionProvider"]
            self._app = FaceAnalysis(name=config.FACE_INSIGHTFACE_MODEL, providers=providers)
            self._app.prepare(ctx_id=0 if config.FACE_USE_GPU else -1, det_size=(config.FACE_DET_SIZE, config.FACE_DET_SIZE))
            return self._app

    def detect(self, rgb: np.ndarray, gray: Optional[np.ndarray] = None) -> List[FaceHit]:
        app = self._ensure_app()
        faces = app.get(rgb)
        hits = []
        for f in faces:
            x1, y1, x2, y2 = (int(v) for v in f.bbox)
            embedding = None
            if getattr(f, "embedding", None) is not None:
                embedding = [float(v) for v in f.embedding]
            keypoints = np.asarray(getattr(f, "kps", None)) if getattr(f, "kps", None) is not None else None
            hits.append(FaceHit(box=(y1, x2, y2, x1), embedding=embedding, keypoints=keypoints))
        return hits

    def embed_photo(self, rgb: np.ndarray) -> Optional[List[float]]:
        hits = self.detect(rgb)
        if not hits:
            return None
        best = max(hits, key=lambda h: (h.box[2] - h.box[0]) * (h.box[3] - h.box[1]))
        return best.embedding


def _build_backend():
    want = (config.FACE_BACKEND or "auto").lower()
    if want == "legacy":
        print("[FaceBackend] using legacy dlib pipeline")
        return LegacyBackend()
    try:
        backend = InsightFaceBackend()
        backend.detect(np.zeros((64, 64, 3), dtype=np.uint8))  # probe load (models + wiring)
        print(f"[FaceBackend] using insightface/{config.FACE_INSIGHTFACE_MODEL} (ONNX, lightweight)")
        return backend
    except Exception as e:
        print(f"[FaceBackend] insightface unavailable ({e}); falling back to legacy dlib pipeline")
        return LegacyBackend()


_backend_lock = threading.Lock()
_backend = None


def get_backend():
    """Return the shared recognition backend (chosen once, thread-safe)."""
    global _backend
    if _backend is None:
        with _backend_lock:
            if _backend is None:
                _backend = _build_backend()
    return _backend