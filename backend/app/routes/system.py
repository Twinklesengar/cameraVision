import time
from app.utils.timeutil import utcnow
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import config
from app.db.sqlite_db import get_db
from app.db.models import AssetLog, AttendanceLog, HealthLog, IncidentAlert, Personnel, ProductivityLog
from app.db.vector_db import vector_db
from app.routes.auth import require_admin
from app.services.camera_manager import camera_manager

_START_TIME = time.time()

router = APIRouter(prefix="/api/system", tags=["System Health & Admin"])

_SENSITIVE_SUBSTR = ("JWT", "PASSWORD", "TOKEN", "SECRET", "API_KEY", "KEY")


@router.get("/health")
def system_health(db: Session = Depends(get_db)):
    cameras = []
    for cam in camera_manager.list_cameras():
        cameras.append({
            "camera_id": cam["camera_id"],
            "name": cam.get("name", cam["camera_id"]),
            "type": cam.get("type", "gate"),
            "online": bool(cam.get("online", False)),
            "last_frame_age": cam.get("last_frame_age"),
        })

    today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    counts = {
        "personnel": db.query(Personnel).count(),
        "attendance_today": db.query(AttendanceLog).filter(AttendanceLog.timestamp >= today_start).count(),
        "productivity": db.query(ProductivityLog).count(),
        "health_logs": db.query(HealthLog).count(),
        "alerts": db.query(IncidentAlert).count(),
        "unresolved_alerts": db.query(IncidentAlert).filter(IncidentAlert.is_resolved == False).count(),
        "assets": db.query(AssetLog).count(),
    }

    try:
        vector_stats = {"embeddings": vector_db.count_embeddings(), "persons_indexed": vector_db.count_persons()}
    except Exception:
        vector_stats = {"embeddings": 0, "persons_indexed": 0}

    return {
        "status": "success",
        "uptime_seconds": round(time.time() - _START_TIME, 1),
        "version": config.VERSION,
        "timestamp": utcnow().isoformat(),
        "cameras": cameras,
        "counts": counts,
        "vector_stats": vector_stats,
    }


@router.get("/logs")
def system_logs(
    lines: int = Query(40, ge=1, le=500),
    auth: dict = Depends(require_admin),
):
    """Tail of the active application log (admin only)."""
    log_file = config.LOGS_DIR / "aegisvision.log"
    if not log_file.exists():
        return {"status": "success", "lines": []}
    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        tail = f.readlines()[-lines:]
    return {"status": "success", "lines": [line.rstrip("\n") for line in tail]}


@router.get("/config")
def system_config(auth: dict = Depends(require_admin)):
    """Sanitized runtime configuration overview (admin only; secrets omitted)."""
    safe = {}
    for key, value in config.model_dump().items():
        if any(s in key.upper() for s in _SENSITIVE_SUBSTR):
            continue
        if isinstance(value, (str, int, float, bool)):
            safe[key] = value
    safe.pop("CAMERA_STREAMS", None)
    safe["cameras"] = {cid: cfg.get("name") for cid, cfg in config.CAMERA_STREAMS.items()}
    return {"status": "success", "config": safe}