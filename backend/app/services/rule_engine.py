import asyncio
from app.utils.timeutil import utcnow
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from app.config import config
from app.db.sqlite_db import SessionLocal
from app.db.models import AttendanceLog, HealthLog, ProductivityLog
from app.services.alert_service import emit_alert

logger = logging.getLogger("aegisvision.rule_engine")


class RuleEngine:
    """Background rule-based escalation over recent telemetry.

    Runs a periodic sweep (RULE_SWEEP_INTERVAL_SEC) that looks for repeated signals
    inside the RULE_WINDOW_MIN window and emits severity-ranked IncidentAlerts
    (which are WS-pushed and forwarded to external providers by alert_service).
    Per-signal dedupe prevents alert storms.
    """

    def __init__(self):
        self._last_emitted: dict[str, datetime] = {}
        self._running = False

    def _dedupe(self, key: str) -> bool:
        now = utcnow()
        last = self._last_emitted.get(key)
        if last and (now - last).total_seconds() < config.ESCALATION_DEDUPE_SEC:
            return False
        self._last_emitted[key] = now
        return True

    def sweep(self) -> int:
        """Evaluate rules once; returns number of alerts emitted."""
        db = SessionLocal()
        emitted = 0
        try:
            since = utcnow() - timedelta(minutes=config.RULE_WINDOW_MIN)
            window_desc = f"last {config.RULE_WINDOW_MIN} min"

            unknown_count = (
                db.query(AttendanceLog)
                .filter(AttendanceLog.timestamp >= since, AttendanceLog.name == "UNKNOWN")
                .count()
            )
            if unknown_count >= config.UNKNOWN_GATE_COUNT and self._dedupe("UNKNOWN_GATE_REPEATED"):
                emit_alert(
                    alert_type="UNKNOWN_REPEATED",
                    severity="CRITICAL",
                    description=f"{unknown_count} UNKNOWN individuals registered at the gate in the {window_desc}. Consider reviewing footage.",
                    camera_id="cam_entrance",
                )
                emitted += 1

            per_person = defaultdict(int)
            for row in (
                db.query(ProductivityLog)
                .filter(ProductivityLog.timestamp >= since, ProductivityLog.status == "PHONE_DISTRACTED")
                .all()
            ):
                if row.person_id:
                    per_person[row.person_id] += 1
            for person_id, cnt in per_person.items():
                if cnt >= config.PHONE_OVERUSE_COUNT and self._dedupe(f"PHONE_OVERUSE_{person_id}"):
                    emit_alert(
                        alert_type="PHONE_OVERUSE",
                        severity="WARNING",
                        description=f"{person_id} was phone-distracted {cnt} times in the {window_desc}.",
                        camera_id="cam_workspace",
                        person_id=person_id,
                    )
                    emitted += 1

            drowsy = defaultdict(int)
            for row in (
                db.query(HealthLog)
                .filter(HealthLog.timestamp >= since, HealthLog.drowsiness_detected == True)
                .all()
            ):
                if row.person_id:
                    drowsy[row.person_id] += 1
            for person_id, cnt in drowsy.items():
                if cnt >= config.DROWSINESS_REPEAT_COUNT and self._dedupe(f"DROWSINESS_{person_id}"):
                    emit_alert(
                        alert_type="DROWSINESS_WARNING",
                        severity="WARNING",
                        description=f"Repeated drowsiness for {person_id} ({cnt} detections in the {window_desc}). Fatigue risk.",
                        camera_id="cam_workspace",
                        person_id=person_id,
                    )
                    emitted += 1

            return emitted
        except Exception:
            logger.exception("Rule sweep failed")
            return emitted
        finally:
            db.close()

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                await asyncio.sleep(config.RULE_SWEEP_INTERVAL_SEC)
                emitted = self.sweep()
                if emitted:
                    logger.info("Rule engine emitted %s escalation alert(s)", emitted)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Rule engine sweep crashed")
        self._running = False

    def stop(self) -> None:
        self._running = False


rule_engine = RuleEngine()