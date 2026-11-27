import time
import cv2
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from app.config import config
from app.db.vector_db import vector_db
from app.services.face_backend import get_backend


class Track:
    """Single-face identity state maintained across frames."""

    __slots__ = (
        "tid", "bbox", "label", "person_id", "role", "confidence",
        "distance", "is_live", "last_seen", "last_embed", "seen",
    )

    def __init__(self, tid: int, bbox: Tuple[int, int, int, int]):
        self.tid = tid
        self.bbox = bbox
        self.label = None
        self.person_id = None
        self.role = "Employee"
        self.confidence = 0.0
        self.distance = 1.0
        self.is_live = False
        self.last_seen = time.time()
        self.last_embed = 0.0
        self.seen = 1


def _iou(a, b) -> float:
    """IoU between two (top, right, bottom, left) boxes."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = min(ax2, bx2) - max(ax1, bx1)
    ih = min(ay2, by2) - max(ay1, by1)
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)


class FaceRecognitionEngine:
    """
    Detection → trajectory tracking → (throttled) embedding + ChromaDB match → UNKNOWN tagging.

    Tracking lets a stable face reuse its label for several frames, so expensive
    embedding and vector queries run at `TRACK_REEMBED_INTERVAL_SEC` instead of
    every frame — this is what keeps crowded scenes fast.
    """

    def __init__(self):
        self.distance_threshold = config.FACE_DISTANCE_THRESHOLD
        self.anti_spoof_threshold = config.ANTI_SPOOF_THRESHOLD
        self.backend = get_backend()
        self._tracks: Dict[int, Track] = {}
        self._next_tid = 0

    # ---- liveness ----
    def check_liveness(self, face_crop: np.ndarray) -> Tuple[bool, float]:
        """Texture-based anti-spoofing score (kept as cheap fallback; CNN swap possible in Phase 1)."""
        if face_crop.size == 0:
            return False, 0.0
        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        liveness_score = min(1.0, laplacian_var / 350.0)
        return liveness_score >= 0.25, round(liveness_score, 2)

    # ---- detection + embedding (backend-agnostic) ----
    def _detect(self, rgb_small: np.ndarray, gray_small: np.ndarray):
        """Run the chosen backend; returns FaceHits when available else bare boxes."""
        try:
            return self.backend.detect(rgb_small, gray_small)
        except Exception as e:
            print(f"[FaceEngine] backend detect error: {e}")
            return []

    def _embed(self, rgb_small: np.ndarray, to_embed_locs: list, hits_by_box: dict) -> List[Optional[List[float]]]:
        """Embeddings for tracks whose re-embed window elapsed."""
        if not to_embed_locs:
            return []
        if self.backend.embeds_in_detect:
            return [hits_by_box.get(loc) for loc in to_embed_locs]
        return self._legacy_embed_locations(rgb_small, to_embed_locs)

    def _extract_embedding_fallback(self, rgb_image: np.ndarray, face_location: Tuple[int, int, int, int]) -> Optional[List[float]]:
        top, right, bottom, left = face_location
        crop = rgb_image[top:bottom, left:right]
        if crop.size > 0:
            resized = cv2.resize(crop, (32, 32))
            hist = cv2.calcHist([resized], [0, 1, 2], None, [4, 4, 8], [0, 256, 0, 256, 0, 256])
            vec = cv2.normalize(hist, hist).flatten().tolist()
            if len(vec) < 128:
                vec.extend([0.0] * (128 - len(vec)))
            return vec[:128]
        return None

    def _legacy_embed_locations(self, rgb_small: np.ndarray, locations: list) -> List[Optional[List[float]]]:
        """128-d embeddings for the legacy dlib path only."""
        if not locations:
            return []
        try:
            import face_recognition

            return face_recognition.face_encodings(rgb_small, known_face_locations=list(locations))
        except Exception:
            return [self._extract_embedding_fallback(rgb_small, loc) for loc in locations]

    # ---- tracker ----
    def _assign_tracks(self, boxes: List[Tuple[int, int, int, int]], now: float) -> List[Tuple[int, Tuple[int, int, int, int]]]:
        assignments = []
        used = set()
        for loc in boxes:
            best_tid, best_iou = None, config.TRACK_IOU_MIN
            for tid, t in self._tracks.items():
                if tid in used:
                    continue
                iou = _iou(t.bbox, loc)
                if iou > best_iou:
                    best_tid, best_iou = tid, iou
            if best_tid is None:
                best_tid = self._next_tid
                self._next_tid += 1
                self._tracks[best_tid] = Track(best_tid, loc)
            used.add(best_tid)
            t = self._tracks[best_tid]
            t.bbox, t.last_seen, t.seen = loc, now, t.seen + 1
            assignments.append((best_tid, loc))
        return assignments

    def _expire_tracks(self, now: float):
        stale = [tid for tid, t in self._tracks.items() if now - t.last_seen > config.TRACK_KEEP_SECONDS]
        for tid in stale:
            del self._tracks[tid]

    # ---- main pipeline ----
    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        detections: List[Dict[str, Any]] = []
        if frame is None or frame.size == 0:
            return frame, detections

        h, w, _ = frame.shape
        small = cv2.resize(frame, (w // 2, h // 2))
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        now = time.time()

        hits = self._detect(rgb_small, gray_small)
        boxes = [h.box for h in hits]
        if not boxes:
            self._expire_tracks(now)
            return frame, detections

        hits_by_box = {}
        if self.backend.embeds_in_detect:
            hits_by_box = {h.box: h.embedding for h in hits}

        assignments = self._assign_tracks(boxes, now)

        # Only embed/mismatch tracks whose re-embed window elapsed (or that are brand new).
        to_embed = []
        to_embed_tracks = []
        for tid, loc in assignments:
            t = self._tracks[tid]
            if t.person_id is None or (now - t.last_embed) >= config.TRACK_REEMBED_INTERVAL_SEC:
                t.last_embed = now
                to_embed.append(loc)
                to_embed_tracks.append(t)

        encodings = self._embed(rgb_small, to_embed, hits_by_box)
        for track, encoding in zip(to_embed_tracks, encodings):
            if encoding is None:
                continue
            result = vector_db.query_face(encoding)
            distance = result.get("distance", 1.0)
            meta = result.get("metadata", {})
            if result.get("match_id") and distance <= self.distance_threshold:
                track.person_id = result["match_id"]
                track.label = meta.get("name", result["match_id"])
                track.role = meta.get("role", "Employee")
                track.distance = distance
                track.confidence = round((1.0 - distance) * 100, 1)
            else:
                track.person_id = "UNKNOWN"
                track.label = "UNKNOWN"
                track.role = "Visitor/Unverified"
                track.distance = distance
                track.confidence = 0.0

        self._expire_tracks(now)

        SCALE = 2
        for tid, loc in assignments:
            t = self._tracks[tid]
            top, right, bottom, left = loc
            y1, x2, y2, x1 = top * SCALE, right * SCALE, bottom * SCALE, left * SCALE
            y1, y2 = max(0, y1), min(h, y2)
            x1, x2 = max(0, x1), min(w, x2)

            face_crop = frame[y1:y2, x1:x2]
            is_live, liveness_score = self.check_liveness(face_crop)
            t.is_live = is_live

            if t.person_id == "UNKNOWN":
                name, role = "UNKNOWN", "Visitor/Unverified"
                confidence = 0.0
                status_label = "UNKNOWN (SPOOF SUSPECT)" if not is_live else "UNKNOWN FACE"
                box_color = (0, 69, 255)
            else:
                name, role = t.label, t.role
                confidence = t.confidence
                status_label = f"{name} ({confidence}%)"
                box_color = (0, 255, 120)

            detections.append({
                "person_id": t.person_id,
                "name": name,
                "role": role,
                "confidence": confidence,
                "distance": t.distance,
                "is_live": is_live,
                "liveness_score": liveness_score,
                "bbox": [x1, y1, x2, y2],
            })

            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            cv2.rectangle(frame, (x1, y2 - 30), (x2, y2), box_color, cv2.FILLED)
            cv2.putText(frame, status_label, (x1 + 6, y2 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        return frame, detections


face_engine = FaceRecognitionEngine()