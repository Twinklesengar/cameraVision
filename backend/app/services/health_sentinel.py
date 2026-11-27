import cv2
import numpy as np
from typing import Dict, Any, List
from app.db.sqlite_db import SessionLocal
from app.db.models import HealthLog
from app.services.alert_service import emit_alert
from app.config import config

class HealthSentinelEngine:
    def __init__(self):
        self.drowsiness_tracker: Dict[str, int] = {}

    def calculate_eye_aspect_ratio(self, eye_points: np.ndarray) -> float:
        """
        Computes Eye Aspect Ratio (EAR).
        EAR drops significantly when eyes close or droop (drowsiness indicator).
        """
        if len(eye_points) < 6:
            return 0.30

        # Vertical eye landmarks
        A = np.linalg.norm(eye_points[1] - eye_points[5])
        B = np.linalg.norm(eye_points[2] - eye_points[4])
        # Horizontal eye landmark
        C = np.linalg.norm(eye_points[0] - eye_points[3])

        ear = (A + B) / (2.0 * C) if C > 0 else 0.30
        return float(ear)

    def analyze_health_and_posture(self, person_id: str, frame: np.ndarray, face_bbox: List[int], camera_id: str = "cam_workspace") -> Dict[str, Any]:
        """
        Analyzes employee/student ergonomics, eye closure fatigue, and posture.
        Logs telemetry to HealthLog in SQLite and triggers alerts on fatigue.
        """
        if person_id == "UNKNOWN" or not face_bbox:
            return {"drowsiness": False, "posture": "UNKNOWN"}

        x1, y1, x2, y2 = face_bbox
        face_w = x2 - x1
        face_h = y2 - y1

        # Posture check: head aspect ratio & vertical position relative to frame height
        posture_status = "GOOD"
        if face_h > 0:
            aspect = float(face_w) / face_h
            if aspect > 1.2 or y2 > frame.shape[0] * 0.85:
                posture_status = "SLOUCHING"

        # Eye aspect ratio & drowsiness simulation based on eye region intensity variance
        h, w, _ = frame.shape
        eye_region_y1 = max(0, y1 + int(face_h * 0.2))
        eye_region_y2 = min(h, y1 + int(face_h * 0.55))
        eye_crop = frame[eye_region_y1:eye_region_y2, x1:x2]

        ear_val = 0.28
        is_drowsy = False

        if eye_crop.size > 0:
            gray_eye = cv2.cvtColor(eye_crop, cv2.COLOR_BGR2GRAY)
            # Low contrast variance in eye region correlates with closed eyelids
            eye_std = np.std(gray_eye)
            if eye_std < 18.0:
                ear_val = 0.16
                is_drowsy = True

        count = self.drowsiness_tracker.get(person_id, 0)
        if is_drowsy:
            count += 1
            self.drowsiness_tracker[person_id] = count
        else:
            self.drowsiness_tracker[person_id] = max(0, count - 1)

        fatigue_score = min(1.0, count / 10.0)
        drowsiness_alert = count >= 8

        # Log health metrics
        db = SessionLocal()
        drowsiness_alert_fired = False
        try:
            log = HealthLog(
                person_id=person_id,
                drowsiness_detected=drowsiness_alert,
                eye_aspect_ratio=round(ear_val, 2),
                posture_status=posture_status,
                fatigue_score=round(fatigue_score, 2),
                camera_id=camera_id
            )
            db.add(log)

            if drowsiness_alert and count == 8:
                drowsiness_alert_fired = True

            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[HealthSentinel Error] {e}")
        finally:
            db.close()

        if drowsiness_alert_fired:
            emit_alert(
                alert_type="DROWSINESS_WARNING",
                severity="WARNING",
                description=f"Fatigue warning: Person {person_id} exhibits persistent eye closure / drowsiness.",
                camera_id=camera_id,
                person_id=person_id,
            )

        return {
            "drowsiness_alert": drowsiness_alert,
            "ear": round(ear_val, 2),
            "posture": posture_status,
            "fatigue_score": round(fatigue_score, 2)
        }

health_sentinel = HealthSentinelEngine()
