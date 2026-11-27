import json
from app.utils.timeutil import utcnow
import time
import cv2
import numpy as np
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from app.db.sqlite_db import SessionLocal
from app.db.models import AssetLog
from app.services.alert_service import emit_alert
from app.config import config


def _overlap(a: List[int], b: List[int]) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return not (ax2 < bx1 or bx2 < ax1 or ay2 < by1 or by2 < ay1)


class SpatialMemoryEngine:
    """Spatial Memory & Anti-Theft Asset Tracking.

    Remembers registered asset regions per camera. On every frame it compares the
    current region against a slowly-adapted background patch. Sustained motion in a
    registered region (without the owner present) raises a displacement alert; an
    UNKNOWN person near the asset escalates to a CRITICAL theft attempt.
    """

    def __init__(self):
        self.tracked_assets: Dict[str, Dict[str, Any]] = {}
        self._refs: Dict[str, np.ndarray] = {}
        self._motion_state: Dict[str, int] = {}
        self._last_alert: Dict[str, float] = {}

    # ---- API / registration ----
    def register_or_update_asset(self, asset_name: str, owner_id: str, bbox: List[int], camera_id: str = "cam_workspace"):
        db = SessionLocal()
        try:
            asset = db.query(AssetLog).filter(AssetLog.asset_name == asset_name).first()
            bbox_str = json.dumps(bbox)
            if not asset:
                asset = AssetLog(
                    asset_name=asset_name,
                    owner_person_id=owner_id,
                    last_seen_bbox=bbox_str,
                    camera_id=camera_id,
                    status="NORMAL",
                )
                db.add(asset)
            else:
                asset.last_seen_bbox = bbox_str
                asset.camera_id = camera_id
                asset.status = "NORMAL"
                asset.updated_at = utcnow()
            db.commit()
            self.tracked_assets[asset_name] = {
                "owner_id": owner_id,
                "bbox": [int(v) for v in bbox],
                "camera_id": camera_id,
                "status": "NORMAL",
            }
            self._refs.pop(asset_name, None)
            self._motion_state.pop(asset_name, None)
        except Exception as e:
            db.rollback()
            print(f"[SpatialMemory Error] {e}")
        finally:
            db.close()

    def delete_asset(self, asset_name: str) -> bool:
        db = SessionLocal()
        try:
            asset = db.query(AssetLog).filter(AssetLog.asset_name == asset_name).first()
            if not asset:
                return False
            db.delete(asset)
            db.commit()
            self.tracked_assets.pop(asset_name, None)
            self._refs.pop(asset_name, None)
            self._motion_state.pop(asset_name, None)
            return True
        finally:
            db.close()

    # ---- live surveillance ----
    def monitor(self, camera_id: str, frame: np.ndarray, detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Per-frame region-diff surveillance against registered assets on this camera."""
        if frame is None or frame.size == 0:
            return []
        now = time.time()
        alerts_generated = []
        h, w, _ = frame.shape

        db = SessionLocal()
        try:
            assets = db.query(AssetLog).filter(AssetLog.camera_id == camera_id).all()
            for asset in assets:
                stored = json.loads(asset.last_seen_bbox) if asset.last_seen_bbox else []
                if len(stored) < 4:
                    continue
                x1, y1, x2, y2 = (max(0, int(v)) for v in stored)
                x1, y1 = min(x1, w - 2), min(y1, h - 2)
                x2, y2 = max(x1 + 1, min(x2, w)), max(y1 + 1, min(y2, h))
                if (x2 - x1) < 4 or (y2 - y1) < 4:
                    continue

                crop = frame[y1:y2, x1:x2]
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                gray = cv2.resize(gray, (64, 48)).astype(np.float32)

                ref = self._refs.get(asset.asset_name)
                if ref is None:
                    self._refs[asset.asset_name] = gray
                    self._motion_state[asset.asset_name] = 0
                    continue

                diff = float(np.mean(np.abs(gray - ref)))
                movement = diff > config.ASSET_MOTION_DIFF_THRESHOLD

                if not movement:
                    self._motion_state[asset.asset_name] = 0
                    self._refs[asset.asset_name] = ref * 0.9 + gray * 0.1
                    continue

                owner_near = False
                stranger_near = False
                asset_bbox = [x1, y1, x2, y2]
                for det in detections:
                    if not _overlap(asset_bbox, det.get("bbox", [])):
                        continue
                    if det.get("person_id") == asset.owner_person_id:
                        owner_near = True
                    elif det.get("person_id") is not None:
                        stranger_near = True

                if owner_near:
                    self._motion_state[asset.asset_name] = 0
                    self._refs[asset.asset_name] = gray
                    continue

                state = self._motion_state.get(asset.asset_name, 0) + 1
                self._motion_state[asset.asset_name] = state
                if state < config.ASSET_MOTION_CONFIRM_FRAMES:
                    continue

                self._motion_state[asset.asset_name] = 0
                if now - self._last_alert.get(asset.asset_name, 0) < config.ASSET_ALERT_COOLDOWN_SECONDS:
                    continue
                self._last_alert[asset.asset_name] = now

                asset.status = "THEFT_SUSPECTED" if stranger_near else "DISPLACED_MISSING"
                db.add(asset)

                if stranger_near:
                    emit_alert(
                        alert_type="THEFT_ATTEMPT",
                        severity="CRITICAL",
                        description=f"CRITICAL THEFT ALERT: UNKNOWN individual near registered asset '{asset.asset_name}' (Owner: {asset.owner_person_id}).",
                        camera_id=camera_id,
                        person_id="UNKNOWN",
                    )
                    alerts_generated.append({
                        "asset_name": asset.asset_name,
                        "status": "THEFT_SUSPECTED",
                        "owner_id": asset.owner_person_id,
                    })
                else:
                    emit_alert(
                        alert_type="ASSET_DISPLACED",
                        severity="WARNING",
                        description=f"Asset '{asset.asset_name}' was moved/detected at a new location (Owner: {asset.owner_person_id}).",
                        camera_id=camera_id,
                        person_id=asset.owner_person_id,
                    )
                    alerts_generated.append({
                        "asset_name": asset.asset_name,
                        "status": "DISPLACED_MISSING",
                        "owner_id": asset.owner_person_id,
                    })

                self._refs[asset.asset_name] = gray

            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[SpatialMemory Error] {e}")
        finally:
            db.close()

        return alerts_generated


spatial_memory = SpatialMemoryEngine()