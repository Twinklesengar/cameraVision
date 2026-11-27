from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.sqlite_db import get_db
from app.db.models import IncidentAlert
from app.schemas.api import IncidentListOut, IncidentOut
from app.services.alert_dispatcher import alert_dispatcher
from app.routes.auth import require_admin

router = APIRouter(prefix="/api/alerts", tags=["Incident & Alert Management"])


@router.get("/", response_model=IncidentListOut)
def get_alerts(resolved: bool = False, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(IncidentAlert)
    if not resolved:
        query = query.filter(IncidentAlert.is_resolved == False)
    alerts = query.order_by(IncidentAlert.timestamp.desc()).limit(limit).all()
    return IncidentListOut(count=len(alerts), data=[IncidentOut.model_validate(a) for a in alerts])


@router.post("/resolve/{alert_id}", response_model=IncidentOut)
def resolve_alert(alert_id: int, db: Session = Depends(get_db), auth: dict = Depends(require_admin)):
    alert = db.query(IncidentAlert).filter(IncidentAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_resolved = True
    db.commit()
    db.refresh(alert)
    alert_dispatcher.broadcast_sync({
        "type": "ALERT_RESOLVED",
        "id": alert.id,
        "alert_type": alert.alert_type,
        "timestamp": alert.timestamp.isoformat() if alert.timestamp else None,
    })
    return IncidentOut.model_validate(alert)


@router.get("/types")
def get_alert_types(db: Session = Depends(get_db)):
    rows = db.query(IncidentAlert.alert_type, IncidentAlert.severity).distinct().all()
    types = [{"alert_type": t, "severity": s} for t, s in rows]
    return {"status": "success", "count": len(types), "data": types}