"""Prometheus text metrics for fleet/analysis gauges (text/plain scrape endpoint)."""

import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.sqlite_db import get_db
from app.db.models import IncidentAlert
from app.services.analysis_scheduler import analysis_scheduler
from app.services.camera_manager import camera_manager

router = APIRouter(tags=["Metrics"])

_START_TIME = time.time()


@router.get("/api/metrics")
def prometheus_metrics(db: Session = Depends(get_db)):
    cameras = camera_manager.list_cameras()
    total = len(cameras)
    online = sum(1 for c in cameras if c["online"])
    busy = sum(1 for c in cameras if c["online"] and c.get("scene_state") in ("BUSY", "CROWDED"))
    unresolved = db.query(IncidentAlert).filter(IncidentAlert.is_resolved == False).count()

    lines = [
        "# HELP aegis_analysis_budget_available Global face-analysis token budget remaining.",
        "# TYPE aegis_analysis_budget_available gauge",
        f"aegis_analysis_budget_available {analysis_scheduler.available()}",
        "# HELP aegis_analysis_queue Depth of the bounded analysis work queue.",
        "# TYPE aegis_analysis_queue gauge",
        f"aegis_analysis_queue {analysis_scheduler.queue_depth()}",
        "# HELP aegis_cameras_total Configured cameras.",
        "# TYPE aegis_cameras_total gauge",
        f"aegis_cameras_total {total}",
        "# HELP aegis_cameras_online Cameras delivering frames right now.",
        "# TYPE aegis_cameras_online gauge",
        f"aegis_cameras_online {online}",
        "# HELP aegis_cameras_busy Cameras in a busy/crowded scene.",
        "# TYPE aegis_cameras_busy gauge",
        f"aegis_cameras_busy {busy}",
        "# HELP aegis_alerts_unresolved Open incidents.",
        "# TYPE aegis_alerts_unresolved gauge",
        f"aegis_alerts_unresolved {unresolved}",
        "# HELP aegis_uptime_seconds Process uptime.",
        "# TYPE aegis_uptime_seconds gauge",
        f"aegis_uptime_seconds {round(time.time() - _START_TIME, 1)}",
    ]
    return Response(content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")