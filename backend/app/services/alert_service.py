from app.utils.timeutil import utcnow
from app.db.sqlite_db import SessionLocal
from app.db.models import IncidentAlert
from app.services.alert_dispatcher import alert_dispatcher
from app.services.notify import push_alert


def emit_alert(
    alert_type: str,
    severity: str = "WARNING",
    description: str = "",
    camera_id: str = "cam_main",
    person_id: str | None = None,
) -> IncidentAlert | None:
    """Persists an IncidentAlert and pushes it live to dashboard clients.

    Thread-safe: designed to be called from camera workers / services.
    """
    db = SessionLocal()
    alert = None
    try:
        alert = IncidentAlert(
            alert_type=alert_type,
            severity=severity,
            description=description,
            camera_id=camera_id,
            person_id=person_id,
            is_resolved=False,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
    except Exception as e:
        db.rollback()
        print(f"[AlertService Error] {e}")
    finally:
        db.close()

    if alert is not None:
        payload = {
            "type": "ALERT",
            "id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "description": alert.description,
            "camera_id": alert.camera_id,
            "person_id": alert.person_id,
            "timestamp": alert.timestamp.isoformat() if alert.timestamp else utcnow().isoformat(),
        }
        alert_dispatcher.broadcast_sync(payload)
        push_alert(payload)

    return alert


def has_pending_alert(camera_id: str, alert_type: str) -> bool:
    """True if an unresolved alert of `alert_type` already exists for the camera."""
    db = SessionLocal()
    try:
        return (
            db.query(IncidentAlert)
            .filter(
                IncidentAlert.camera_id == camera_id,
                IncidentAlert.alert_type == alert_type,
                IncidentAlert.is_resolved == False,
            )
            .first()
            is not None
        )
    finally:
        db.close()


def resolve_camera_alerts(camera_id: str, alert_type: str) -> int:
    """Mark all open alerts of `alert_type` for the camera as resolved. Returns count."""
    db = SessionLocal()
    count = 0
    try:
        rows = (
            db.query(IncidentAlert)
            .filter(
                IncidentAlert.camera_id == camera_id,
                IncidentAlert.alert_type == alert_type,
                IncidentAlert.is_resolved == False,
            )
            .all()
        )
        for row in rows:
            row.is_resolved = True
        db.commit()
        count = len(rows)
    except Exception as e:
        db.rollback()
        print(f"[AlertService Error] {e}")
    finally:
        db.close()
    return count