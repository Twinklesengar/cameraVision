from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.services.camera_manager import camera_manager
from app.services.camera_registry import camera_registry
from app.db.sqlite_db import get_db
from app.db.models import Personnel, AttendanceLog, ProductivityLog, HealthLog, AssetLog, IncidentAlert, CameraActivityLog
from app.utils.timeutil import utcnow
from app.schemas.api import (
    AttendanceListOut,
    AttendanceOut,
    ProductivityListOut,
    ProductivityOut,
    HealthListOut,
    HealthOut,
    AssetListOut,
    AssetOut,
    DashboardOut,
    DashboardSummary,
    PersonDailyOut,
    OccupancyOut,
)

router = APIRouter(prefix="/api/analytics", tags=["Surveillance Analytics"])


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard_summary(db: Session = Depends(get_db)):
    today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    summary = DashboardSummary(
        total_personnel=db.query(Personnel).count(),
        today_attendance=db.query(AttendanceLog).filter(AttendanceLog.timestamp >= today_start).count(),
        unresolved_alerts=db.query(IncidentAlert).filter(IncidentAlert.is_resolved == False).count(),
        total_assets=db.query(AssetLog).count(),
        theft_threats=db.query(AssetLog).filter(AssetLog.status == "THEFT_SUSPECTED").count(),
        productive_sessions=db.query(ProductivityLog).filter(
            ProductivityLog.timestamp >= today_start, ProductivityLog.status == "PRODUCTIVE"
        ).count(),
        phone_distractions=db.query(ProductivityLog).filter(
            ProductivityLog.timestamp >= today_start, ProductivityLog.status == "PHONE_DISTRACTED"
        ).count(),
        bunking_incidents=db.query(ProductivityLog).filter(
            ProductivityLog.timestamp >= today_start, ProductivityLog.status == "BUNKING"
        ).count(),
        health_warnings=db.query(HealthLog).filter(
            HealthLog.timestamp >= today_start, HealthLog.drowsiness_detected == True
        ).count(),
    )

    return DashboardOut(status="success", timestamp=utcnow().isoformat(), summary=summary)


@router.get("/occupancy", response_model=List[OccupancyOut])
def get_occupancy(db: Session = Depends(get_db)):
    """Live gate occupancy across the registered gate cameras."""
    result = []
    for cam in camera_manager.list_cameras():
        if cam.get("type") != "gate" or not cam.get("active"):
            continue
        occ = cam.get("occupancy")
        if occ is None:
            continue
        occ.pop("camera_id", None)
        result.append(OccupancyOut(camera_id=cam["camera_id"], **occ))
    return result


