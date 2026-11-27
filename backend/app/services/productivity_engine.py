import time
import cv2
import numpy as np
from datetime import datetime
from typing import Dict, Any, List
from app.db.sqlite_db import SessionLocal
from app.db.models import ProductivityLog
from app.services.alert_service import emit_alert
from app.config import config

class ProductivityEngine:
    def __init__(self):
        self.presence_tracker: Dict[str, Dict[str, Any]] = {}

    def detect_phone_in_hand_or_face(self, frame: np.ndarray, face_bbox: List[int]) -> bool:
        """
        Detects smartphone usage near the face area using color & edge analysis.
        Mobile screens/chassis exhibit rectangular contours and high screen contrast near hands/face.
        """
        if frame is None or not face_bbox or len(face_bbox) < 4:
            return False

        x1, y1, x2, y2 = face_bbox
        h, w, _ = frame.shape

        # Define search region around face (hands holding phone near chin/cheek)
        roi_y1 = max(0, y1 - 20)
        roi_y2 = min(h, y2 + 100)
        roi_x1 = max(0, x1 - 60)
        roi_x2 = min(w, x2 + 60)

        roi = frame[roi_y1:roi_y2, roi_x1:roi_x2]
        if roi.size == 0:
            return False

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 75, 200)

        # Look for rectangular contours matching standard phone aspect ratio (approx 16:9 or 2:1)
        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 800 < area < 15000:
                peri = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
                if len(approx) == 4:
                    rx, ry, rw, rh = cv2.boundingRect(cnt)
                    aspect_ratio = float(rh) / rw if rw > 0 else 0
                    if 1.4 < aspect_ratio < 2.5 or 0.4 < aspect_ratio < 0.7:
                        return True
        return False

    def update_presence(self, person_id: str, is_present: bool, camera_id: str, frame: np.ndarray = None, face_bbox: List[int] = None) -> Dict[str, Any]:
        """
        Updates employee/student workstation presence state.
        Tracks active desk time, idle time, bunking, and phone usage.
        """
        if person_id == "UNKNOWN":
            return {"status": "UNKNOWN_VISITOR"}

        now = time.time()
        if person_id not in self.presence_tracker:
            self.presence_tracker[person_id] = {
                "first_seen": now,
                "last_seen": now,
                "active_time": 0,
                "phone_time": 0,
                "status": "PRODUCTIVE",
                "phone_counter": 0
            }

        tracker = self.presence_tracker[person_id]

        if is_present:
            elapsed = now - tracker["last_seen"]
            tracker["active_time"] += elapsed if elapsed < 10 else 1
            tracker["last_seen"] = now

            # Check phone usage
            has_phone = False
            if frame is not None and face_bbox:
                has_phone = self.detect_phone_in_hand_or_face(frame, face_bbox)

            if has_phone:
                tracker["phone_counter"] += 1
                tracker["phone_time"] += 1
                if tracker["phone_counter"] > 5:
                    tracker["status"] = "PHONE_DISTRACTED"
            else:
                tracker["phone_counter"] = max(0, tracker["phone_counter"] - 1)
                if tracker["phone_counter"] == 0:
                    tracker["status"] = "PRODUCTIVE"

        else:
            idle_duration = now - tracker["last_seen"]
            if idle_duration > config.IDLE_TIMEOUT_SECONDS:
                tracker["status"] = "BUNKING"
            elif idle_duration > 60:
                tracker["status"] = "LAZY_IDLE"

        # Log session status to SQLite
        db = SessionLocal()
        alert_trigger = None
        try:
            log = ProductivityLog(
                person_id=person_id,
                status=tracker["status"],
                duration_seconds=int(tracker["active_time"]),
                camera_id=camera_id,
                notes=f"Phone time: {int(tracker['phone_time'])}s"
            )
            db.add(log)

            # Trigger alert for excessive phone use or bunking
            if tracker["status"] in ["PHONE_DISTRACTED", "BUNKING"] and tracker["phone_counter"] == 6:
                alert_trigger = (
                    "PHONE_OVERUSE" if tracker["status"] == "PHONE_DISTRACTED" else "BUNKING_EXCEEDED",
                    tracker["status"],
                )

            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[ProductivityEngine Error] {e}")
        finally:
            db.close()

        if alert_trigger:
            alert_type, status = alert_trigger
            emit_alert(
                alert_type=alert_type,
                severity="WARNING",
                description=f"Person {person_id} flagged for {status} at workstation.",
                camera_id=camera_id,
                person_id=person_id,
            )

        return tracker

productivity_engine = ProductivityEngine()
