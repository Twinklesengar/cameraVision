"""Runtime camera registry.

The camera set a worker fleet runs is the *merged* view of:

1. the baseline map `config.CAMERA_STREAMS` (env / settings defaults), and
2. persistent overrides in the `camera_streams` SQLite table.

A row whose `id` matches a baseline camera replaces that baseline's
name/source/type and (important for corporate ops) a row with `active=False`
disables the camera for this session *across restarts* — the baseline entry
comes back only if the override row is deleted. Brand-new camera ids are pure
additions. This gives operators a durable, admin-only way to manage the fleet
without touching environment variables.
"""

import threading
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select

from app.config import config
from app.db.sqlite_db import SessionLocal
from app.db.models import CameraStream

_VALID_SCHEMES = ("http", "https", "rtsp", "rtsps")


class CameraRegistry:
    def __init__(self):
        self._lock = threading.Lock()

    # ---- source validation ----
    @staticmethod
    def normalize_source(source: Any) -> Any:
        """Return a worker-ready source (int index, or validated stream URL)."""
        if isinstance(source, int):
            return source
        if isinstance(source, float):
            if source == int(source):
                return int(source)
            raise ValueError("camera source must be an integer index or a stream URL")
        text = str(source).strip()
        if not text:
            raise ValueError("camera source cannot be empty")
        try:
            return int(text)
        except ValueError:
            pass
        scheme, _, _ = text.partition("://")
        if scheme.lower() not in _VALID_SCHEMES:
            raise ValueError(
                f"camera source URL must use one of {', '.join(_VALID_SCHEMES)} schemes"
            )
        return text

    @staticmethod
    def redact_source(source: Any) -> str:
        """Strip credentials out of an RTSP/HTTP url for human-facing output."""
        text = str(source)
        if "://" not in text:
            return text
        prefix, rest = text.split("://", 1)
        userinfo, _, rest_after = rest.rpartition("@")
        if not userinfo or not rest.startswith(userinfo + "@"):
            return text
        head, _, tail = userinfo.partition(":")
        if ":" not in userinfo:
            return prefix + "://" + "***@" + rest_after
        return prefix + "://" + head + ":***@" + rest_after

    # ------------------------------------------------------------------
    # persistence primitives
    # ------------------------------------------------------------------
    def _get_row(self, db, camera_id: str) -> Optional[Any]:
        return db.execute(select(CameraStream).where(CameraStream.id == camera_id)).scalar_one_or_none()

    @staticmethod
    def _row_to_cfg(row: CameraStream) -> Dict[str, Any]:
        try:
            source = CameraRegistry.normalize_source(row.source)
        except ValueError:
            source = row.source
        return {
            "camera_id": row.id,
            "name": row.name,
            "source": source,
            "type": row.type,
            "resolution": row.resolution,
            "fps_limit": row.fps_limit,
            "active": bool(row.active),
        }

    def _baseline(self) -> Dict[str, Dict[str, Any]]:
        """The default catalog from settings/env, before any overrides."""
        out = {}
        for cam_id, cfg in config.CAMERA_STREAMS.items():
            out[cam_id] = {
                "camera_id": cam_id,
                "name": cfg.get("name", cam_id),
                "source": self.normalize_source(cfg.get("source", 0)),
                "type": cfg.get("type", "gate"),
                "resolution": None,
                "fps_limit": None,
                "active": True,
            }
        return out

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def configs(self) -> Dict[str, Dict[str, Any]]:
        """Merged, effective camera catalog (baseline + persistent overrides)."""
        with self._lock:
            merged = self._baseline()
            db = SessionLocal()
            try:
                rows = db.execute(select(CameraStream).order_by(CameraStream.id)).scalars().all()
                for row in rows:
                    merged[row.id] = self._row_to_cfg(row)
            finally:
                db.close()
            return merged

    def get(self, camera_id: str) -> Optional[Dict[str, Any]]:
        return self.configs().get(camera_id)

    def exists(self, camera_id: str) -> bool:
        with self._lock:
            db = SessionLocal()
            try:
                return self._get_row(db, camera_id) is not None
            finally:
                db.close()

    def add(
        self,
        camera_id: str,
        name: str,
        source: Any,
        cam_type: str = "gate",
        resolution: Optional[str] = None,
        fps_limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Insert a brand-new camera. Rejects ids that already exist as rows."""
        normalized = self.normalize_source(source)
        camera_id = camera_id.strip()
        with self._lock:
            db = SessionLocal()
            try:
                if self._get_row(db, camera_id) is not None:
                    raise ValueError(f"camera {camera_id!r} already registered")
                db.add(CameraStream(
                    id=camera_id,
                    name=name.strip(),
                    source=str(normalized),
                    type=cam_type,
                    resolution=resolution,
                    fps_limit=fps_limit,
                    active=True,
                ))
                db.commit()
            except ValueError:
                db.rollback()
                raise
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        return self.get(camera_id)

    def update(self, camera_id: str, **fields) -> Optional[Dict[str, Any]]:
        """Update persisted fields (and/or flips `active`). Returns None if unknown id."""
        allowed = {"name", "source", "cam_type", "resolution", "fps_limit", "active"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported camera fields: {', '.join(sorted(unknown))}")
        if "source" in fields and fields["source"] is not None:
            fields["source"] = str(self.normalize_source(fields["source"]))
        if "cam_type" in fields:
            fields["type"] = fields.pop("cam_type")
        with self._lock:
            db = SessionLocal()
            try:
                row = self._get_row(db, camera_id)
                if row is None:
                    base = self._baseline().get(camera_id)
                    if base is None:
                        return None
                    row = CameraStream(
                        id=camera_id,
                        name=base["name"],
                        source=str(base["source"]),
                        type=base["type"],
                        active=base["active"],
                    )
                    db.add(row)
                for key, value in fields.items():
                    if value is None:
                        continue
                    if hasattr(row, key):
                        setattr(row, key, value)
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        return self.get(camera_id)

    def set_active(self, camera_id: str, active: bool) -> Optional[Dict[str, Any]]:
        return self.update(camera_id, active=bool(active))

    def delete(self, camera_id: str) -> bool:
        """Physically remove the override row (baseline may take over again)."""
        with self._lock:
            db = SessionLocal()
            try:
                row = self._get_row(db, camera_id)
                if row is None:
                    return False
                db.delete(row)
                db.commit()
                return True
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()


camera_registry = CameraRegistry()