@router.get("/camera-activity")
def get_camera_activity(camera_id: str, hours: int = 24, db: Session = Depends(get_db)):
    """Per-camera persisted activity series (minute buckets) for 24h/7d charts."""
    if hours < 1 or hours > 168:
        raise HTTPException(status_code=400, detail="hours must be between 1 and 168")
    cfg = camera_registry.get(camera_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    since = utcnow() - timedelta(hours=hours)
    rows = (
            db.query(CameraActivityLog)
            .filter(CameraActivityLog.camera_id == camera_id, CameraActivityLog.bucket >= since)
            .order_by(CameraActivityLog.bucket.asc())
            .all()
    )
    return {
        "status": "success",
        "camera_id": camera_id,
        "hours": hours,
        "granularity": "minute",
        "data": [
            {
                "bucket": r.bucket.isoformat(),
                "avg_motion": r.avg_motion,
                "peak_motion": r.peak_motion,
                "crowd_seconds": r.crowd_seconds,
                "people_seen": r.people_seen,
                "analyzed_count": r.analyzed_count,
            }
            for r in rows
        ],
    }


@router.get("/attendance", response_model=AttendanceListOut)
def get_attendance_logs(limit: int = 50, db: Session = Depends(get_db)):
    logs = db.query(AttendanceLog).order_by(AttendanceLog.timestamp.desc()).limit(limit).all()
    return AttendanceListOut(count=len(logs), data=[AttendanceOut.model_validate(l) for l in logs])


@router.get("/productivity", response_model=ProductivityListOut)
def get_productivity_logs(limit: int = 50, db: Session = Depends(get_db)):
    logs = db.query(ProductivityLog).order_by(ProductivityLog.timestamp.desc()).limit(limit).all()
    return ProductivityListOut(count=len(logs), data=[ProductivityOut.model_validate(l) for l in logs])


@router.get("/health", response_model=HealthListOut)
def get_health_logs(limit: int = 50, db: Session = Depends(get_db)):
    logs = db.query(HealthLog).order_by(HealthLog.timestamp.desc()).limit(limit).all()
    return HealthListOut(count=len(logs), data=[HealthOut.model_validate(l) for l in logs])


@router.get("/assets", response_model=AssetListOut)
def get_asset_logs(db: Session = Depends(get_db)):
    assets = db.query(AssetLog).all()
    return AssetListOut(count=len(assets), data=[AssetOut.model_validate(a) for a in assets])


@router.get("/timeseries")
def get_timeseries(metric: str = "attendance", hours: int = 24, db: Session = Depends(get_db)):
    """Hourly-grouped event counts (`metric` = attendance | productivity | health | alerts)."""
    metric_map = {
        "attendance": (AttendanceLog, "event_type"),
        "productivity": (ProductivityLog, "status"),
        "health": (HealthLog, "drowsiness_detected"),
        "alerts": (IncidentAlert, "severity"),
    }
    if metric not in metric_map or hours < 1 or hours > 168:
        raise HTTPException(status_code=400, detail="metric must be attendance|productivity|health|alerts and 1<=hours<=168")

    model, label_field = metric_map[metric]
    since = utcnow() - timedelta(hours=hours)
    rows = db.query(model).filter(model.timestamp >= since).all()

    buckets: dict[str, dict] = {}
    for r in rows:
        key = r.timestamp.strftime("%Y-%m-%dT%H:00:00")
        bucket = buckets.setdefault(key, {"bucket": key, "count": 0, "by_label": {}})
        bucket["count"] += 1
        label = str(getattr(r, label_field))
        bucket["by_label"][label] = bucket["by_label"].get(label, 0) + 1

    return {
        "status": "success",
        "metric": metric,
        "hours": hours,
        "data": [buckets[k] for k in sorted(buckets)],
    }


@router.get("/person/{person_id}/{day}", response_model=PersonDailyOut)
def get_person_daily(person_id: str, day: str, db: Session = Depends(get_db)):
    """Per-person daily summary (Phase 2 aggregation). `day` = YYYY-MM-DD (local)."""
    from datetime import datetime as _dt

    try:
        day_start = _dt.strptime(day, "%Y-%m-%d")
    except ValueError:
        return PersonDailyOut(person_id=person_id, date=day)

    day_end = day_start + timedelta(days=1)
    logs = (
        db.query(ProductivityLog)
        .filter(
            ProductivityLog.person_id == person_id,
            ProductivityLog.timestamp >= day_start,
            ProductivityLog.timestamp < day_end,
        )
        .all()
    )

    seconds = {"PRODUCTIVE": 0, "LAZY_IDLE": 0, "BUNKING": 0, "PHONE_DISTRACTED": 0}
    for log in logs:
        seconds[log.status] = seconds.get(log.status, 0) + int(log.duration_seconds or 0)

    entries = db.query(AttendanceLog).filter(
        AttendanceLog.person_id == person_id,
        AttendanceLog.timestamp >= day_start,
        AttendanceLog.timestamp < day_end,
        AttendanceLog.event_type == "ENTRY",
    ).count()
    exits = db.query(AttendanceLog).filter(
        AttendanceLog.person_id == person_id,
        AttendanceLog.timestamp >= day_start,
        AttendanceLog.timestamp < day_end,
        AttendanceLog.event_type == "EXIT",
    ).count()

    total = max(1, sum(seconds.values()))
    score = round(seconds["PRODUCTIVE"] / total, 2)

    return PersonDailyOut(
        person_id=person_id,
        date=day,
        active_seconds=seconds["PRODUCTIVE"],
        idle_seconds=seconds["LAZY_IDLE"],
        bunk_seconds=seconds["BUNKING"],
        phone_seconds=seconds["PHONE_DISTRACTED"],
        productive_score=score,
        entries=entries,
        exits=exits,
    )